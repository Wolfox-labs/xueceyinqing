"""个人学习资料 API 数据结构。"""
from pydantic import BaseModel


class MaterialItem(BaseModel):
    id: str
    name: str
    file_type: str
    size_bytes: int
    enabled: bool
    status: str
    created_at: str
    updated_at: str


class MaterialListResponse(BaseModel):
    materials: list[MaterialItem]


class MaterialToggleRequest(BaseModel):
    enabled: bool


class MaterialSource(BaseModel):
    id: str
    name: str
    excerpt: str