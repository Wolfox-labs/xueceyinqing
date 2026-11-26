"""
学习路径的结构化输出定义。
"""
from pydantic import BaseModel, Field


class PathNode(BaseModel):
    id: str
    title: str
    type: str = "document"
    duration: str = ""
    status: str = "pending"
    deps: list[str] = Field(default_factory=list)
    knowledge_point: str = ""
    resource_type: str = ""
    resource_ref: str = ""


class LearningPath(BaseModel):
    title: str
    topic: str
    nodes: list[PathNode]
    user_id: str = "default"
    created_at: str = ""
    updated_at: str = ""
