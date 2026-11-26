from pydantic import BaseModel
from typing import Union
from .profile import StudentProfile
from .learning_path import LearningPath, PathNode


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    crewai_ready: bool
    # 图片/扫描件能否识别取决于多模态接口是否配置就绪，单独暴露便于部署自查。
    image_recognition_ready: bool
    # AI 引擎（crewai + LLM）后台加载进度：pending/loading/ready/error。
    # 端口先可用、引擎后加载，所以必须把这两件事分开报告，否则前端只能猜。
    ai_engine_state: str = "pending"
    ai_engine_detail: str = ""


class SessionResponse(BaseModel):
    id: str
    title: str
    updated_at: str


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    timestamp: str


class ProfileResponse(BaseModel):
    user_id: str
    profile: StudentProfile


class ReportSummaryResponse(BaseModel):
    total_hours: float = 0.0
    completed_nodes: int = 0
    avg_accuracy: float = 0.0
    last_topic: str = ""


class ChartData(BaseModel):
    labels: list[str] = []
    values: list[int | float] = []


class ChartsResponse(BaseModel):
    radar: ChartData | None = None
    line: ChartData | None = None
    pie: ChartData | None = None


class ReportSuggestionsResponse(BaseModel):
    suggestions: list[str] = []


class ErrorResponse(BaseModel):
    detail: str


LearningPathResponse = Union[list[PathNode], LearningPath]
