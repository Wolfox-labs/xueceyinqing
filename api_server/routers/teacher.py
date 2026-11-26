"""教师工作台与轻量作业路由。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from api_server.deps import (
    _assignment_service,
    _auth_service,
    _require_teacher,
    _uid,
)
from schemas.assignment import (
    AssignmentCreate,
    AssignmentItem,
    AssignmentListResponse,
    TeacherOverviewResponse,
)

router = APIRouter(tags=["teacher"])


@router.get("/api/teacher/overview", response_model=TeacherOverviewResponse)
async def teacher_overview(request: Request):
    _require_teacher(request)
    teacher_id = _uid()
    students = _auth_service.list_users("student")
    overview = _assignment_service.overview(teacher_id, len(students))
    return {
        **overview,
        "students": students,
    }


@router.post("/api/assignments", response_model=AssignmentItem)
async def create_assignment(req: AssignmentCreate, request: Request):
    _require_teacher(request)
    return _assignment_service.create_assignment(
        _uid(),
        req.title.strip(),
        req.topic.strip(),
        req.resource_type,
        req.instructions.strip(),
        req.due_at,
    )


@router.get("/api/assignments", response_model=AssignmentListResponse)
async def list_assignments(request: Request):
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="未登录")
    if user.role == "teacher":
        items = _assignment_service.list_for_teacher(user.user_id)
    else:
        items = _assignment_service.list_for_student(user.user_id)
    return {"assignments": items}


@router.post("/api/assignments/{assignment_id}/complete")
async def complete_assignment(assignment_id: str, request: Request):
    user = getattr(request.state, "user", None)
    if user is None or user.role != "student":
        raise HTTPException(status_code=403, detail="仅学生账号可完成任务")
    result = _assignment_service.complete(user.user_id, assignment_id)
    if result is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return result
