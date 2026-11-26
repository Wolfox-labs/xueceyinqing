"""
对话记忆管理 — 压缩、格式化上下文、存取对话记录。
"""
import re
from db.interface import StorageBackend, ConversationRecord


class ConversationMemory:
    """管理单个用户的对话记忆。

    与 user_id 绑定。不同用户应创建不同实例。
    多 session/agent 可能同时使用，但当前不考虑并发。
    """

    def __init__(self, store: StorageBackend, user_id: str):
        self._store = store
        self._user_id = user_id

    @staticmethod
    def compress(text: str, max_chars: int = 300) -> str:
        """截取回答开头作为摘要，尽量在句号处截断。"""
        if len(text) <= max_chars:
            return text
        truncated = text[:max_chars]
        sentences = re.split(r"(?<=[。.！!？?\n])", truncated)
        if len(sentences) > 1:
            sentences.pop()
        return "".join(sentences).rstrip()

    @staticmethod
    def format_context(records: list[ConversationRecord]) -> str:
        """将对话记录列表格式化为可注入 Task 的上下文文本。"""
        if not records:
            return ""
        lines = []
        for r in records:
            lines.append(f"用户：{r.question}")
            lines.append(f"助手：{r.answer_summary}")
        return "\n".join(lines)

    def get_context(self, session_id: str, current_turn: int,
                    n: int = 5) -> str:
        """获取最近 N 轮对话上下文（已格式化）。"""
        records = self._store.get_recent_conversations(
            self._user_id, session_id, current_turn, n=n
        )
        return self.format_context(records)

    def save_turn(self, session_id: str, turn: int,
                   question: str, answer_full: str) -> None:
        """压缩回答并持久化一轮对话。"""
        summary = self.compress(answer_full)
        record = ConversationRecord(
            user_id=self._user_id,
            session_id=session_id,
            turn=turn,
            question=question,
            answer_summary=summary,
            answer_full=answer_full,
        )
        self._store.save_conversation(record)

    def get_messages(self, session_id: str) -> list[dict]:
        """直接返回结构化消息列表，不经过文本格式化。"""
        records = self._store.get_recent_conversations(
            self._user_id, session_id, current_turn=99999, n=100
        )
        messages = []
        for r in records:
            messages.append({
                "id": r.record_id,
                "role": "user",
                "content": r.question,
                "timestamp": r.timestamp or "",
            })
            messages.append({
                "id": f"{r.record_id}_reply",
                "role": "assistant",
                "content": r.answer_full or r.answer_summary,
                "timestamp": r.timestamp or "",
            })
        return messages

    def get_next_turn(self, session_id: str) -> int:
        """返回当前 session 的下一轮编号（已有记录的最大 turn + 1，无记录时返回 1）。"""
        records = self._store.get_recent_conversations(
            self._user_id, session_id, current_turn=99999, n=100
        )
        if not records:
            return 1
        return max(r.turn for r in records) + 1
