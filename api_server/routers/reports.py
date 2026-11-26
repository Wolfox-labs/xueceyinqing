"""学习报告路由（共用带缓存的报表构建，且已移出事件循环）。"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter

from api_server.deps import _ctx_wrap, _report_data_for, _uid
from schemas.api_responses import (
    ChartData,
    ChartsResponse,
    ReportSuggestionsResponse,
    ReportSummaryResponse,
)

router = APIRouter(tags=["reports"])


@router.get("/api/reports/summary", response_model=ReportSummaryResponse)
async def get_report_summary(user_id: str = "default"):
    user_id = _uid(user_id)
    # 报表构建会读存储并做聚合，属阻塞调用：放到线程池，别占住事件循环。
    loop = asyncio.get_running_loop()
    data = await loop.run_in_executor(None, _ctx_wrap(lambda: _report_data_for(user_id)))
    return ReportSummaryResponse(
        total_hours=data.total_hours,
        completed_nodes=data.completed_nodes,
        avg_accuracy=data.avg_accuracy,
        last_topic=data.last_topic,
    )


@router.get("/api/reports/charts", response_model=ChartsResponse)
async def get_chart_data(user_id: str = "default", type: str = "radar"):
    user_id = _uid(user_id)
    loop = asyncio.get_running_loop()
    data = await loop.run_in_executor(None, _ctx_wrap(lambda: _report_data_for(user_id)))
    if type == "radar" and data.radar:
        return ChartsResponse(radar=ChartData(labels=data.radar["labels"], values=data.radar["values"]))
    if type == "line" and data.line:
        return ChartsResponse(line=ChartData(labels=data.line["labels"], values=data.line["values"]))
    if type == "pie" and data.pie:
        return ChartsResponse(pie=ChartData(labels=data.pie["labels"], values=data.pie["values"]))
    return ChartsResponse()


@router.get("/api/reports/suggestions", response_model=ReportSuggestionsResponse)
async def get_suggestions(user_id: str = "default"):
    user_id = _uid(user_id)
    loop = asyncio.get_running_loop()
    data = await loop.run_in_executor(None, _ctx_wrap(lambda: _report_data_for(user_id)))
    return ReportSuggestionsResponse(suggestions=data.suggestions)
