"""
评估检测的数据结构定义。
"""
from pydantic import BaseModel, Field
from typing import Optional


class AssessmentResult(BaseModel):
    user_id: str
    topic: str
    total_score: int
    max_score: int
    percentage: float
    weak_points: list[dict] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    timestamp: str = ""


class AssessmentTask(BaseModel):
    topic: str
    exercise: dict
    user_id: str = "default"


class QuestionItem(BaseModel):
    id: int
    type: str
    question: str
    options: Optional[list[str]] = None
    score: int = 10
    knowledge_point: str = ""
    difficulty: Optional[str] = None


class AssessGenerateResponse(BaseModel):
    assessment_id: str
    title: str
    questions: list[QuestionItem]


class AnswerItem(BaseModel):
    question_id: int
    answer: str


class AssessSubmitRequest(BaseModel):
    assessment_id: str
    user_id: str = "default"
    answers: list[AnswerItem]


class AssessGenerateRequest(BaseModel):
    topic: str
    question_count: int = 5
    user_id: str = "default"
