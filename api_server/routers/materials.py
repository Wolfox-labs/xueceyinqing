"""个人学习资料路由。"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from api_server.deps import (
    _ctx_wrap,
    _material_service,
    _public_error,
    _read_upload_limited,
    _uid,
)
from core.vision_ocr import VisionServiceError
from schemas.material import MaterialItem, MaterialListResponse, MaterialToggleRequest

router = APIRouter(tags=["materials"])


@router.get("/api/materials", response_model=MaterialListResponse)
async def list_materials():
    return {"materials": _material_service.list_materials(_uid())}


@router.post("/api/materials", response_model=MaterialItem)
async def upload_material(request: Request, file: UploadFile = File(...)):
    user_id = _uid()
    try:
        # 先按上限分块读入，再交给解析（解析内部还会再校验一次格式与大小）。
        data = await _read_upload_limited(request, file)
        return await asyncio.get_running_loop().run_in_executor(
            None,
            _ctx_wrap(lambda: _material_service.add_material(
                user_id, file.filename or "未命名资料", data
            )),
        )
    except HTTPException:
        # 413 等由本函数主动抛出的状态码必须原样传出，
        # 否则会被下面的通用 except 改写成语义不同的 422。
        raise
    except VisionServiceError as exc:
        # 识别服务不可用属于服务侧故障，用 503 明确区分于"你的文件有问题"（400）。
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=_public_error(exc, "资料解析失败，请检查文件格式或大小"),
        ) from exc


@router.patch("/api/materials/{material_id}", response_model=MaterialItem)
async def update_material(material_id: str, req: MaterialToggleRequest):
    item = _material_service.set_enabled(_uid(), material_id, req.enabled)
    if item is None:
        raise HTTPException(status_code=404, detail="资料不存在")
    return item


@router.delete("/api/materials/{material_id}")
async def delete_material(material_id: str):
    if not _material_service.delete_material(_uid(), material_id):
        raise HTTPException(status_code=404, detail="资料不存在")
    return {"status": "ok"}
