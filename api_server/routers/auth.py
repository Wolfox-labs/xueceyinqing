"""认证、账号与学习时长路由。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from api_server.deps import (
    _auth_service,
    _bearer_token,
    _uid,
)
from core.learning_time_service import LearningTimeService
from schemas.activity import LearningHeartbeatRequest
from schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    UserInfo,
)

router = APIRouter(tags=["auth"])


@router.post("/api/auth/login", response_model=LoginResponse)
async def auth_login(req: LoginRequest):
    result = _auth_service.login(req.username, req.password, req.role)
    if result is None:
        raise HTTPException(status_code=401, detail="账号、密码或角色不正确")
    token, user, expires_at = result
    return LoginResponse(
        access_token=token,
        expires_at=expires_at.isoformat(),
        user=UserInfo(user_id=user.user_id, username=user.username, role=user.role),
    )


@router.post("/api/auth/logout")
async def auth_logout(request: Request):
    _auth_service.logout(_bearer_token(request))
    return {"status": "ok"}


@router.post("/api/auth/register", response_model=LoginResponse)
async def auth_register(req: RegisterRequest):
    try:
        # 自助注册一律创建学生账号：role 不再接受客户端指定，否则任何访客都能
        # 注册成 teacher 并访问全校学生名单、修改全局实验配置。
        token, user, expires_at = _auth_service.register(req.username, req.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return LoginResponse(
        access_token=token,
        expires_at=expires_at.isoformat(),
        user=UserInfo(user_id=user.user_id, username=user.username, role=user.role),
    )


@router.post("/api/auth/change-password")
async def change_password(req: ChangePasswordRequest, request: Request):
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="未登录")
    try:
        _auth_service.change_password(user.user_id, req.current_password, req.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "message": "密码已修改，请重新登录"}


@router.get("/api/auth/me", response_model=UserInfo)
async def auth_me(request: Request):
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="未登录")
    return UserInfo(user_id=user.user_id, username=user.username, role=user.role)


@router.post("/api/activity/heartbeat")
async def learning_time_heartbeat(req: LearningHeartbeatRequest):
    return LearningTimeService(_uid()).record(req.seconds, source=req.source)


@router.get("/api/activity/summary")
async def learning_time_summary():
    return LearningTimeService(_uid()).summary()
