"""SQLite 通用键值存储。

用于用户画像、测评结果、学习路径、学习时长和虚拟学习者状态。
这些数据不需要向量索引，放在 SQLite 比放在 ChromaDB 更稳定。
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class SQLiteKVStore:
    def __init__(self, db_path: str | None = None) -> None:
        path = db_path or os.getenv("APP_DB_PATH") or str(_PROJECT_ROOT / "runtime" / "app.db")
        self._db_path = Path(path).resolve()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(str(self._db_path), timeout=10)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS kv_store (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def save_data(self, key: str, data: dict) -> None:
        self.set_text(key, json.dumps(data, ensure_ascii=False))

    def get_data(self, key: str) -> dict | None:
        raw = self.get_text(key)
        if raw is None:
            return None
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, dict) else None

    def set_text(self, key: str, value: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO kv_store(key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                """,
                (key, value, now),
            )

    def get_text(self, key: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM kv_store WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def list_data_by_prefix(self, prefix: str) -> list[dict]:
        escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT value FROM kv_store WHERE key LIKE ? ESCAPE '\\'",
                (escaped + "%",),
            ).fetchall()
        values = []
        for (raw,) in rows:
            try:
                value = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                values.append(value)
        return values

    def set_value(self, key: str, value: Any) -> None:
        self.set_text(key, json.dumps(value, ensure_ascii=False))

    def get_value(self, key: str) -> Any:
        raw = self.get_text(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw