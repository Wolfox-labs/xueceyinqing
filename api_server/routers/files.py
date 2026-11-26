"""安全产物下载路由（短期票据 + 归属校验）。"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from api_server.deps import (
    _file_tickets,
    _output_owner,
    _uid,
    output_dir,
)
from schemas.requests import FileTicketRequest

logger = logging.getLogger(__name__)

router = APIRouter(tags=["files"])


@router.post("/api/files/ticket")
async def create_file_ticket(req: FileTicketRequest):
    user_id = _uid()
    safe_name = Path(req.filename).name
    target = (output_dir / safe_name).resolve()
    try:
        target.relative_to(output_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="非法文件名")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    # output 目录是所有用户共用的：必须确认这个产物属于当前用户，否则任何
    # 登录用户都能为别人的成果签发票据并下载。无归属记录的旧产物按兼容策略
    # 放行并告警（见 _record_output_owner 只对新生效）。
    owner = _output_owner(safe_name)
    if owner is not None and owner != user_id:
        logger.warning("越权下载尝试 user=%s owner=%s file=%s", user_id, owner, safe_name)
        raise HTTPException(status_code=404, detail="文件不存在")
    if owner is None:
        logger.warning("产物缺少归属记录，按兼容策略签发票据 file=%s user=%s", safe_name, user_id)
    ticket, expires_at = _file_tickets.create(user_id, target)
    return {
        "ticket": ticket,
        "url": f"/api/files/download/{ticket}",
        "filename": safe_name,
        "expires_at": expires_at.isoformat(),
    }


@router.get("/api/files/download/{ticket}")
async def download_file_by_ticket(ticket: str):
    target = _file_tickets.resolve(ticket)
    if target is None:
        raise HTTPException(status_code=404, detail="下载票据无效或已过期")
    return FileResponse(path=str(target), filename=target.name)
