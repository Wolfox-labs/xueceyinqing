"""多智能体运行配置：Agent 开关、协商阈值和最大轮次。"""
from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DB_PATH = _PROJECT_ROOT / "runtime" / "app.db"
_ROW_ID = 1

_DEFAULT_CONFIG = {
    "profile_enabled": True,
    "critic_enabled": True,
    "reviewer_enabled": True,
    "quiz_agent_enabled": True,
    "orchestration_mode": "multi_agent",
    "standard_threshold": 0.24,
    "deliberate_threshold": 0.68,
    "max_rounds": 2,
}


class AgentConfigService:
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
                CREATE TABLE IF NOT EXISTS agent_runtime_config (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    profile_enabled INTEGER NOT NULL,
                    critic_enabled INTEGER NOT NULL,
                    reviewer_enabled INTEGER NOT NULL,
                    quiz_agent_enabled INTEGER NOT NULL,
                    orchestration_mode TEXT NOT NULL,
                    standard_threshold REAL NOT NULL,
                    deliberate_threshold REAL NOT NULL,
                    max_rounds INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            exists = conn.execute(
                "SELECT 1 FROM agent_runtime_config WHERE id = ?", (_ROW_ID,)
            ).fetchone()
            if exists is None:
                self._insert_defaults(conn)

    def _insert_defaults(self, conn: sqlite3.Connection) -> None:
        from datetime import datetime, timezone

        config = dict(_DEFAULT_CONFIG)
        env_mode = os.getenv("ORCHESTRATION_MODE", "").strip().lower()
        if env_mode in {"multi_agent", "single_agent"}:
            config["orchestration_mode"] = env_mode
        conn.execute(
            """INSERT INTO agent_runtime_config
               (id, profile_enabled, critic_enabled, reviewer_enabled, quiz_agent_enabled,
                orchestration_mode, standard_threshold, deliberate_threshold, max_rounds, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                _ROW_ID,
                int(config["profile_enabled"]),
                int(config["critic_enabled"]),
                int(config["reviewer_enabled"]),
                int(config["quiz_agent_enabled"]),
                config["orchestration_mode"],
                config["standard_threshold"],
                config["deliberate_threshold"],
                config["max_rounds"],
                datetime.now(timezone.utc).isoformat(),
            ),
        )

    @staticmethod
    def _row_to_config(row: sqlite3.Row) -> dict:
        return {
            "profile_enabled": bool(row["profile_enabled"]),
            "critic_enabled": bool(row["critic_enabled"]),
            "reviewer_enabled": bool(row["reviewer_enabled"]),
            "quiz_agent_enabled": bool(row["quiz_agent_enabled"]),
            "orchestration_mode": row["orchestration_mode"],
            "standard_threshold": float(row["standard_threshold"]),
            "deliberate_threshold": float(row["deliberate_threshold"]),
            "max_rounds": int(row["max_rounds"]),
            "updated_at": row["updated_at"],
        }

    def get(self) -> dict:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM agent_runtime_config WHERE id = ?", (_ROW_ID,)
            ).fetchone()
        return self._row_to_config(row)

    def update(self, values: dict) -> dict:
        from datetime import datetime, timezone

        current = self.get()
        merged = {**current, **{key: value for key, value in values.items() if value is not None}}
        mode = str(merged.get("orchestration_mode", "multi_agent")).strip().lower()
        if mode not in {"multi_agent", "single_agent"}:
            raise ValueError("编排模式无效")
        standard = float(merged.get("standard_threshold", 0.24))
        deliberate = float(merged.get("deliberate_threshold", 0.68))
        if not 0 <= standard < deliberate <= 1:
            raise ValueError("阈值必须满足 0 ≤ 标准阈值 < 深度协商阈值 ≤ 1")
        max_rounds = max(0, min(int(merged.get("max_rounds", 2)), 5))
        with self._lock, self._connect() as conn:
            conn.execute(
                """UPDATE agent_runtime_config
                   SET profile_enabled = ?, critic_enabled = ?, reviewer_enabled = ?,
                       quiz_agent_enabled = ?, orchestration_mode = ?,
                       standard_threshold = ?, deliberate_threshold = ?, max_rounds = ?, updated_at = ?
                   WHERE id = ?""",
                (
                    int(bool(merged.get("profile_enabled", True))),
                    int(bool(merged.get("critic_enabled", True))),
                    int(bool(merged.get("reviewer_enabled", True))),
                    int(bool(merged.get("quiz_agent_enabled", True))),
                    mode,
                    standard,
                    deliberate,
                    max_rounds,
                    datetime.now(timezone.utc).isoformat(),
                    _ROW_ID,
                ),
            )
        return self.get()

    def reset(self) -> dict:
        return self.update(dict(_DEFAULT_CONFIG))