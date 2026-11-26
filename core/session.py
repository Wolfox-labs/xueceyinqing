"""
会话生命周期管理 — session_id 生成与轮次追踪。

session_id 使用“时间戳 + 随机短 ID”，避免同一秒内创建多个会话时发生碰撞。
"""
from datetime import datetime
from uuid import uuid4


class SessionManager:
    """管理一次会话的 ID 与轮次状态。"""

    def __init__(self):
        self._session_id: str | None = None
        self._turn: int = 0

    @property
    def session_id(self) -> str:
        if self._session_id is None:
            self.create()
        return self._session_id

    @property
    def turn(self) -> int:
        return self._turn

    def create(self) -> str:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self._session_id = f"{stamp}-{uuid4().hex[:8]}"
        self._turn = 0
        return self._session_id

    def next_turn(self) -> int:
        self._turn += 1
        return self._turn