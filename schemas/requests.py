"""API 层请求模型。

从 api_server/main.py 迁移而来：路由拆到 api_server/routers/*.py 之后，
请求模型如果留在 main.py，路由模块就得反向导入 main（循环依赖）。

字段与默认值与原定义逐字一致，仅去掉不再使用的 Field 导入。
"""
from __future__ import annotations

from pydantic import BaseModel


class CreateSessionRequest(BaseModel):
    user_id: str = "default"


class GenerateRequest(BaseModel):
    type: str = "document"
    topic: str
    user_id: str = "default"
    theme: str = "dark_tech"
    material_ids: list[str] = []


class LearningPathGenerateRequest(BaseModel):
    topic: str = "Python 编程"
    user_id: str = "default"


class FileTicketRequest(BaseModel):
    filename: str


class SaveQuestionsRequest(BaseModel):
    topic: str
    raw_text: str


class UpdateNodeResourceRequest(BaseModel):
    resource_type: str = ""
    resource_ref: str = ""


class UpdateNodeStatusRequest(BaseModel):
    status: str = "in_progress"
