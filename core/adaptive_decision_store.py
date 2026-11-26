"""记录真实算法决策，供算法实验室追踪与解释。"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DB_PATH = _PROJECT_ROOT / "runtime" / "app.db"


class AdaptiveDecisionStore:
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
                CREATE TABLE IF NOT EXISTS adaptive_decisions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    knowledge_point TEXT NOT NULL DEFAULT '',
                    mastery REAL,
                    forgetting REAL,
                    urgency REAL,
                    selected_action TEXT NOT NULL DEFAULT '',
                    reward REAL,
                    related_id TEXT NOT NULL DEFAULT '',
                    details_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_adaptive_decisions_user
                    ON adaptive_decisions(user_id, created_at DESC);
                """
            )

    def save(
        self,
        user_id: str,
        event_type: str,
        *,
        knowledge_point: str = "",
        mastery: float | None = None,
        forgetting: float | None = None,
        urgency: float | None = None,
        selected_action: str = "",
        reward: float | None = None,
        related_id: str = "",
        details: dict | None = None,
    ) -> dict:
        item_id = uuid.uuid4().hex
        created_at = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                """INSERT INTO adaptive_decisions
                   (id, user_id, event_type, knowledge_point, mastery, forgetting,
                    urgency, selected_action, reward, related_id, details_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    item_id,
                    user_id,
                    event_type,
                    knowledge_point,
                    mastery,
                    forgetting,
                    urgency,
                    selected_action,
                    reward,
                    related_id,
                    json.dumps(details or {}, ensure_ascii=False),
                    created_at,
                ),
            )
        return {
            "id": item_id,
            "event_type": event_type,
            "knowledge_point": knowledge_point,
            "mastery": mastery,
            "forgetting": forgetting,
            "urgency": urgency,
            "selected_action": selected_action,
            "reward": reward,
            "related_id": related_id,
            "details": details or {},
            "created_at": created_at,
        }

    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> dict:
        try:
            details = json.loads(row["details_json"] or "{}")
        except json.JSONDecodeError:
            details = {}
        return {
            "id": row["id"],
            "event_type": row["event_type"],
            "knowledge_point": row["knowledge_point"],
            "mastery": row["mastery"],
            "forgetting": row["forgetting"],
            "urgency": row["urgency"],
            "selected_action": row["selected_action"],
            "reward": row["reward"],
            "related_id": row["related_id"],
            "details": details,
            "created_at": row["created_at"],
        }

    def latest_for_related(self, user_id: str, event_type: str, related_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT * FROM adaptive_decisions
                   WHERE user_id = ? AND event_type = ? AND related_id = ?
                   ORDER BY created_at DESC LIMIT 1""",
                (user_id, event_type, related_id),
            ).fetchone()
        return self._row_to_item(row) if row is not None else None

    def latest_for_knowledge_point(
        self, user_id: str, event_type: str, knowledge_point: str
    ) -> dict | None:
        """按知识点回查最近一次决策。

        用途：把奖励记到**真正交付给用户**的 (context, action) 上。原先
        /api/adaptive/evidence 是重新 select 一个动作再给它记奖励，等于让策略
        奖励自己当前的偏好，而不是实际教学效果。
        """
        if not knowledge_point:
            return None
        with self._connect() as conn:
            row = conn.execute(
                """SELECT * FROM adaptive_decisions
                   WHERE user_id = ? AND event_type = ? AND knowledge_point = ?
                   ORDER BY created_at DESC LIMIT 1""",
                (user_id, event_type, knowledge_point),
            ).fetchone()
        return self._row_to_item(row) if row is not None else None

    def list_for_user(self, user_id: str, limit: int = 50) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM adaptive_decisions
                   WHERE user_id = ?
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (user_id, max(1, min(limit, 200))),
            ).fetchall()
        return [self._row_to_item(row) for row in rows]