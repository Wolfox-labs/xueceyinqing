"""短期文件下载票据服务。

登录 Token 不应出现在 URL 中。文件下载先通过认证接口领取短期票据，
浏览器再使用票据打开下载地址；票据过期或使用后失效。
"""
from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


@dataclass(slots=True)
class DownloadTicket:
    user_id: str
    path: Path
    expires_at: datetime


class FileTicketService:
    def __init__(self, ttl_seconds: int = 90) -> None:
        self.ttl = timedelta(seconds=max(10, ttl_seconds))
        self._tickets: dict[str, DownloadTicket] = {}
        self._lock = threading.RLock()

    def create(self, user_id: str, path: Path) -> tuple[str, datetime]:
        ticket = secrets.token_urlsafe(24)
        expires_at = datetime.now(timezone.utc) + self.ttl
        with self._lock:
            # 未被兑换的票据此前会永久留在字典里：签发前顺手清理过期项。
            self._purge_locked(datetime.now(timezone.utc))
            self._tickets[ticket] = DownloadTicket(user_id=user_id, path=path, expires_at=expires_at)
        return ticket, expires_at

    def resolve(self, ticket: str, user_id: str | None = None) -> Path | None:
        now = datetime.now(timezone.utc)
        with self._lock:
            record = self._tickets.pop(ticket, None)
        if record is None or record.expires_at <= now:
            return None
        if user_id and record.user_id != user_id:
            return None
        return record.path

    def purge_expired(self) -> int:
        """清理已过期票据，返回清理数量。"""
        with self._lock:
            return self._purge_locked(datetime.now(timezone.utc))

    def pending(self) -> int:
        """当前未兑换票据数量（供测试与观测使用）。"""
        with self._lock:
            return len(self._tickets)

    def _purge_locked(self, now: datetime) -> int:
        expired = [key for key, record in self._tickets.items() if record.expires_at <= now]
        for key in expired:
            del self._tickets[key]
        return len(expired)