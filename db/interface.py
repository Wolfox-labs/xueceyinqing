"""
存储后端抽象接口 — 定义所有数据库操作的标准协议。

所有具体存储实现（ChromaDB、SQLite、PostgreSQL 等）必须实现此接口，
方便之后替换底层数据库而无需改动上层代码。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ConversationRecord:
    user_id: str
    session_id: str
    turn: int
    question: str
    answer_summary: str
    answer_full: str
    topics: list[str] = field(default_factory=list)
    timestamp: Optional[str] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()

    @property
    def record_id(self) -> str:
        return f"{self.user_id}_{self.session_id}_{self.turn:04d}"

    @property
    def search_text(self) -> str:
        summary = self.answer_summary[:200] if self.answer_summary else ""
        topics_str = "、".join(self.topics) if self.topics else ""
        return f"问：{self.question}\n答：{summary}\n主题：{topics_str}"


class StorageBackend(ABC):
    """
    存储后端抽象基类。
    方法命名遵循 get_ / save_ / search_ 前缀约定。
    """

    # ---- 知识库 ----

    @abstractmethod
    def search_knowledge(self, query: str, n_results: int = 3) -> list[str]:
        """语义搜索知识库，返回最相关的文本片段列表。"""
        ...

    # ---- 用户画像 ----

    @abstractmethod
    def get_profile(self, user_id: str) -> str:
        """读取指定用户的画像文本。"""
        ...

    @abstractmethod
    def update_profile(self, user_id: str, profile_text: str) -> None:
        """写入或更新指定用户的画像文本。"""
        ...

    # ---- 对话记忆 ----

    @abstractmethod
    def save_conversation(self, record: ConversationRecord) -> None:
        """保存一条压缩后的对话记录。"""
        ...

    @abstractmethod
    def get_recent_conversations(
        self, user_id: str, session_id: str, current_turn: int, n: int = 5
    ) -> list[ConversationRecord]:
        """获取当前 session 最近 N 轮对话记录（时序）。"""
        ...

    @abstractmethod
    def search_conversations(
        self, user_id: str, query: str, n_results: int = 3
    ) -> list[str]:
        """语义搜索用户的历史对话，返回相关对话摘要列表。"""
        ...

    # ---- 通用键值存储 ----

    @abstractmethod
    def save_data(self, key: str, data: dict) -> None:
        """通用键值数据存储。"""
        ...

    @abstractmethod
    def get_data(self, key: str) -> dict | None:
        """按 key 读取数据。"""
        ...

    @abstractmethod
    def list_data_by_prefix(self, prefix: str) -> list[dict]:
        """按 key 前缀列出所有数据。"""
        ...

    # ---- 会话列表 ----

    @abstractmethod
    def list_sessions(self, user_id: str) -> list[dict]:
        """返回指定用户的会话列表，每条含 id、title、updatedAt。"""
        ...
