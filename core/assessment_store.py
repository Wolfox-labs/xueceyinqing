"""
评估结果存取。
"""
from datetime import datetime
from db.interface import StorageBackend


class AssessmentStore:
    """管理评估结果的持久化存取。"""

    def __init__(self, store: StorageBackend, user_id: str):
        self._store = store
        self._user_id = user_id

    def save_assessment(self, result: dict) -> None:
        """保存评估结果到 user_profiles collection。"""
        ts = result.get("timestamp") or datetime.now().isoformat()
        key = f"assessment_{self._user_id}_{ts}"
        self._store.save_data(key, result)

    def get_latest_assessment(self) -> dict | None:
        """获取用户最近一次评估结果。"""
        prefix = f"assessment_{self._user_id}_"
        records = self._store.list_data_by_prefix(prefix)
        if not records:
            return None
        records.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return records[0]

    def get_history(self, limit: int = 20) -> list[dict]:
        """获取按时间倒序的评估历史列表。"""
        prefix = f"assessment_{self._user_id}_"
        records = self._store.list_data_by_prefix(prefix)
        records.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return records[:limit]
