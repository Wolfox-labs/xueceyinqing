"""
学习路径存取。
"""
from datetime import datetime
from db.interface import StorageBackend
from schemas.learning_path import LearningPath


class PathStore:
    """管理学习路径的持久化存取。"""

    def __init__(self, store: StorageBackend, user_id: str):
        self._store = store
        self._user_id = user_id

    @staticmethod
    def _path_key(user_id: str, topic: str) -> str:
        return f"path_{user_id}_{topic}"

    def save_path(self, path: LearningPath) -> str:
        """保存学习路径。返回 key 字符串。"""
        path.updated_at = datetime.now().isoformat()
        if not path.created_at:
            path.created_at = path.updated_at
        key = self._path_key(path.user_id, path.topic)
        self._store.save_data(key, path.model_dump())
        return key

    def get_path(self, topic: str = None) -> LearningPath | None:
        """获取学习路径。不传 topic 返回最新路径。"""
        if topic:
            key = self._path_key(self._user_id, topic)
            data = self._store.get_data(key)
            if data:
                try:
                    return LearningPath.model_validate(data)
                except Exception:
                    return None
            return None

        prefix = f"path_{self._user_id}_"
        records = self._store.list_data_by_prefix(prefix)
        candidates = []
        for data in records:
            try:
                path = LearningPath.model_validate(data)
                candidates.append(path)
            except Exception:
                continue

        if not candidates:
            return None

        candidates.sort(key=lambda p: p.updated_at or "", reverse=True)
        return candidates[0]
