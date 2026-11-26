"""轻量教师任务服务：教师布置任务，学生标记完成。"""
from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DB_PATH = _PROJECT_ROOT / "runtime" / "app.db"


class AssignmentService:
    def __init__(self) -> None:
        self._db_path = _DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS assignments (
                    id TEXT PRIMARY KEY,
                    teacher_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    resource_type TEXT NOT NULL,
                    instructions TEXT NOT NULL DEFAULT '',
                    due_at TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS assignment_completions (
                    assignment_id TEXT NOT NULL,
                    student_id TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    PRIMARY KEY (assignment_id, student_id),
                    FOREIGN KEY(assignment_id) REFERENCES assignments(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_assignments_teacher
                    ON assignments(teacher_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_completions_student
                    ON assignment_completions(student_id);
                """
            )

    def create_assignment(
        self,
        teacher_id: str,
        title: str,
        topic: str,
        resource_type: str,
        instructions: str = "",
        due_at: str | None = None,
    ) -> dict:
        assignment_id = uuid.uuid4().hex
        now = self._now()
        with self._lock, self._connect() as conn:
            conn.execute(
                """INSERT INTO assignments
                   (id, teacher_id, title, topic, resource_type, instructions, due_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (assignment_id, teacher_id, title, topic, resource_type, instructions, due_at, now),
            )
        return {
            "id": assignment_id,
            "title": title,
            "topic": topic,
            "resource_type": resource_type,
            "instructions": instructions,
            "due_at": due_at,
            "created_at": now,
            "completed": False,
            "completion_count": 0,
        }

    def list_for_teacher(self, teacher_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT a.*, COUNT(c.student_id) AS completion_count
                   FROM assignments a
                   LEFT JOIN assignment_completions c ON c.assignment_id = a.id
                   WHERE a.teacher_id = ?
                   GROUP BY a.id
                   ORDER BY a.created_at DESC""",
                (teacher_id,),
            ).fetchall()
        return [self._row_to_item(row) for row in rows]

    def list_for_student(self, student_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT a.*, c.completed_at
                   FROM assignments a
                   LEFT JOIN assignment_completions c
                     ON c.assignment_id = a.id AND c.student_id = ?
                   ORDER BY a.created_at DESC""",
                (student_id,),
            ).fetchall()
        return [self._row_to_item(row) for row in rows]

    def complete(self, student_id: str, assignment_id: str) -> dict | None:
        now = self._now()
        with self._lock, self._connect() as conn:
            exists = conn.execute(
                "SELECT 1 FROM assignments WHERE id = ?", (assignment_id,)
            ).fetchone()
            if exists is None:
                return None
            conn.execute(
                """INSERT INTO assignment_completions(assignment_id, student_id, completed_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(assignment_id, student_id)
                   DO UPDATE SET completed_at = excluded.completed_at""",
                (assignment_id, student_id, now),
            )
        return {"status": "ok", "completed_at": now}

    def overview(self, teacher_id: str, student_count: int) -> dict:
        assignments = self.list_for_teacher(teacher_id)
        completed_count = sum(int(item.get("completion_count") or 0) for item in assignments)
        possible = max(1, student_count * len(assignments))
        return {
            "stats": {
                "student_count": student_count,
                "assignment_count": len(assignments),
                "completed_count": completed_count,
                "completion_rate": round(completed_count / possible * 100, 1),
            },
            "assignments": assignments,
        }

    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> dict:
        keys = set(row.keys())
        return {
            "id": row["id"],
            "title": row["title"],
            "topic": row["topic"],
            "resource_type": row["resource_type"],
            "instructions": row["instructions"] or "",
            "due_at": row["due_at"],
            "created_at": row["created_at"],
            "completed": bool(row["completed_at"]) if "completed_at" in keys else False,
            "completion_count": int(row["completion_count"] or 0) if "completion_count" in keys else 0,
        }