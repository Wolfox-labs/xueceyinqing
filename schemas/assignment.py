"""教师任务与学生任务的轻量数据结构。"""
from typing import Literal

from pydantic import BaseModel, Field


class AssignmentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    topic: str = Field(min_length=1, max_length=200)
    resource_type: Literal["document", "mindmap", "exercise", "ppt"] = "document"
    instructions: str = Field(default="", max_length=1000)
    due_at: str | None = None


class AssignmentItem(BaseModel):
    id: str
    title: str
    topic: str
    resource_type: str
    instructions: str = ""
    due_at: str | None = None
    created_at: str
    completed: bool = False
    completion_count: int = 0


class AssignmentListResponse(BaseModel):
    assignments: list[AssignmentItem]


class TeacherOverviewResponse(BaseModel):
    stats: dict
    students: list[dict]
    assignments: list[AssignmentItem]