"""多智能体消融实验配置结构。"""
from typing import Literal

from pydantic import BaseModel, Field


class AgentRuntimeConfigUpdate(BaseModel):
    profile_enabled: bool | None = None
    critic_enabled: bool | None = None
    reviewer_enabled: bool | None = None
    quiz_agent_enabled: bool | None = None
    orchestration_mode: Literal["multi_agent", "single_agent"] | None = None
    standard_threshold: float | None = Field(default=None, ge=0, le=1)
    deliberate_threshold: float | None = Field(default=None, ge=0, le=1)
    max_rounds: int | None = Field(default=None, ge=0, le=5)

class AblationRunRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    # variants/topics 上限是必要的：单次实验的总运行次数 =
    # variants × topics × repetitions，而每运行一次都真实调用大模型。
    # topics 此前完全无上限，一次请求就能排出上万次调用。
    variants: list[str] = Field(min_length=1, max_length=6)
    topics: list[str] = Field(min_length=1, max_length=20)
    repetitions: int = Field(default=1, ge=1, le=5)
    task_type: Literal["document", "exercise"] = "document"
    dry_run: bool = False


class ResourceFeedbackRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=200)
    resource_type: str = Field(default="document", max_length=40)
    rating: Literal["helpful", "neutral", "not_helpful"]
    difficulty: Literal["too_easy", "appropriate", "too_hard"] = "appropriate"
    source_match: bool | None = None