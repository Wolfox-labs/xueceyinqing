"""学习时长统计服务。

前端按活跃学习时间发送心跳，本服务按用户和日期累计秒数，
并通过现有 StorageBackend 的通用键值接口持久化。
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

from db.vector_store import get_store

_CST = timezone(timedelta(hours=8))
_LOCK = threading.RLock()
_MAX_HEARTBEAT_SECONDS = 120


class LearningTimeService:
    def __init__(self, user_id: str, store=None) -> None:
        self.user_id = user_id
        self._store = store or get_store()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(_CST)

    def _day_key(self, day: str) -> str:
        return f"learning_time_day_{self.user_id}_{day}"

    def _total_key(self) -> str:
        return f"learning_time_total_{self.user_id}"

    def record(self, seconds: int, source: str = "web") -> dict:
        """累计一次学习心跳，seconds 限制为 1~120 秒。"""
        seconds = max(1, min(int(seconds), _MAX_HEARTBEAT_SECONDS))
        now = self._now()
        day = now.strftime("%Y-%m-%d")
        day_key = self._day_key(day)
        total_key = self._total_key()

        with _LOCK:
            day_data = self._store.get_data(day_key) or {
                "user_id": self.user_id,
                "date": day,
                "seconds": 0,
            }
            total_data = self._store.get_data(total_key) or {
                "user_id": self.user_id,
                "seconds": 0,
            }

            day_data["seconds"] = int(day_data.get("seconds", 0)) + seconds
            day_data["updated_at"] = now.isoformat()
            day_data["source"] = source
            total_data["seconds"] = int(total_data.get("seconds", 0)) + seconds
            total_data["updated_at"] = now.isoformat()

            self._store.save_data(day_key, day_data)
            self._store.save_data(total_key, total_data)

        return self.summary()

    def summary(self) -> dict:
        now = self._now()
        day = now.strftime("%Y-%m-%d")
        with _LOCK:
            day_data = self._store.get_data(self._day_key(day)) or {}
            total_data = self._store.get_data(self._total_key()) or {}

        today_seconds = max(0, int(day_data.get("seconds", 0)))
        total_seconds = max(0, int(total_data.get("seconds", 0)))
        return {
            "user_id": self.user_id,
            "date": day,
            "today_seconds": today_seconds,
            "today_minutes": round(today_seconds / 60, 1),
            "total_seconds": total_seconds,
            "total_minutes": round(total_seconds / 60, 1),
            "total_hours": round(total_seconds / 3600, 2),
        }