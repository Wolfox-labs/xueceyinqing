"""认证 API 数据结构。"""
from typing import Literal

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    role: Literal["student", "teacher"] | None = None


class RegisterRequest(BaseModel):
    """自助注册请求。

    不含 role 字段：自助注册一律创建学生账号，教师只能由运维通过
    DEMO_*_PASSWORD 种子账号或 create_user() 开通。旧前端若仍发送 role，
    Pydantic 会忽略该多余字段。
    """

    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=6, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=6, max_length=128)

class UserInfo(BaseModel):
    user_id: str
    username: str
    role: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: str
    user: UserInfo