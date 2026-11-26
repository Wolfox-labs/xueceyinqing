"""学习时长心跳数据结构。"""
from pydantic import BaseModel, Field


class LearningHeartbeatRequest(BaseModel):
    seconds: int = Field(default=30, ge=1, le=120)
    source: str = Field(default="web", max_length=32)