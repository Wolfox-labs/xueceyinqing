"""学习者动态档案的 API 数据结构。"""
from pydantic import BaseModel, Field


class ProfileCardItem(BaseModel):
    label: str
    value: str
    source: str = "system"
    status: str = "default"
    confidence: float | None = None
    score: float | None = None


class ProfileCard(BaseModel):
    id: str
    title: str
    subtitle: str = ""
    kind: str = "list"
    items: list[ProfileCardItem] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    updated_at: str = ""


class ProfileActivity(BaseModel):
    timestamp: str
    source: str
    title: str
    detail: str = ""


class ProfileDashboardResponse(BaseModel):
    user_id: str
    identity: dict = Field(default_factory=dict)
    summary: dict = Field(default_factory=dict)
    cards: list[ProfileCard] = Field(default_factory=list)
    knowledge: dict = Field(default_factory=dict)
    activities: list[ProfileActivity] = Field(default_factory=list)
    update_log: list[ProfileActivity] = Field(default_factory=list)
