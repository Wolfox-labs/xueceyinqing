"""
虚拟课堂数据结构。
"""
from pydantic import BaseModel, Field


class ClassroomQuiz(BaseModel):
    position: str
    question: str
    options: list[str]
    answer: str
    explanation: str


class ClassroomSlide(BaseModel):
    slide_index: int
    title: str
    bullet_points: list[str]
    script: str


class ClassroomScript(BaseModel):
    title: str
    topic: str
    slides: list[ClassroomSlide]
    quizzes: list[ClassroomQuiz] = Field(min_length=3, max_length=3)
