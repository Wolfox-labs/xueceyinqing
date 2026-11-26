"""多智能体消融实验任务与结果存储。"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DB_PATH = _PROJECT_ROOT / "runtime" / "app.db"


class ExperimentService:
    def __init__(self) -> None:
        self._db_path = _DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS ablation_experiments (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    variants_json TEXT NOT NULL,
                    topics_json TEXT NOT NULL,
                    repetitions INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    total_runs INTEGER NOT NULL,
                    completed_runs INTEGER NOT NULL DEFAULT 0,
                    error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS ablation_runs (
                    id TEXT PRIMARY KEY,
                    experiment_id TEXT NOT NULL,
                    variant TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    repetition INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    output_text TEXT NOT NULL DEFAULT '',
                    latency_ms INTEGER,
                    estimated_tokens INTEGER,
                    format_pass INTEGER,
                    withdrawn INTEGER NOT NULL DEFAULT 0,
                    agent_trace_json TEXT NOT NULL DEFAULT '[]',
                    error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(experiment_id) REFERENCES ablation_experiments(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_ablation_runs_experiment
                    ON ablation_runs(experiment_id, created_at);
                """
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def create(self, user_id: str, name: str, task_type: str, variants: list[str], topics: list[str], repetitions: int) -> dict:
        experiment_id = uuid.uuid4().hex
        total_runs = len(variants) * len(topics) * repetitions
        with self._lock, self._connect() as conn:
            conn.execute(
                """INSERT INTO ablation_experiments
                   (id, user_id, name, task_type, variants_json, topics_json, repetitions,
                    status, total_runs, completed_runs, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, 0, ?)""",
                (
                    experiment_id,
                    user_id,
                    name,
                    task_type,
                    json.dumps(variants, ensure_ascii=False),
                    json.dumps(topics, ensure_ascii=False),
                    repetitions,
                    total_runs,
                    self._now(),
                ),
            )
        return self.get(experiment_id, user_id) or {}

    def get(self, experiment_id: str, user_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM ablation_experiments WHERE id = ? AND user_id = ?",
                (experiment_id, user_id),
            ).fetchone()
            if row is None:
                return None
            runs = conn.execute(
                "SELECT * FROM ablation_runs WHERE experiment_id = ? ORDER BY created_at",
                (experiment_id,),
            ).fetchall()
        item = dict(row)
        item["variants"] = json.loads(item.pop("variants_json") or "[]")
        item["topics"] = json.loads(item.pop("topics_json") or "[]")
        item["runs"] = [self._row_to_run(run) for run in runs]
        return item

    def list_for_user(self, user_id: str, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id FROM ablation_experiments WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, max(1, min(limit, 100))),
            ).fetchall()
        return [item for row in rows if (item := self.get(row["id"], user_id))]

    def update_status(self, experiment_id: str, status: str, error: str = "", completed_at: str | None = None) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE ablation_experiments SET status = ?, error = ?, completed_at = ? WHERE id = ?",
                (status, error, completed_at, experiment_id),
            )

    def increment_completed(self, experiment_id: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE ablation_experiments SET completed_runs = completed_runs + 1 WHERE id = ?",
                (experiment_id,),
            )

    def add_run(self, experiment_id: str, **values) -> dict:
        run_id = uuid.uuid4().hex
        created_at = self._now()
        with self._lock, self._connect() as conn:
            conn.execute(
                """INSERT INTO ablation_runs
                   (id, experiment_id, variant, topic, repetition, status, output_text,
                    latency_ms, estimated_tokens, format_pass, withdrawn, agent_trace_json,
                    error, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_id,
                    experiment_id,
                    values.get("variant", ""),
                    values.get("topic", ""),
                    int(values.get("repetition", 0)),
                    values.get("status", "completed"),
                    values.get("output_text", ""),
                    values.get("latency_ms"),
                    values.get("estimated_tokens"),
                    None if values.get("format_pass") is None else int(bool(values["format_pass"])),
                    int(bool(values.get("withdrawn", False))),
                    json.dumps(values.get("agent_trace", []), ensure_ascii=False),
                    values.get("error", ""),
                    created_at,
                ),
            )
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM ablation_runs WHERE id = ?", (run_id,)).fetchone()
        return self._row_to_run(row)

    @staticmethod
    def _row_to_run(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "variant": row["variant"],
            "topic": row["topic"],
            "repetition": row["repetition"],
            "status": row["status"],
            "output_text": row["output_text"],
            "latency_ms": row["latency_ms"],
            "estimated_tokens": row["estimated_tokens"],
            "format_pass": None if row["format_pass"] is None else bool(row["format_pass"]),
            "withdrawn": bool(row["withdrawn"]),
            "agent_trace": json.loads(row["agent_trace_json"] or "[]"),
            "error": row["error"],
            "created_at": row["created_at"],
        }