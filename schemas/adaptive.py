"""自适应学习引擎 API 数据结构。"""
from datetime import datetime

from pydantic import BaseModel, Field


class MasteryStateInput(BaseModel):
    knowledge_point: str
    mastery: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence_count: int = Field(default=0, ge=0)
    last_practiced: datetime | None = None


class KnowledgeNodeInput(BaseModel):
    name: str
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    prerequisites: list[str] = Field(default_factory=list)


class EvidenceObservation(BaseModel):
    knowledge_point: str
    score: float = Field(ge=0.0, le=1.0)
    observed_at: datetime | None = None


class AdaptiveEvidenceRequest(BaseModel):
    observations: list[EvidenceObservation] = Field(min_length=1)
    recent_errors: dict[str, int] = Field(default_factory=dict)


class AdaptiveRecommendRequest(BaseModel):
    states: list[MasteryStateInput] = Field(min_length=1)
    graph: list[KnowledgeNodeInput] = Field(default_factory=list)
    recent_errors: dict[str, int] = Field(default_factory=dict)
    limit: int | None = Field(default=None, ge=1, le=100)


class RecommendationResponse(BaseModel):
    knowledge_point: str
    effective_mastery: float
    forgetting_risk: float
    priority: float
    target_difficulty: float
    reason: str


class PolicySelectRequest(BaseModel):
    mastery: float = Field(ge=0.0, le=1.0)
    urgency: float = Field(ge=0.0, le=1.0)
    # 调用方没给学习偏好时不应替它假定一个；空串会被 context_key 归入 unknown 桶。
    learning_style: str = ""
    actions: list[str] = Field(default_factory=lambda: [
        "explain", "example", "practice", "review", "challenge"
    ])


class PolicyUpdateRequest(BaseModel):
    context: str
    action: str
    reward: float = Field(ge=0.0, le=1.0)

class AdaptiveSimulationRequest(BaseModel):
    knowledge_point: str = "算法基础"
    mastery: float = Field(default=0.5, ge=0.0, le=1.0)
    forgetting: float = Field(default=0.4, ge=0.0, le=1.0)
    dependency: float = Field(default=0.5, ge=0.0, le=1.0)
    errors: float = Field(default=0.3, ge=0.0, le=1.0)
    importance: float = Field(default=0.7, ge=0.0, le=1.0)