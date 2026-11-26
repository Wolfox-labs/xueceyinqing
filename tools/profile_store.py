"""
用户画像存取工具 — CrewAI Tool 层。
支持多用户隔离（通过 user_id）。
"""
import json
from crewai.tools import BaseTool
from db.vector_store import get_store
from schemas.profile import StudentProfile


class ProfileGetTool(BaseTool):
    name: str = "get_profile"
    description: str = (
        "获取当前用户的画像信息。不需要任何输入参数。"
        "返回一段描述用户学习阶段、知识薄弱点、学习偏好、语言风格的文本。"
        "在对用户进行个性化回答或资源生成之前，应先调用此工具。"
    )

    def __init__(self, user_id: str = "default", **kwargs):
        super().__init__(**kwargs)
        self._user_id = user_id

    def _run(self, _: str = "") -> str:
        store = get_store()
        text = store.get_profile(self._user_id)
        profile = StudentProfile.from_text(text)
        return profile.model_dump_json(indent=2)


class ProfileUpdateTool(BaseTool):
    name: str = "update_profile"
    description: str = (
        "更新用户画像。参数 profile_text 为完整的用户画像描述文本。"
        "应包含学习阶段、正在学习的主题、薄弱点、偏好、语言风格等信息。"
        "每次从对话中发现新信息时调用此工具更新画像。"
    )

    def __init__(self, user_id: str = "default", **kwargs):
        super().__init__(**kwargs)
        self._user_id = user_id

    def _run(self, profile_text: str) -> str:
        store = get_store()
        try:
            data = json.loads(profile_text)
            profile = StudentProfile.model_validate(data)
        except (json.JSONDecodeError, Exception):
            profile = StudentProfile.from_text(profile_text)

        store.update_profile(self._user_id, StudentProfile.to_text(profile))
        return "用户画像已更新。"
