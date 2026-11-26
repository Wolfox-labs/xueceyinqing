"""API 层共享依赖。

这里放**所有路由都要用**的基础设施：认证上下文、限流器、错误文案、上传读取、
产物归属等。抽出来的目的是让 api_server/main.py 只保留"应用装配"（app 创建、
中间件、lifespan、路由挂载），各业务路由可以放进 api_server/routers/*.py 而
不必从 main 反向导入（那会造成循环依赖）。

注意：本模块**不导入** agents / crews / tools.registry / core.pipeline ——
它们会拉起 crewai，从而让整个 API 层无法在不初始化 LLM 框架时被导入。
"""
from __future__ import annotations

import contextvars
import logging
import threading
import time
from contextvars import ContextVar
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

from fastapi import HTTPException, Request, UploadFile

from core.auth_service import AuthService, SlidingWindowRateLimiter
from core.adaptive_decision_store import AdaptiveDecisionStore
from core.adaptive_state_store import AdaptiveStateStore
from core.agent_config_service import AgentConfigService
from core.assignment_service import AssignmentService
from core.deliberation import DeliberationDecision, DeliberationMode
from core.experiment_service import ExperimentService
from core.file_ticket_service import FileTicketService
from core.material_service import MAX_FILE_BYTES, MaterialService
from db.vector_store import get_store

logger = logging.getLogger(__name__)

__all__ = [
    "MAX_FILE_BYTES",
    "output_dir",
    "_ACTION_LABELS",
    "_AUTH_RATE_LIMITED_PATHS",
    "_EXPENSIVE_PREFIXES",
    "_PUBLIC_PATHS",
    "_adaptive_store",
    "_agent_config_service",
    "_all_api_limiter",
    "_apply_agent_runtime_config",
    "_assignment_service",
    "_auth_limiter",
    "_auth_service",
    "_bearer_token",
    "_client_ip",
    "_ctx_wrap",
    "_current_user",
    "_decision_store",
    "_experiment_service",
    "_file_tickets",
    "_llm_limiter",
    "_log_future_error",
    "_material_service",
    "_output_owner",
    "_public_error",
    "_read_upload_limited",
    "_record_output_owner",
    "_record_profile_safely",
    "_report_data_for",
    "_require_teacher",
    "_uid",
]

# ── 服务实例 ────────────────────────────────────────────
#
# 这些是**进程内共享单例**，被多个路由模块使用，因此放在 deps 而不是某个路由
# 文件里。注意：它们（以及限流器、票据服务）都是进程内状态，多 worker 部署下
# 会各持一份；要真正支持多 worker 需要把它们外部化到 Redis/DB。

_auth_service = AuthService()
_file_tickets = FileTicketService()
_material_service = MaterialService()
_assignment_service = AssignmentService()
_adaptive_store = AdaptiveStateStore()
_decision_store = AdaptiveDecisionStore()
_agent_config_service = AgentConfigService()
_experiment_service = ExperimentService()

# ── 限流器 ──────────────────────────────────────────────

_all_api_limiter = SlidingWindowRateLimiter(limit=120, window_seconds=60)
_llm_limiter = SlidingWindowRateLimiter(limit=20, window_seconds=60)
# 认证端点单独限流：登录/注册此前在限流之前就放行了，可被无限撞库与无限注册。
_auth_limiter = SlidingWindowRateLimiter(limit=10, window_seconds=60)
_AUTH_RATE_LIMITED_PATHS = {"/api/auth/login", "/api/auth/register"}

# ── 认证上下文 ──────────────────────────────────────────

_current_user: ContextVar[str | None] = ContextVar("xuece_current_user", default=None)

_PUBLIC_PATHS = {
    "/api/health",
    "/api/auth/login",
    "/api/auth/register",
    "/openapi.json",
    "/docs",
    "/redoc",
}
_EXPENSIVE_PREFIXES = (
    "/api/sessions/",
    "/api/generate",
    "/api/assess/",
    "/api/learning-path/generate",
)

# ── 产物目录与归属 ──────────────────────────────────────

output_dir = Path(__file__).resolve().parent.parent / "runtime" / "output"
output_dir.mkdir(parents=True, exist_ok=True)

# 教学动作标签：原先在 /api/generate 与 /api/adaptive/dashboard 各写一份，容易漂移。
_ACTION_LABELS = {
    "explain": "概念讲解",
    "example": "示例驱动讲解",
    "practice": "基础练习",
    "review": "间隔复习",
    "challenge": "挑战任务",
}


# ── 认证与权限 ──────────────────────────────────────────

def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None
    return None


def _uid(requested: str | None = None) -> str:
    """以认证上下文的用户为准，避免客户端伪造 user_id 访问他人数据。

    绝不能退回共享的 "default"：那个 key 在 kv_store 里是**真实存在**的
    （profile_dashboard_state_default、assessment_default_* 等），于是任何
    没带上认证上下文的请求都会读到同一份数据，表现为"换个账号登录，档案页
    显示的还是别人的薄弱知识点"。这类跨用户串数据在比赛演示时是致命的。

    真正兜底的是请求里显式声明的用户（内部调用/CLI），否则退到 "default"
    仅用于无认证场景（如本地 CLI），HTTP 路径一律由 _current_user 决定。
    """
    current = _current_user.get()
    if current:
        return current
    cleaned = (requested or "").strip()
    # 显式传来的 "default" 视为"没传"：它不可能是某个真实登录用户的 ID
    # （登录用户的 ID 是 uuid4().hex），继续用它只会读到共享那份数据。
    if cleaned and cleaned != "default":
        return cleaned
    return "default"


def _require_teacher(request: Request) -> None:
    user = getattr(request.state, "user", None)
    if user is None or user.role != "teacher":
        raise HTTPException(status_code=403, detail="仅教师账号可使用此功能")


def _client_ip(request: Request) -> str:
    """取调用方来源地址；反向代理下优先用 X-Forwarded-For 的第一段。"""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"


# ── 线程池与错误处理 ────────────────────────────────────

def _ctx_wrap(fn: Callable[[], Any]) -> Callable[[], Any]:
    """把当前请求上下文（认证用户等）带进线程池。

    run_in_executor 不会复制 contextvars，worker 线程里 _current_user 为空，
    _uid() 会退化成 "default"，跨用户串数据。提交前用 copy_context() 抓取。
    """
    ctx = contextvars.copy_context()

    def _runner():
        return ctx.run(fn)

    return _runner


def _log_future_error(fut) -> None:
    """取回线程池任务的异常，避免 "exception was never retrieved" 静默丢失。"""
    if fut.cancelled():
        return
    exc = fut.exception()
    if exc is not None:
        logger.error("后台任务异常: %s", exc, exc_info=exc)


def _record_profile_safely(user_id: str, action: str, write: Callable[[], Any]) -> None:
    """画像写入失败不应打断用户请求，但必须留下日志。

    原先四处都是 `except Exception: pass`，画像与自适应状态可以静默停止更新，
    运维侧完全没有信号。
    """
    try:
        write()
    except Exception:
        logger.warning("画像写入失败 user=%s action=%s", user_id, action, exc_info=True)


def _public_error(exc: Exception, fallback: str) -> str:
    """对外错误文案：不回吐内部异常细节与路径。"""
    logger.warning("请求处理失败，对外返回通用提示: %s", exc, exc_info=True)
    return fallback


# ── 学习报告数据（短 TTL 缓存） ─────────────────────────
#
# 仪表盘会连续调用 /api/reports/{summary,charts,suggestions}，旧实现每个接口都
# 完整重建一遍，同一份数据在一次页面加载里被算 3 次。放在 deps 是因为 3 个报表
# 路由都要用它，留在 main 会导致路由模块反向导入 main。

_REPORT_CACHE_TTL_SECONDS = 10.0
_REPORT_CACHE_MAX_ENTRIES = 256
_report_cache: dict[str, tuple[float, Any]] = {}
_report_cache_lock = threading.RLock()


def _report_data_for(user_id: str):
    """构建学习报告数据（带短 TTL 缓存，按用户区分）。"""
    now = time.monotonic()
    with _report_cache_lock:
        cached = _report_cache.get(user_id)
        if cached is not None and now - cached[0] < _REPORT_CACHE_TTL_SECONDS:
            return cached[1]

    from core.report_builder import ReportBuilder
    data = ReportBuilder(user_id).build()

    with _report_cache_lock:
        if len(_report_cache) >= _REPORT_CACHE_MAX_ENTRIES:
            # 先清理过期项，避免这个字典像限流器那样无界增长。
            for key in [k for k, (ts, _) in _report_cache.items()
                        if now - ts >= _REPORT_CACHE_TTL_SECONDS]:
                del _report_cache[key]
        _report_cache[user_id] = (now, data)
    return data


# ── 上传 ────────────────────────────────────────────────

async def _read_upload_limited(
    request: Request, file: UploadFile, limit: int = MAX_FILE_BYTES
) -> bytes:
    """边读边判上限，避免在大小校验发生之前就把整个请求体读进内存。

    MaterialService.add_material 里确实有 20MB 校验，但它在 `await file.read()`
    之后才生效——那时请求体已经完整驻留内存了，超大上传仍能打爆内存。
    """
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limit:
        raise HTTPException(
            status_code=413, detail=f"文件超过 {limit // (1024 * 1024)} MB 上限"
        )
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HTTPException(
                status_code=413, detail=f"文件超过 {limit // (1024 * 1024)} MB 上限"
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _record_output_owner(user_id: str, filename: str) -> None:
    """登记生成产物的归属，供下载票据做越权校验。

    仅凭文件名无法判断归属：生成成功时把「文件名 → 用户」写进 KV 存储。
    """
    name = Path(filename or "").name
    if not name:
        return
    try:
        get_store().save_data(f"output_owner:{name}", {"user_id": user_id})
    except Exception:
        logger.warning("记录产物归属失败 file=%s user=%s", name, user_id, exc_info=True)


def _output_owner(filename: str) -> str | None:
    """查询产物归属；无记录返回 None。"""
    name = Path(filename or "").name
    if not name:
        return None
    try:
        data = get_store().get_data(f"output_owner:{name}")
    except Exception:
        logger.warning("读取产物归属失败 file=%s", name, exc_info=True)
        return None
    if isinstance(data, dict):
        owner = data.get("user_id")
        return str(owner) if owner else None
    return None


# ── 实验配置 ────────────────────────────────────────────

def _apply_agent_runtime_config(
    decision: DeliberationDecision, config: dict
) -> DeliberationDecision:
    """把实验开关应用到协商路由结果。"""
    mode = decision.mode
    max_rounds = min(decision.max_rounds, int(config.get("max_rounds", 2)))
    reasons = list(decision.reasons)

    if config.get("orchestration_mode") == "single_agent" or not config.get("reviewer_enabled", True):
        mode = DeliberationMode.FAST
        max_rounds = 0
        reasons.append("实验配置已关闭审核或启用单 Agent 模式")
    elif not config.get("critic_enabled", True) and mode == DeliberationMode.DELIBERATE:
        mode = DeliberationMode.STANDARD
        max_rounds = min(max_rounds, 1)
        reasons.append("实验配置已关闭质疑 Agent，降级为标准审核")

    return replace(decision, mode=mode, max_rounds=max_rounds, reasons=tuple(reasons))
