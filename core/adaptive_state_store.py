"""持久化用户自适应学习状态，避免服务重启后丢失真实证据。"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DB_PATH = _PROJECT_ROOT / "runtime" / "app.db"


class AdaptiveStateStore:
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
                CREATE TABLE IF NOT EXISTS adaptive_states (
                    user_id TEXT NOT NULL,
                    knowledge_point TEXT NOT NULL,
                    mastery REAL NOT NULL,
                    evidence_count INTEGER NOT NULL DEFAULT 0,
                    last_practiced TEXT,
                    PRIMARY KEY (user_id, knowledge_point)
                );
                CREATE TABLE IF NOT EXISTS adaptive_errors (
                    user_id TEXT NOT NULL,
                    knowledge_point TEXT NOT NULL,
                    error_count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, knowledge_point)
                );
                """
            )

    def load(self, user_id: str) -> tuple[list[dict], dict[str, int]]:
        with self._connect() as conn:
            state_rows = conn.execute(
                """SELECT knowledge_point, mastery, evidence_count, last_practiced
                   FROM adaptive_states WHERE user_id = ?""",
                (user_id,),
            ).fetchall()
            error_rows = conn.execute(
                "SELECT knowledge_point, error_count FROM adaptive_errors WHERE user_id = ?",
                (user_id,),
            ).fetchall()
        states = [dict(row) for row in state_rows]
        errors = {row["knowledge_point"]: int(row["error_count"]) for row in error_rows}
        return states, errors

    def save_state(
        self,
        user_id: str,
        knowledge_point: str,
        mastery: float,
        evidence_count: int,
        last_practiced: str | None,
    ) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """INSERT INTO adaptive_states
                   (user_id, knowledge_point, mastery, evidence_count, last_practiced)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(user_id, knowledge_point)
                   DO UPDATE SET mastery=excluded.mastery,
                                 evidence_count=excluded.evidence_count,
                                 last_practiced=excluded.last_practiced""",
                (user_id, knowledge_point, mastery, evidence_count, last_practiced),
            )

    def save_errors(self, user_id: str, errors: dict[str, int]) -> None:
        with self._lock, self._connect() as conn:
            for knowledge_point, count in errors.items():
                conn.execute(
                    """INSERT INTO adaptive_errors(user_id, knowledge_point, error_count)
                       VALUES (?, ?, ?)
                       ON CONFLICT(user_id, knowledge_point)
                       DO UPDATE SET error_count=excluded.error_count""",
                    (user_id, knowledge_point, int(count)),
                )