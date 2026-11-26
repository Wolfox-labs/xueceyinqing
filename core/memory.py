"""
向后兼容的 MemoryManager 组合包装。

委托到 ConversationMemory / PathStore / AssessmentStore，
现有调用方无需修改。
"""
from db.vector_store import get_store
from core.conversation_memory import ConversationMemory
from core.path_store import PathStore
from core.assessment_store import AssessmentStore


class MemoryManager:
    """向后兼容的 MemoryManager — 委托到三个拆分模块。"""

    def __init__(self, user_id: str):
        store = get_store()
        self._store = store
        self._user_id = user_id
        self._conv = ConversationMemory(store, user_id)
        self._path = PathStore(store, user_id)
        self._assess = AssessmentStore(store, user_id)

    # ── 对话记忆委托 ──

    @staticmethod
    def compress(text: str, max_chars: int = 300) -> str:
        return ConversationMemory.compress(text, max_chars)

    @staticmethod
    def format_context(records):
        return ConversationMemory.format_context(records)

    def get_context(self, session_id: str, current_turn: int,
                    n: int = 5) -> str:
        return self._conv.get_context(session_id, current_turn, n)

    def save_turn(self, session_id: str, turn: int,
                   question: str, answer_full: str) -> None:
        return self._conv.save_turn(session_id, turn, question, answer_full)

    def get_messages(self, session_id: str) -> list[dict]:
        return self._conv.get_messages(session_id)

    def get_next_turn(self, session_id: str) -> int:
        return self._conv.get_next_turn(session_id)

    # ── 学习路径委托 ──

    def save_path(self, path) -> str:
        return self._path.save_path(path)

    def get_path(self, topic: str = None):
        return self._path.get_path(topic)

    # ── 评估结果委托 ──

    def save_assessment(self, result: dict) -> None:
        return self._assess.save_assessment(result)

    def get_latest_assessment(self) -> dict | None:
        return self._assess.get_latest_assessment()

    # ── 用户画像委托 ──

    def get_profile_text(self) -> str:
        return self._store.get_profile(self._user_id)
