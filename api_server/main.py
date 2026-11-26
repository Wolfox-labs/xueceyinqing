"""
学策引擎 API Server - FastAPI backend for the adaptive learning system.
"""
# 最早安装：@app.on_event / lifespan 里才会拉起 crewai。
# 不装的话，在"配置目录不可写"的 Windows 机器上，后端会卡在启动阶段
# 几十分钟不 bind 端口（一键脚本因此打不开系统）。详见 core/crewai_compat.py。
from core.crewai_compat import install as _install_crewai_compat

_install_crewai_compat()

import json
import asyncio
import logging
import os
import re
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse

from api_server.deps import (
    _ACTION_LABELS,
    _AUTH_RATE_LIMITED_PATHS,
    _EXPENSIVE_PREFIXES,
    _PUBLIC_PATHS,
    _all_api_limiter,
    _apply_agent_runtime_config,
    _auth_limiter,
    _auth_service,
    _bearer_token,
    _client_ip,
    _ctx_wrap,
    _current_user,
    _llm_limiter,
    _log_future_error,
    _public_error,
    _record_output_owner,
    _record_profile_safely,
    _require_teacher,
    _uid,
)
from core import MemoryManager, SessionManager
from core.adaptive_engine import AdaptiveLearningEngine, ContextualUCBPolicy, KnowledgeNode, MasteryState
from core.assessment_service import AssessmentService
from core.parsing import parse_resource, _parse_path_nodes, validate_resource_format
from core.runner import PipelineResult, extract_token_usage
from core.deliberation import AdaptiveDeliberationRouter, DeliberationMode, DeliberationResult
from core.deliberation_service import DeliberationService
from core.agent_trace import agent_trigger_rules, public_summary
from core.adaptive_simulation_service import AdaptiveSimulationService
from core.profile_service import ProfileService
from core.material_service import MaterialService
from core.assignment_service import AssignmentService
from core.adaptive_state_store import AdaptiveStateStore
from core.adaptive_decision_store import AdaptiveDecisionStore
from core.adaptive_graph import build_graph, load_hint_aliases, match_terms
from core.agent_config_service import AgentConfigService
from core.experiment_service import ExperimentService
from core.learning_time_service import LearningTimeService  # adaptive_dashboard 使用
from core.vision_ocr import vision_available  # /api/health 如实报告图片识别是否就绪
from db.vector_store import get_store, init_knowledge_base

# 导入策略（重要）：
#   agents / crews.* / tools.registry / core.pipeline 在导入时都会拉起 crewai。
#   把它们的导入放在模块级，会让**整个 API 层**无法在不初始化 LLM 框架的情况下
#   被导入——健康检查、认证、资料、报表这些端点本不需要它，测试也因此跑不起来。
#   现在统一改为在真正用到它们的地方局部导入（见各处理函数内的 "局部导入" 注释）。
#   这不会改变运行时行为：Python 会缓存已导入的模块。
from schemas import AssessmentResult, LearningPath
from schemas.adaptive import (
    AdaptiveEvidenceRequest,
    AdaptiveSimulationRequest,
    AdaptiveRecommendRequest,
    PolicySelectRequest,
    PolicyUpdateRequest,
)
from schemas.experiment import AblationRunRequest, AgentRuntimeConfigUpdate, ResourceFeedbackRequest
from schemas.assessment import AssessGenerateRequest, AssessSubmitRequest, AssessGenerateResponse
from schemas.api_responses import (
    HealthResponse,
    LearningPathResponse,
    MessageResponse,
    ProfileResponse,
    SessionResponse,
)
from schemas.profile import StudentProfile
from schemas.profile_dashboard import ProfileDashboardResponse


# ── Request models ──────────────────────────────────────
#
# 请求模型已迁到 schemas/requests.py：路由拆到 api_server/routers/*.py 后，
# 若模型留在本文件，子路由就得反向导入 main（循环依赖）。
from schemas.requests import (  # noqa: E402
    CreateSessionRequest,
    GenerateRequest,
    LearningPathGenerateRequest,
    UpdateNodeResourceRequest,
    UpdateNodeStatusRequest,
)


# ── Helper ──────────────────────────────────────────────

def _clean_learning_response(text: str) -> str:
    """移除工具调用前的说明和查询 JSON，仅保留教学回答。"""
    stripped = text.lstrip()
    brace = stripped.find("{")
    if brace >= 0:
        try:
            payload, end = json.JSONDecoder().raw_decode(stripped[brace:])
        except json.JSONDecodeError:
            payload = None
            end = 0
        if isinstance(payload, dict) and ("query" in payload or "profile_text" in payload):
            return stripped[brace + end:].lstrip()

    lines = stripped.splitlines()
    while lines and lines[0].strip().lower().startswith(("i'll ", "i will ", "we'll ", "let me ")):
        lines.pop(0)
    return "\n".join(lines).lstrip()


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r'(?<=[。.！!？?\n])', text)
    return [p for p in parts if p.strip()]


# _uid / _ctx_wrap / _log_future_error / _record_profile_safely / _public_error /
# _require_teacher / _bearer_token / _client_ip / _read_upload_limited /
# 产物归属 / 限流器 / 认证上下文 / output_dir / _ACTION_LABELS
# 均已迁移到 api_server/deps.py（见文件头导入），此处不再重复定义。


# 报告数据构建（含短 TTL 缓存）已迁到 api_server/deps.py 的 _report_data_for：
# 三个报表路由拆到 routers/reports.py 后都需要它，留在 main 会造成反向导入。

# 消融实验的并发与规模护栏：每次运行都真实调用大模型。
_ABLATION_MAX_CONCURRENT = 2
_ABLATION_MAX_TOTAL_RUNS = 60
_ablation_slots = threading.BoundedSemaphore(_ABLATION_MAX_CONCURRENT)


def _execute_ablation_with_slot(*args) -> None:
    """包一层以保证**并发槽位必定释放**（执行体内部吞掉异常也不影响释放）。"""
    try:
        _execute_ablation(*args)
    finally:
        _ablation_slots.release()


_ABLATION_VARIANTS = {
    "full_system": {
        "profile_enabled": True,
        "critic_enabled": True,
        "reviewer_enabled": True,
        "quiz_agent_enabled": True,
        "orchestration_mode": "multi_agent",
    },
    "no_critic": {
        "profile_enabled": True,
        "critic_enabled": False,
        "reviewer_enabled": True,
        "quiz_agent_enabled": True,
        "orchestration_mode": "multi_agent",
    },
    "no_reviewer": {
        "profile_enabled": True,
        "critic_enabled": True,
        "reviewer_enabled": False,
        "quiz_agent_enabled": True,
        "orchestration_mode": "multi_agent",
    },
    "no_profile": {
        "profile_enabled": False,
        "critic_enabled": True,
        "reviewer_enabled": True,
        "quiz_agent_enabled": True,
        "orchestration_mode": "multi_agent",
    },
    "no_quiz_agent": {
        "profile_enabled": True,
        "critic_enabled": True,
        "reviewer_enabled": True,
        "quiz_agent_enabled": False,
        "orchestration_mode": "multi_agent",
    },
    "single_agent": {
        "profile_enabled": True,
        "critic_enabled": False,
        "reviewer_enabled": False,
        "quiz_agent_enabled": False,
        "orchestration_mode": "single_agent",
    },
}


def _run_ablation_resource(user_id: str, variant: str, topic: str, task_type: str, dry_run: bool) -> dict:
    config = _ABLATION_VARIANTS.get(variant)
    if config is None:
        raise ValueError(f"未知实验组：{variant}")
    if dry_run:
        trace = ["profile_context"] if config["profile_enabled"] else []
        trace.append("quiz_agent" if task_type == "exercise" and config["quiz_agent_enabled"] else "teacher_agent")
        if config["reviewer_enabled"] and config["orchestration_mode"] == "multi_agent":
            trace.append("reviewer_agent")
        # dry-run 只验证编排配置、不产生真实产物，必须与真实结果可区分：
        # 否则"格式通过率 / 时延 / token"这些指标会被 0 时延的假数据污染。
        return {
            "status": "dry_run",
            "output_text": f"[dry-run] {variant} / {topic}",
            "latency_ms": None,
            "estimated_tokens": None,
            "format_pass": None,
            "withdrawn": False,
            "agent_trace": trace,
        }

    profile_text = ""
    if config["profile_enabled"]:
        try:
            profile_text = MemoryManager(user_id).get_profile_text()
        except Exception:
            # 静默降级为空会让消融结论失真（no_profile 与"读取失败"无法区分）。
            logger.warning("消融实验读取画像失败 user=%s", user_id, exc_info=True)
            profile_text = ""

    # 局部导入：agents / crews / tools.registry 会拉起 crewai（见文件头导入策略）。
    from agents import create_agents
    from crews.generate import build_gen_crew
    from tools.registry import get_tools

    _, teacher, reviewer = create_agents(user_id)
    single_agent = config["orchestration_mode"] == "single_agent"
    use_quiz_agent = task_type == "exercise" and config["quiz_agent_enabled"] and not single_agent
    enable_reviewer = config["reviewer_enabled"] and not single_agent
    crew = build_gen_crew(
        teacher,
        reviewer,
        task_type,
        topic,
        context=profile_text,
        tools=get_tools(user_id, resource_type=task_type),
        user_id=user_id,
        use_quiz_agent=use_quiz_agent,
        enable_reviewer=enable_reviewer,
    )
    started = time.perf_counter()
    result = CrewPipeline(reviewer).execute(crew)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    raw = result.raw or ""
    trace = ["profile_context"] if config["profile_enabled"] else []
    trace.append("quiz_agent" if use_quiz_agent else "teacher_agent")
    if enable_reviewer:
        trace.append("reviewer_agent")
    # 优先使用 CrewAI 上报的真实 token 用量，取不到才回退字符估算。
    measured_tokens = extract_token_usage(getattr(result, "metrics", None))
    estimated_tokens = (
        measured_tokens
        if measured_tokens is not None
        else max(1, (len(profile_text) + len(raw) + len(topic)) // 4)
    )
    # format_pass 必须真实校验资源格式；旧实现只判断 raw 非空，
    # 等于把任何一段文本（包括审核判词）都算成格式通过。
    format_pass = (
        bool(raw.strip())
        and not result.withdrawn
        and validate_resource_format(task_type, raw)
    )
    return {
        "status": "completed",
        "output_text": raw,
        "latency_ms": elapsed_ms,
        "estimated_tokens": estimated_tokens,
        "format_pass": format_pass,
        "withdrawn": bool(result.withdrawn),
        "agent_trace": trace,
        "error": result.reason if result.withdrawn else "",
    }


def _execute_ablation(
    experiment_id: str,
    user_id: str,
    variants: list[str],
    topics: list[str],
    repetitions: int,
    task_type: str,
    dry_run: bool,
) -> None:
    try:
        _experiment_service.update_status(experiment_id, "running")
        for variant in variants:
            for topic in topics:
                for repetition in range(1, repetitions + 1):
                    try:
                        result = _run_ablation_resource(user_id, variant, topic, task_type, dry_run)
                        _experiment_service.add_run(
                            experiment_id,
                            variant=variant,
                            topic=topic,
                            repetition=repetition,
                            status=result.pop("status", "completed"),
                            **result,
                        )
                    except Exception as exc:
                        _experiment_service.add_run(
                            experiment_id,
                            variant=variant,
                            topic=topic,
                            repetition=repetition,
                            status="failed",
                            error=str(exc),
                        )
                    finally:
                        _experiment_service.increment_completed(experiment_id)
        _experiment_service.update_status(
            experiment_id,
            "completed",
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as exc:
        _experiment_service.update_status(experiment_id, "failed", error=str(exc))

# ── Lifespan — initialize agents and knowledge base ─────

_profile_agent = None
_teacher = None
_reviewer = None
_store = None
_deliberation_router = AdaptiveDeliberationRouter()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("xuece.api")
_material_service = MaterialService()
_assignment_service = AssignmentService()
_adaptive_store = AdaptiveStateStore()
_decision_store = AdaptiveDecisionStore()
_agent_config_service = AgentConfigService()
_experiment_service = ExperimentService()
# _auth_service / _file_tickets / 限流器 / _current_user / _client_ip /
# _PUBLIC_PATHS / _EXPENSIVE_PREFIXES / output_dir 均来自 api_server.deps。


# ── 启动引导：AI 引擎在后台线程加载，绝不阻塞端口绑定 ──────────
#
# 曾经的写法是在 lifespan 里同步 `create_agents("default")`。而 uvicorn 只有在
# lifespan 跑完之后才 bind 端口，于是"AI 引擎加载慢"会直接表现为"后端根本没
# 起来"：一键脚本等 90 秒也等不到 8001，浏览器打开的是打不开的页面。
# 现在改成：后台线程加载 + 限时等待，超时就先把服务放出去，加载完成后自动补上。
_AGENT_BOOTSTRAP_TIMEOUT = float(os.getenv("AGENT_BOOTSTRAP_TIMEOUT", "45"))

#: AI 引擎状态，供 /api/health 如实上报；前端据此给出准确提示。
_agent_status: dict[str, str] = {
    "state": "pending",
    "detail": "AI 引擎尚未开始加载",
}


def _bootstrap_ai_engine():
    """初始化知识库并创建常驻 Agent；返回 (agents, store)。"""
    print("[API] Initializing knowledge base...", flush=True)
    init_knowledge_base()

    print("[API] Loading agents...", flush=True)
    from agents import create_agents  # 局部导入：会拉起 crewai（已装兼容补丁）
    agents = create_agents("default")
    print("[API] Agents ready.", flush=True)
    return agents, get_store()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _profile_agent, _teacher, _reviewer, _store

    def _apply_agents(fut) -> None:
        global _profile_agent, _teacher, _reviewer, _store
        try:
            agents, store = fut.result()
        except Exception as exc:  # noqa: BLE001 - 启动失败必须如实记录并继续服务
            _agent_status.update(state="error", detail=_public_error(exc, "AI 引擎加载失败"))
            logger.exception("AI 引擎加载失败")
            return
        _profile_agent, _teacher, _reviewer = agents
        _store = store
        _agent_status.update(state="ready", detail="AI 引擎已就绪")
        print("[API] AI 引擎就绪（后台加载完成）", flush=True)

    loop = asyncio.get_running_loop()
    fut = loop.run_in_executor(None, _bootstrap_ai_engine)
    fut.add_done_callback(_apply_agents)
    try:
        # shield：超时只放弃等待，不取消后台加载——加载慢时最终仍会就绪。
        await asyncio.wait_for(asyncio.shield(fut), timeout=_AGENT_BOOTSTRAP_TIMEOUT)
    except asyncio.TimeoutError:
        _agent_status.update(
            state="loading",
            detail=f"AI 引擎加载较慢（已超过 {_AGENT_BOOTSTRAP_TIMEOUT:.0f} 秒），后台仍在加载",
        )
        logger.warning(
            "AI 引擎加载超过 %.0f 秒，先放行服务启动（端口已可用）",
            _AGENT_BOOTSTRAP_TIMEOUT,
        )
    except Exception as exc:  # noqa: BLE001 - 已在回调里记录，这里只保证服务能起来
        _agent_status.update(state="error", detail=_public_error(exc, "AI 引擎加载失败"))

    yield


app = FastAPI(title="学策引擎 API Server", version="1.0.0", lifespan=lifespan)

# 业务路由按域拆在 api_server/routers/*.py，这里统一挂载。
# 每个子模块只依赖 api_server/deps.py，不反向导入本文件。
from api_server.routers import ROUTERS  # noqa: E402  （需在 app 定义之后导入）

for _router in ROUTERS:
    app.include_router(_router)

_cors_origins = [
    item.strip()
    for item in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if item.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def auth_and_rate_limit(request: Request, call_next):
    """认证、用户上下文和基础限流；健康检查保持公开。"""
    path = request.url.path

    # 认证端点必须在放行公开路径之前限流（旧实现的顺序让登录/注册完全不受限）。
    if request.method != "OPTIONS" and path in _AUTH_RATE_LIMITED_PATHS:
        if not _auth_limiter.allow(f"auth:{_client_ip(request)}"):
            return JSONResponse(status_code=429, content={"detail": "尝试过于频繁，请稍后再试"})

    if (
        request.method == "OPTIONS"
        or path in _PUBLIC_PATHS
        or path.startswith(("/docs", "/redoc"))
        or path.startswith("/api/files/download/")
    ):
        return await call_next(request)

    token = _bearer_token(request)
    if token:
        # 认证要走 SQLite（一次连接 + JOIN 查询）。直接在事件循环上做会让所有
        # 并发请求在这条查询上串行化，因此放到线程池里执行。
        # token 为空时 authenticate 立即返回 None，无需占用线程。
        loop = asyncio.get_running_loop()
        user = await loop.run_in_executor(None, _auth_service.authenticate, token)
    else:
        user = None
    if user is None:
        return JSONResponse(status_code=401, content={"detail": "未登录或登录已过期"})

    if path.startswith("/api/"):
        if not _all_api_limiter.allow(f"all:{user.user_id}"):
            return JSONResponse(status_code=429, content={"detail": "请求过于频繁，请稍后再试"})
        if path.startswith(_EXPENSIVE_PREFIXES) and not _llm_limiter.allow(f"llm:{user.user_id}"):
            return JSONResponse(status_code=429, content={"detail": "模型调用频率过高，请稍后再试"})

    context_token = _current_user.set(user.user_id)
    request.state.user = user
    try:
        response = await call_next(request)
        logger.info("%s %s user=%s status=%s", request.method, path, user.user_id, response.status_code)
        return response
    finally:
        _current_user.reset(context_token)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error: %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


# output_dir / _record_output_owner / _output_owner 已迁移到 api_server/deps.py。
#
# 注意：这里曾经 app.mount("/output", StaticFiles(...))。output 目录是全体用户
# 共用的，任何已认证用户都能按路径取到别人的产物；前端也并不使用该挂载
# （下载走 /api/files/ticket 的归属校验流程），因此移除。


# ═════════════════════════════════════════════════════════
#  Health
# ═════════════════════════════════════════════════════════

@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "crewai_ready": _profile_agent is not None,
        "image_recognition_ready": vision_available(),
        "ai_engine_state": _agent_status["state"],
        "ai_engine_detail": _agent_status["detail"],
    }


@app.get("/api/agents/trigger-rules")
async def get_agent_trigger_rules():
    """已登录学习者可查看触发规则；修改配置仍仅限教师。"""
    return agent_trigger_rules(_agent_config_service.get())


# ═════════════════════════════════════════════════════════
#  Authentication / Activity  →  api_server/routers/auth.py
#  Materials                  →  api_server/routers/materials.py
#  Teacher / Assignments      →  api_server/routers/teacher.py
#  Secure Output Download     →  api_server/routers/files.py
#  以上路由已拆出，由文件末尾的 include_router 挂载。
# ═════════════════════════════════════════════════════════


# ═════════════════════════════════════════════════════════
#  Session APIs
# ═════════════════════════════════════════════════════════

@app.post("/api/sessions", response_model=SessionResponse)
async def create_session(req: CreateSessionRequest):
    session = SessionManager()
    session.create()
    return SessionResponse(
        id=session.session_id,
        title="新对话",
        updated_at=datetime.now().isoformat(),
    )


@app.get("/api/sessions", response_model=list[SessionResponse])
async def list_sessions(user_id: str = "default"):
    user_id = _uid(user_id)
    store = get_store()
    sessions = store.list_sessions(user_id)
    return [
        SessionResponse(
            id=s["id"],
            title=s["title"],
            updated_at=s.get("updatedAt", ""),
        )
        for s in sessions
    ]


@app.get("/api/sessions/{session_id}/messages", response_model=list[MessageResponse])
async def get_messages(session_id: str, user_id: str = "default"):
    user_id = _uid(user_id)
    memory = MemoryManager(user_id)
    return memory.get_messages(session_id)


@app.get("/api/sessions/{session_id}/messages/stream")
async def stream_messages(
    session_id: str,
    question: str = Query(...),
    user_id: str = "default",
    simulation_id: str | None = Query(None),
):
    user_id = _uid(user_id)
    memory = MemoryManager(user_id)
    current_turn = memory.get_next_turn(session_id)
    ctx = memory.get_context(session_id, current_turn)

    async def event_generator():
        q: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_event_loop()

        status_started: dict[str, float] = {}
        active_statuses: dict[str, dict] = {}
        turn_trigger_rules: dict = {}

        def emit_status_payload(payload: dict):
            payload = dict(payload)
            stage = payload.get("stage", "")
            if stage == "route":
                payload["trigger_rules"] = dict(turn_trigger_rules)
            if payload.get("state") == "running":
                status_started.setdefault(stage, time.monotonic())
                active_statuses[stage] = payload
            elif stage in status_started:
                payload["elapsed_ms"] = round((time.monotonic() - status_started[stage]) * 1000)
            if payload.get("state") != "running":
                active_statuses.pop(stage, None)
            loop.call_soon_threadsafe(q.put_nowait, {"type": "status", **payload})

        def emit_status(stage: str, label: str, detail: str,
                        state: str = "completed", mode: str = "",
                        summary: list[str] | None = None, handoff: str = ""):
            emit_status_payload({
                "stage": stage,
                "label": label,
                "detail": detail,
                "state": state,
                "mode": mode,
                "summary": summary or [detail],
                "handoff": handoff,
            })

        def run_deliberation():
            fallback_mode = DeliberationMode.FAST
            try:
                # 局部导入：agents / crews.ask / tools.registry 会拉起 crewai。
                from agents import create_deliberation_agents
                from crews.ask import build_profile_crew
                from tools.registry import get_tools

                agent_config = _agent_config_service.get()
                turn_trigger_rules.update(agent_trigger_rules(agent_config))
                profile_agent, teacher, reviewer, critic = create_deliberation_agents(user_id)
                tools = get_tools(user_id)
                if agent_config.get("profile_enabled", True):
                    emit_status("profile", "画像 Agent 分析", "正在更新学习者画像", "running")
                    profile_result = build_profile_crew(profile_agent, question, ctx).kickoff()
                    emit_status("profile", "画像 Agent 分析", "画像已更新", "completed",
                                summary=public_summary(getattr(profile_result, "raw", "")),
                                handoff="向后续教学提供最新的学习者画像。")
                else:
                    emit_status("profile", "画像 Agent 已关闭", "实验配置跳过画像更新", "completed")

                try:
                    profile_text = memory.get_profile_text() if agent_config.get("profile_enabled", True) else ""
                except Exception:
                    logger.warning("读取画像上下文失败，本次按无画像处理 user=%s", user_id, exc_info=True)
                    profile_text = ""

                simulation = AdaptiveSimulationService(user_id).get(simulation_id) if simulation_id else None
                if simulation:
                    adaptive_hint = simulation["hint"]
                    profile_text = f"{profile_text}\n\n[算法实验室虚拟学习者]\n{simulation['profile_text']}"
                else:
                    adaptive_hint = _adaptive_hint_for_question(user_id, question)
                runtime_router = AdaptiveDeliberationRouter(
                    standard_threshold=float(agent_config.get("standard_threshold", 0.24)),
                    deliberate_threshold=float(agent_config.get("deliberate_threshold", 0.68)),
                )
                decision = runtime_router.route(
                    question,
                    profile_text=profile_text,
                    adaptive_hint=adaptive_hint,
                )
                decision = _apply_agent_runtime_config(decision, agent_config)
                fallback_mode = decision.mode

                service = DeliberationService(
                    teacher=teacher,
                    critic=critic,
                    reviewer=reviewer,
                    tools=tools,
                    router=runtime_router,
                )
                result = service.run(
                    question,
                    context=ctx,
                    profile_text=profile_text,
                    adaptive_hint=adaptive_hint,
                    decision=decision,
                    on_status=emit_status_payload,
                )

                if result.withdrawn:
                    loop.call_soon_threadsafe(q.put_nowait, result)
                    return

                cleaned = _clean_learning_response(result.raw)
                if cleaned:
                    memory.save_turn(session_id, current_turn, question, cleaned)
                    _record_profile_safely(
                        user_id, "record_qa",
                        lambda: ProfileService(user_id).record_qa(
                            question,
                            cleaned,
                            knowledge_point=(adaptive_hint or {}).get("knowledge_point"),
                            mode=result.mode.value,
                        ),
                    )
                    loop.call_soon_threadsafe(q.put_nowait, cleaned)
                loop.call_soon_threadsafe(q.put_nowait, result)
            except Exception as exc:
                reason = _public_error(exc, "协商执行失败，请稍后重试")
                for payload in list(active_statuses.values()):
                    emit_status_payload({
                        **payload,
                        "state": "error",
                        "detail": "此阶段执行中断",
                        "summary": [reason],
                        "handoff": "本次协商已停止，可稍后重试。",
                    })
                loop.call_soon_threadsafe(
                    q.put_nowait,
                    DeliberationResult(
                        raw="",
                        mode=fallback_mode,
                        withdrawn=True,
                        reason=reason,
                    ),
                )

        loop.run_in_executor(None, _ctx_wrap(run_deliberation))

        while True:
            chunk = await q.get()
            if isinstance(chunk, dict) and chunk.get("type") == "status":
                payload = {k: v for k, v in chunk.items() if k != "type"}
                yield f"event: status\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                continue
            if isinstance(chunk, DeliberationResult):
                if chunk.withdrawn:
                    yield f"event: chunk\ndata: {json.dumps({'content': f'内容已被审核撤回：{chunk.reason}'}, ensure_ascii=False)}\n\n"
                break
            for sentence in _split_sentences(str(chunk)):
                yield f"event: chunk\ndata: {json.dumps({'content': sentence}, ensure_ascii=False)}\n\n"

        yield f"event: done\ndata: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ═════════════════════════════════════════════════════════
#  Generate API
# ═════════════════════════════════════════════════════════

@app.get("/api/generate/ppt-themes")
async def get_ppt_themes():
    """返回 PPT 主题列表，供生成页展示和选择。"""
    from tools.ppt_themes import list_themes
    return {"themes": list_themes()}


@app.post("/api/generate")
async def generate_resource(req: GenerateRequest):
    user_id = _uid(req.user_id)

    async def event_generator():
        q: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_event_loop()
        agent_config = _agent_config_service.get()
        single_agent = agent_config.get("orchestration_mode") == "single_agent"
        use_quiz_agent = bool(agent_config.get("quiz_agent_enabled", True)) and not single_agent
        enable_reviewer = bool(agent_config.get("reviewer_enabled", True)) and not single_agent
        strategy_action = ""
        strategy_action_label = ""
        agent_trace = []
        if agent_config.get("profile_enabled", True):
            agent_trace.append("画像与学习状态")
        agent_trace.append("出题 Agent" if use_quiz_agent else "教学 Agent")
        if enable_reviewer:
            agent_trace.append("审核 Agent")

        material_context, material_sources = _material_service.build_context(
            user_id, req.material_ids, req.topic
        )
        states, _, policy = _adaptive_snapshot(user_id)
        recommendations = _adaptive_recommendations(user_id, limit=1)
        strategy_context = ""
        if states and recommendations:
            top = recommendations[0]
            context_key = policy.context_key(
                mastery=top.effective_mastery,
                urgency=top.priority,
                learning_style=_learning_style_for(user_id),
            )
            action = policy.select(
                context_key,
                ["explain", "example", "practice", "review", "challenge"],
            )
            action_labels = _ACTION_LABELS
            strategy_action = action
            strategy_action_label = action_labels.get(action, action)
            strategy_context = (
                f"[自适应教学策略]\n"
                f"知识点：{top.knowledge_point}\n"
                f"建议策略：{action_labels.get(action, action)}\n"
                f"选择依据：有效掌握度 {top.effective_mastery:.2f}，"
                f"遗忘风险 {top.forgetting_risk:.2f}，优先级 {top.priority:.2f}。\n\n"
            )
            _decision_store.save(
                user_id,
                "resource_generate",
                knowledge_point=top.knowledge_point,
                mastery=top.effective_mastery,
                forgetting=top.forgetting_risk,
                urgency=top.priority,
                selected_action=action,
                related_id=req.topic,
                details={
                    # context 必须落盘：奖励归因要回查"真正交付过的 (context, action)"，
                    # 缺了它 /api/feedback/resource 里的 policy.update 永远不会执行。
                    "context": context_key,
                    "action": action,
                    "resource_type": req.type,
                    "material_ids": req.material_ids,
                    "material_count": len(material_sources),
                },
            )
        full_context = strategy_context + material_context

        def run_crew():
            def on_chunk(text: str):
                loop.call_soon_threadsafe(q.put_nowait, text)
            try:
                # 局部导入：agents / crews.generate / tools.registry / core.pipeline
                # 都会拉起 crewai，不能在模块级导入（见文件头导入策略）。
                from agents import create_agents
                from core.pipeline import CrewPipeline
                from crews.generate import build_gen_crew
                from tools.registry import get_tools

                _, teacher, reviewer = create_agents(user_id)
                tools = get_tools(user_id, resource_type=req.type)
                crew = build_gen_crew(
                    teacher, reviewer, req.type, req.topic,
                    context=full_context, tools=tools, user_id=user_id, use_quiz_agent=use_quiz_agent, enable_reviewer=enable_reviewer,
                )
                pipeline = CrewPipeline(reviewer)
                result = pipeline.execute(crew, on_chunk=on_chunk)
            except Exception as exc:
                # 必须保证哨兵入队：否则消费端的 `await q.get()` 会永久阻塞，
                # 请求挂死并泄漏连接。此前 create_agents / build_gen_crew /
                # pipeline.execute 任一抛错都会走进这个死局。
                logger.exception("资源生成失败 user=%s type=%s", user_id, req.type)
                result = PipelineResult(
                    raw="",
                    withdrawn=True,
                    reason=_public_error(exc, "生成失败，请稍后重试"),
                )
            loop.call_soon_threadsafe(q.put_nowait, result)  # sentinel: PipelineResult

        fut = loop.run_in_executor(None, _ctx_wrap(run_crew))
        fut.add_done_callback(_log_future_error)

        while True:
            chunk = await q.get()
            if isinstance(chunk, PipelineResult):
                if chunk.withdrawn:
                    # 撤回是一个**独立事件**，不能混进正文流：
                    # 旧做法把它当普通 chunk 塞进内容里，前端只能显示一大段文字，
                    # 用户既看不出"这是被审核拦下的"，也没有重试入口。
                    # 这里把判词原文一并回传，让前端能展示"拦截理由 + 审核意见"。
                    yield (
                        "event: withdrawn\ndata: "
                        + json.dumps(
                            {
                                "reason": chunk.reason or "内容未通过审核",
                                "verdict": chunk.verdict or "",
                                "review": (chunk.review_text or "").strip()[:2000],
                                "agent_trace": agent_trace,
                            },
                            ensure_ascii=False,
                        )
                        + "\n\n"
                    )
                else:
                    try:
                        if req.type == "exercise":
                            result_data = {
                                "content": chunk.raw,
                                "sources": material_sources,
                                "strategy": strategy_action_label,
                                "strategy_action": strategy_action,
                                "agent_trace": agent_trace,
                            }
                        else:
                            parsed = parse_resource(req.type, chunk.raw, ppt_theme=req.theme)
                            result_data = {
                                "content": parsed,
                                "sources": material_sources,
                                "strategy": strategy_action_label,
                                "strategy_action": strategy_action,
                                "agent_trace": agent_trace,
                            }
                            if req.type in ("document", "ppt", "mindmap"):
                                match = re.search(r'文件已生成:\s*(.+?)(?:\r?\n|$)', parsed)
                                if match:
                                    # 只回吐文件名：完整服务端路径属于内部信息，
                                    # 前端也只需要它去换取下载票据。
                                    result_data["filepath"] = Path(match.group(1)).name
                                    # 登记归属：下载票据要据此拒绝跨用户取件。
                                    _record_output_owner(user_id, result_data["filepath"])
                        _record_profile_safely(
                            user_id, "record_resource",
                            lambda: ProfileService(user_id).record_resource(req.type, req.topic),
                        )
                        yield f"event: result\ndata: {json.dumps(result_data, ensure_ascii=False)}\n\n"
                    except Exception as e:
                        yield f"event: chunk\ndata: {json.dumps({'content': _public_error(e, '生成失败，请稍后重试')}, ensure_ascii=False)}\n\n"
                break
            for sentence in _split_sentences(chunk):
                yield f"event: chunk\ndata: {json.dumps({'content': sentence}, ensure_ascii=False)}\n\n"

        yield f"event: done\ndata: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ═════════════════════════════════════════════════════════
#  Profile API
# ═════════════════════════════════════════════════════════

@app.get("/api/profile", response_model=ProfileResponse)
async def get_profile(user_id: str = "default"):
    user_id = _uid(user_id)
    memory = MemoryManager(user_id)
    try:
        profile_text = memory.get_profile_text()
        profile = StudentProfile.from_text(profile_text)
        return ProfileResponse(user_id=user_id, profile=profile)
    except Exception:
        # 原来只抛一句"服务未就绪"：既不记日志，也分不清是解析 bug 还是真宕机。
        logger.exception("读取用户画像失败 user=%s", user_id)
        raise HTTPException(status_code=503, detail="画像服务暂时不可用，请稍后重试")


# ═════════════════════════════════════════════════════════
#  Learning Path APIs
# ═════════════════════════════════════════════════════════

@app.get("/api/profile/dashboard", response_model=ProfileDashboardResponse)
async def get_profile_dashboard(request: Request, user_id: str = "default"):
    """返回结构化数字画像、证据来源和动态更新记录。"""
    user_id = _uid(user_id)
    try:
        dashboard = ProfileService(user_id).build_dashboard()
        # 展示名用登录用户名，而不是 uuid4 十六进制。
        # ProfileService 只认 user_id、拿不到用户名，所以在这里补上。
        # 前端仍会在为空时回退到本地会话里的名字，双保险。
        auth_user = getattr(request.state, "user", None)
        username = getattr(auth_user, "username", "") or ""
        if username and isinstance(dashboard.identity, dict):
            # identity 是 dict（见 schemas/profile_dashboard.py 的 `identity: dict`），
            # 不是 pydantic 子模型，必须按下标赋值。
            dashboard.identity["display_name"] = username
        return dashboard
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=_public_error(exc, "档案聚合服务暂时不可用，请稍后重试"),
        ) from exc


@app.get("/api/learning-path", response_model=LearningPathResponse)
async def get_learning_path(user_id: str = "default"):
    user_id = _uid(user_id)
    memory = MemoryManager(user_id)
    path = memory.get_path()
    if path:
        return path
    return []


@app.post("/api/learning-path/generate")
async def generate_learning_path(req: LearningPathGenerateRequest):
    user_id = _uid(req.user_id)

    async def event_generator():
        memory = MemoryManager(user_id)
        try:
            profile_text = memory.get_profile_text()
        except Exception:
            logger.warning("读取画像上下文失败，本次按无画像处理 user=%s", user_id, exc_info=True)
            profile_text = ""

        def _build_and_run():
            # 局部导入：agents / crews.path / tools.registry / core.pipeline 会拉起 crewai。
            # 建 Agent 与建 Crew 都是阻塞调用，一并放进线程池，避免拖住事件循环。
            from agents import create_agents
            from core.pipeline import CrewPipeline
            from crews.path import build_path_crew
            from tools.registry import get_tools

            _, teacher, reviewer = create_agents(user_id)
            crew = build_path_crew(
                teacher, user_id, req.topic, profile_text, tools=get_tools(user_id)
            )
            return CrewPipeline(reviewer, memory).execute(crew)

        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, _ctx_wrap(_build_and_run))
        except Exception as exc:
            # 这里必须自己收口：异常若冒泡出异步生成器，SSE 会中途断流且不下发 done。
            logger.exception("学习路径生成失败 user=%s", user_id)
            yield f"data: {json.dumps({'error': _public_error(exc, '生成失败，请稍后重试')}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
            return

        if result.withdrawn:
            yield f"data: {json.dumps({'content': f'内容已被审核撤回：{result.reason}'}, ensure_ascii=False)}\n\n"
        else:
            raw_output = result.raw.strip()
            try:
                nodes = _parse_path_nodes(raw_output)
                if not nodes:
                    yield f"data: {json.dumps({'error': '无法解析路径节点', 'raw': result.raw[:500]}, ensure_ascii=False)}\n\n"
                else:
                    path = LearningPath(
                        title=req.topic,
                        topic=req.topic,
                        nodes=nodes,
                        user_id=user_id,
                    )
                    memory = MemoryManager(user_id)
                    memory.save_path(path)
                    _invalidate_adaptive_graph(user_id)
                    _record_profile_safely(
                        user_id, "record_learning_path",
                        lambda: ProfileService(user_id).record_learning_path(path),
                    )
                    yield f"data: {json.dumps(path.model_dump(), ensure_ascii=False)}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': _public_error(e, '解析失败，请稍后重试'), 'raw': result.raw[:500]}, ensure_ascii=False)}\n\n"

        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ═════════════════════════════════════════════════════════
#  Assessment API
# ═════════════════════════════════════════════════════════

@app.post("/api/assess/generate", response_model=AssessGenerateResponse)
async def assess_generate(req: AssessGenerateRequest):
    user_id = _uid(req.user_id)

    def _run():
        # 局部导入（crewai）+ 把建 Agent 放进线程池：它原先在事件循环上阻塞。
        from agents import create_agents
        _, teacher, _ = create_agents(user_id)
        return AssessmentService(user_id, teacher).generate_questions(
            req.topic, req.question_count
        )

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _ctx_wrap(_run))


@app.post("/api/assess/submit", response_model=AssessmentResult)
async def assess_submit(req: AssessSubmitRequest):
    user_id = _uid(req.user_id)
    answers_list = [ans.model_dump() for ans in req.answers]

    def _run():
        # 同上：局部导入 + 阻塞调用移出事件循环。
        from agents import create_agents
        _, teacher, _ = create_agents(user_id)
        return AssessmentService(user_id, teacher).grade(req.assessment_id, answers_list)

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, _ctx_wrap(_run))
    _record_profile_safely(
        user_id, "record_assessment",
        lambda: ProfileService(user_id).record_assessment(result.model_dump()),
    )
    return result


# ═════════════════════════════════════════════════════════
#  Question Bank APIs  →  api_server/routers/question_bank.py
#  （请求模型已移至 schemas/requests.py）
# ═════════════════════════════════════════════════════════



# ═════════════════════════════════════════════════════════
#  Learning Path Node Resource
# ═════════════════════════════════════════════════════════

@app.put("/api/learning-path/{topic}/nodes/{node_id}/resource")
async def update_node_resource(topic: str, node_id: str, req: UpdateNodeResourceRequest,
                                user_id: str = "default"):
    user_id = _uid(user_id)
    memory = MemoryManager(user_id)
    path = memory.get_path(topic)
    if not path:
        raise HTTPException(status_code=404, detail="学习路径不存在")
    if isinstance(path, list):
        raise HTTPException(status_code=404, detail="学习路径不存在")
    for node in path.nodes:
        if node.id == node_id:
            node.resource_type = req.resource_type
            node.resource_ref = req.resource_ref
            path.updated_at = datetime.now().isoformat()
            memory.save_path(path)
            _invalidate_adaptive_graph(user_id)
            return {"status": "ok", "node_id": node_id}
    raise HTTPException(status_code=404, detail="节点不存在")


@app.put("/api/learning-path/{topic}/nodes/{node_id}/status")
async def update_node_status(topic: str, node_id: str, req: UpdateNodeStatusRequest,
                             user_id: str = "default"):
    user_id = _uid(user_id)
    status = (req.status or "").strip()
    if status not in {"pending", "in_progress", "completed"}:
        raise HTTPException(status_code=400, detail="无效的节点状态")
    memory = MemoryManager(user_id)
    path = memory.get_path(topic)
    if not path or isinstance(path, list):
        raise HTTPException(status_code=404, detail="学习路径不存在")
    for node in path.nodes:
        if node.id == node_id:
            node.status = status
            path.updated_at = datetime.now().isoformat()
            memory.save_path(path)
            _invalidate_adaptive_graph(user_id)
            return {"status": "ok", "node_id": node_id, "node_status": status}
    raise HTTPException(status_code=404, detail="节点不存在")


# ═════════════════════════════════════════════════════════
#  Report APIs
# ═════════════════════════════════════════════════════════

# ═════════════════════════════════════════════════════════
#  Report APIs  →  api_server/routers/reports.py
# ═════════════════════════════════════════════════════════

# ═════════════════════════════════════════════════════════
#  Adaptive Learning Engine APIs
# ═════════════════════════════════════════════════════════

_adaptive_engine = AdaptiveLearningEngine(default_half_life_days=14.0)
_adaptive_states_by_user: dict[str, dict[str, MasteryState]] = {}
_adaptive_errors_by_user: dict[str, dict[str, int]] = {}
_adaptive_policies: dict[str, ContextualUCBPolicy] = {}
_adaptive_lock = threading.RLock()

# 知识图谱不再硬编码在这里，见 core/adaptive_graph.py：
#   种子图谱（Python 入门）+ runtime/adaptive_graph.json（使用者自定义）
#   + 该用户真实学习路径推导出的前置依赖边。
_adaptive_graph_cache: dict[str, tuple[float, dict[str, KnowledgeNode]]] = {}
_hint_aliases_cache: dict[str, tuple[float, dict[str, tuple[str, ...]]]] = {}
_ADAPTIVE_GRAPH_TTL_SECONDS = 30.0


def _invalidate_adaptive_graph(user_id: str) -> None:
    """学习路径变化后立即让图谱缓存失效，无需等 TTL。"""
    with _adaptive_lock:
        _adaptive_graph_cache.pop(user_id, None)


def _adaptive_hint_aliases() -> dict[str, tuple[str, ...]]:
    """配置里的手工别名（可选），带 TTL 缓存，避免每次请求都读文件。"""
    now = time.monotonic()
    cached = _hint_aliases_cache.get("_")
    if cached and now - cached[0] < _ADAPTIVE_GRAPH_TTL_SECONDS:
        return cached[1]
    aliases = load_hint_aliases()
    _hint_aliases_cache["_"] = (now, aliases)
    return aliases


def _adaptive_graph_for(user_id: str) -> dict[str, KnowledgeNode]:
    """该用户的知识图谱：配置/种子图谱 + 真实学习路径推导出的依赖边。"""
    now = time.monotonic()
    with _adaptive_lock:
        cached = _adaptive_graph_cache.get(user_id)
        if cached and now - cached[0] < _ADAPTIVE_GRAPH_TTL_SECONDS:
            return cached[1]

    path_nodes = None
    try:
        path = MemoryManager(user_id).get_path()
        path_nodes = getattr(path, "nodes", None)
    except Exception:
        logger.warning("读取学习路径失败 user=%s，仅使用配置/种子图谱", user_id, exc_info=True)

    graph = build_graph(path_nodes)
    with _adaptive_lock:
        _adaptive_graph_cache[user_id] = (now, graph)
    return graph


def _learning_style_for(user_id: str) -> str:
    """取真实画像里的学习偏好。

    原先三处在 context_key 里硬编码 learning_style="reading"，导致 UCB 上下文
    的第三维恒为常数（6 个桶而非 18 个），画像里的偏好从未参与决策。
    未知时返回空串，由 context_key 归入 'unknown' 桶。
    """
    try:
        profile = StudentProfile.from_text(MemoryManager(user_id).get_profile_text())
    except Exception:
        logger.warning("读取学习偏好失败 user=%s", user_id, exc_info=True)
        return ""
    return (profile.learning_style or "").strip()


def _adaptive_policy_for(user_id: str) -> ContextualUCBPolicy:
    with _adaptive_lock:
        return _adaptive_policies.setdefault(user_id, ContextualUCBPolicy(exploration=1.15))


def _seed_adaptive_engine(user_id: str) -> None:
    """为新用户准备空学习状态；真实掌握度只能来自测评或学习证据。"""
    with _adaptive_lock:
        if user_id in _adaptive_states_by_user:
            return
        stored_states, stored_errors = _adaptive_store.load(user_id)
        states: dict[str, MasteryState] = {}
        for row in stored_states:
            last_practiced = datetime.now(timezone.utc)
            if row.get("last_practiced"):
                try:
                    last_practiced = datetime.fromisoformat(row["last_practiced"])
                except ValueError:
                    last_practiced = datetime.now(timezone.utc)
            states[row["knowledge_point"]] = MasteryState(
                knowledge_point=row["knowledge_point"],
                mastery=float(row["mastery"]),
                evidence_count=int(row["evidence_count"]),
                last_practiced=last_practiced,
            )
        _adaptive_states_by_user[user_id] = states
        _adaptive_errors_by_user[user_id] = stored_errors
        _adaptive_policies.setdefault(user_id, ContextualUCBPolicy(exploration=1.15))


def _adaptive_bucket(user_id: str) -> tuple[dict[str, MasteryState], dict[str, int], ContextualUCBPolicy]:
    """返回**活引用**，仅供写入方使用，且必须在 _adaptive_lock 内改动。

    只读路径一律改用 _adaptive_snapshot()：这些字典会被执行线程并发迭代，
    锁外写入会触发 "dictionary changed size during iteration"。
    """
    _seed_adaptive_engine(user_id)
    with _adaptive_lock:
        return (
            _adaptive_states_by_user[user_id],
            _adaptive_errors_by_user[user_id],
            _adaptive_policies[user_id],
        )


def _adaptive_snapshot(user_id: str) -> tuple[dict[str, MasteryState], dict[str, int], ContextualUCBPolicy]:
    """只读路径用的快照：在锁内复制字典，迭代期间不受并发写入影响。"""
    _seed_adaptive_engine(user_id)
    with _adaptive_lock:
        return (
            dict(_adaptive_states_by_user[user_id]),
            dict(_adaptive_errors_by_user[user_id]),
            _adaptive_policies[user_id],
        )


def _adaptive_recommendations(user_id: str, limit: int | None = None):
    states, errors, _ = _adaptive_snapshot(user_id)
    if not states:
        return []
    return _adaptive_engine.recommend(
        states.values(),
        _adaptive_graph_for(user_id),
        recent_errors=errors,
        limit=limit,
    )


def _adaptive_hint_for_question(user_id: str, question: str) -> dict | None:
    """只在与问题明确匹配时注入自适应策略，避免无关知识点污染回答。

    匹配词条一律从知识点名称自身切分（core/adaptive_graph.knowledge_point_terms），
    再叠加配置里的手工别名。原先是一张手写的 Python 术语表，对操作系统、
    计算机网络等真实知识点完全命中不了，自适应提示因此注入不进去。
    """
    states, errors, _ = _adaptive_snapshot(user_id)
    if not states:
        return None
    normalized = re.sub(r"\s+", "", question or "").lower()
    if not normalized:
        return None

    aliases = _adaptive_hint_aliases()
    graph = _adaptive_graph_for(user_id)

    matched = []
    for point, state in states.items():
        terms = match_terms(point, aliases)
        if not any(term.lower() in normalized for term in terms):
            continue
        rows = _adaptive_engine.recommend(
            [state],
            graph,
            recent_errors=errors,
            limit=1,
        )
        if rows:
            matched.append(asdict(rows[0]))

    if not matched:
        return None
    matched.sort(key=lambda row: float(row.get("priority") or 0.0), reverse=True)
    return matched[0]


def _policy_hit_rate(policy: ContextualUCBPolicy) -> float:
    """策略命中率：各上下文里选择动作恰为该上下文经验最优动作的拉动占比。

    原实现算的是"按拉动次数加权的平均奖励"，却命名为命中率；前端按百分比
    展示会误导（它衡量的是奖励水平，不是策略是否选对）。这里给出与名字
    一致的定义：已被拉动的次数中，落在当前经验最优臂上的比例。
    """
    snapshot = policy.snapshot()
    total_pulls = 0
    best_pulls = 0
    for bucket in snapshot.values():
        if not bucket:
            continue
        best_action = max(
            bucket,
            key=lambda action: (bucket[action]["mean_reward"], bucket[action]["pulls"]),
        )
        total_pulls += sum(int(stat["pulls"]) for stat in bucket.values())
        best_pulls += int(bucket[best_action]["pulls"])
    if total_pulls <= 0:
        return 0.0
    return round(best_pulls / total_pulls * 100, 1)


@app.get("/api/adaptive/dashboard")
async def adaptive_dashboard(user_id: str = "default"):
    """返回当前用户的学习驾驶舱算法状态。"""
    user_id = _uid(user_id)
    states, errors, policy = _adaptive_snapshot(user_id)
    learning_summary = LearningTimeService(user_id).summary()
    # 依赖边只存在后端图谱里，前端要画真实的依赖关系就必须拿到它。
    # 顺带修掉一处重复调用：原先它写在 risk_points 的生成式内部，按状态数被调用多次。
    graph = _adaptive_graph_for(user_id)

    def _graph_payload() -> list[dict]:
        """节点 + 前置依赖 + 真实有效掌握度；没有证据的节点 mastery 为 None，不编造。"""
        payload: list[dict] = []
        for node_name, node in graph.items():
            state = states.get(node_name)
            payload.append({
                "name": node_name,
                "importance": round(node.importance, 4),
                "prerequisites": list(node.prerequisites),
                "mastery": (
                    round(_adaptive_engine.effective_mastery(state), 4) if state else None
                ),
            })
        return payload

    if not states:
        return {
            "user_id": user_id,
            "needs_onboarding": True,
            "summary": {
                "mastery": 0.0,
                "study_minutes": learning_summary["today_minutes"],
                "risk_points": 0,
                "policy_hit_rate": 0.0,
            },
            "recommendation": None,
            "recommendations": [],
            "knowledge_states": [],
            "knowledge_graph": _graph_payload(),
            "experiment": [],
            "policy_snapshot": policy.snapshot(),
        }
    recommendations = _adaptive_recommendations(user_id, limit=4)
    average_mastery = sum(
        _adaptive_engine.effective_mastery(state) for state in states.values()
    ) / max(1, len(states))
    risk_points = sum(
        1 for state in states.values()
        if _adaptive_engine.priority_score(
            state,
            importance=graph.get(
                state.knowledge_point,
                KnowledgeNode(state.knowledge_point),
            ).importance,
            recent_errors=errors.get(state.knowledge_point, 0),
        ) >= 0.55
    )
    top = recommendations[0]
    context = policy.context_key(
        mastery=top.effective_mastery,
        urgency=top.priority,
        learning_style=_learning_style_for(user_id),
    )
    action = policy.select(
        context,
        ["explain", "example", "practice", "review", "challenge"],
    )
    action_labels = _ACTION_LABELS
    return {
        "user_id": user_id,
        "needs_onboarding": False,
        "summary": {
            "mastery": round(average_mastery * 100, 1),
            "study_minutes": learning_summary["today_minutes"],
            "risk_points": risk_points,
            "policy_hit_rate": _policy_hit_rate(policy),
        },
        "recommendation": {
            **asdict(top),
            "action": action,
            "action_label": action_labels.get(action, action),
            "context": context,
        },
        "recommendations": [asdict(item) for item in recommendations],
        "knowledge_states": [
            {
                "knowledge_point": state.knowledge_point,
                "stored_mastery": round(state.mastery, 4),
                "effective_mastery": round(_adaptive_engine.effective_mastery(state), 4),
                "evidence_count": state.evidence_count,
                "last_practiced": state.last_practiced.isoformat(),
            }
            for state in states.values()
        ],
        # 这里原先写死三组"掌握增益 / 七天保持率"数字（固定路径 11.8/54、
        # 知识追踪 17.6/68、学策引擎 28.4/82）。问题不只是"用了假数据"，而是
        # **系统从未做过这类测量**：消融实验记录的是耗时、Token、格式通过率与
        # 是否撤回，并不产出 gain / retention。编一组好看的对照比留空更糟，
        # 所以这里返回空数组，由前端如实显示"暂无对照数据"并引导去做真实实验。
        "experiment": [],
        "knowledge_graph": _graph_payload(),
        "policy_snapshot": policy.snapshot(),
    }


@app.post("/api/adaptive/evidence")
async def adaptive_evidence(req: AdaptiveEvidenceRequest):
    """提交答题证据，更新掌握度和当前用户的 UCB 策略。"""
    user_id = _uid()
    states, errors, policy = _adaptive_bucket(user_id)
    # 状态改动必须在锁内完成：这些字典会被执行线程（_adaptive_hint_for_question /
    # _adaptive_recommendations）并发迭代，锁外写入会触发
    # "dictionary changed size during iteration"。落盘 I/O 放到锁外，避免拖住并发写。
    pending: list[tuple[str, float, int, str | None]] = []
    with _adaptive_lock:
        for observation in req.observations:
            state = states.get(observation.knowledge_point)
            if state is None:
                state = MasteryState(knowledge_point=observation.knowledge_point)
                states[observation.knowledge_point] = state
            _adaptive_engine.update_mastery(
                state,
                observation.score,
                observed_at=observation.observed_at,
            )
            pending.append((
                state.knowledge_point,
                state.mastery,
                state.evidence_count,
                state.last_practiced.isoformat() if state.last_practiced else None,
            ))
        errors.update(req.recent_errors)
        errors_snapshot = dict(errors)
        states_view = list(states.values())

    for knowledge_point, mastery, evidence_count, last_practiced in pending:
        _adaptive_store.save_state(
            user_id, knowledge_point, mastery, evidence_count, last_practiced
        )
    _adaptive_store.save_errors(user_id, errors_snapshot)

    recommendations = _adaptive_recommendations(user_id)
    reward = sum(obs.score for obs in req.observations) / max(1, len(req.observations))
    # 奖励必须记到**真正交付给用户**的那个 (context, action) 上。
    # 原实现先更新掌握度、再重算推荐、再 select 一个"此刻会选的动作"并给它记
    # 奖励，等于让策略奖励自己当前的偏好而不是实际教学效果（自我强化）。
    # 改为回查该知识点最近一次资源生成记录；查不到就不训练，只留一条观测。
    policy_update = None
    if recommendations:
        top = recommendations[0]
        delivered = _decision_store.latest_for_knowledge_point(
            user_id, "resource_generate", top.knowledge_point
        )
        served_details = (delivered or {}).get("details") or {}
        served_context = served_details.get("context") or ""
        served_action = (delivered or {}).get("selected_action") or ""

        if served_context and served_action:
            policy.update(served_context, served_action, reward)
            attributed_to = "delivered_resource"
        else:
            attributed_to = "none"

        policy_update = {
            "context": served_context or None,
            "action": served_action or None,
            "reward": round(reward, 4),
            "attributed_to": attributed_to,
            "snapshot": policy.snapshot(),
        }
        if attributed_to == "none":
            policy_update["reason"] = "没有找到该知识点的已交付资源记录，未更新策略"

        _decision_store.save(
            user_id,
            "assessment_evidence",
            knowledge_point=top.knowledge_point,
            mastery=top.effective_mastery,
            forgetting=top.forgetting_risk,
            urgency=top.priority,
            selected_action=served_action,
            reward=round(reward, 4),
            details={
                "context": served_context,
                "observation_count": len(req.observations),
                "attributed_to": attributed_to,
            },
        )

    return {
        "states": [
            {
                "knowledge_point": state.knowledge_point,
                "mastery": round(state.mastery, 4),
                "effective_mastery": round(_adaptive_engine.effective_mastery(state), 4),
                "evidence_count": state.evidence_count,
            }
            for state in states_view
        ],
        "recommendations": [asdict(item) for item in recommendations],
        "policy_update": policy_update,
    }


@app.post("/api/adaptive/simulations")
async def create_adaptive_simulation(req: AdaptiveSimulationRequest):
    return AdaptiveSimulationService(_uid()).create(req.model_dump())


@app.get("/api/adaptive/simulations/{simulation_id}")
async def get_adaptive_simulation(simulation_id: str):
    data = AdaptiveSimulationService(_uid()).get(simulation_id)
    if data is None:
        raise HTTPException(status_code=404, detail="虚拟学习者状态不存在")
    return data


@app.post("/api/adaptive/recommend")
async def adaptive_recommend(req: AdaptiveRecommendRequest):
    """对任意学习者状态集合进行无副作用推荐。"""
    states = [
        MasteryState(
            knowledge_point=item.knowledge_point,
            mastery=item.mastery,
            evidence_count=item.evidence_count,
            last_practiced=item.last_practiced or datetime.now(timezone.utc),
        )
        for item in req.states
    ]
    graph = {
        item.name: KnowledgeNode(
            name=item.name,
            importance=item.importance,
            prerequisites=tuple(item.prerequisites),
        )
        for item in req.graph
    }
    rows = _adaptive_engine.recommend(
        states,
        graph,
        recent_errors=req.recent_errors,
        limit=req.limit,
    )
    return {"recommendations": [asdict(item) for item in rows]}


@app.post("/api/adaptive/policy/select")
async def adaptive_policy_select(req: PolicySelectRequest):
    user_id = _uid()
    policy = _adaptive_policy_for(user_id)
    context = policy.context_key(
        mastery=req.mastery,
        urgency=req.urgency,
        learning_style=req.learning_style,
    )
    action = policy.select(context, req.actions)
    _decision_store.save(
        user_id,
        "policy_select",
        mastery=req.mastery,
        urgency=req.urgency,
        selected_action=action,
        details={"context": context, "actions": req.actions},
    )
    return {"context": context, "action": action, "snapshot": policy.snapshot()}


@app.post("/api/adaptive/policy/update")
async def adaptive_policy_update(req: PolicyUpdateRequest):
    user_id = _uid()
    policy = _adaptive_policy_for(user_id)
    policy.update(req.context, req.action, req.reward)
    _decision_store.save(
        user_id,
        "policy_update",
        selected_action=req.action,
        reward=req.reward,
        details={"context": req.context},
    )
    return {"status": "ok", "snapshot": policy.snapshot()}


@app.get("/api/experiments/agent-config")
async def get_agent_config(request: Request):
    # 与 PUT/reset 保持一致：全局编排开关属于实验配置，不该对学生开放。
    _require_teacher(request)
    return _agent_config_service.get()


@app.put("/api/experiments/agent-config")
async def update_agent_config(req: AgentRuntimeConfigUpdate, request: Request):
    _require_teacher(request)
    try:
        config = _agent_config_service.update(req.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _decision_store.save(
        _uid(),
        "agent_config",
        selected_action=config.get("orchestration_mode", ""),
        details=config,
    )
    return config


@app.post("/api/experiments/agent-config/reset")
async def reset_agent_config(request: Request):
    _require_teacher(request)
    config = _agent_config_service.reset()
    _decision_store.save(
        _uid(),
        "agent_config",
        selected_action="reset",
        details=config,
    )
    return config

@app.post("/api/experiments/ablation")
async def create_ablation_experiment(req: AblationRunRequest, request: Request):
    _require_teacher(request)
    variants = [item for item in req.variants if item in _ABLATION_VARIANTS]
    topics = [item.strip() for item in req.topics if item.strip()]
    if not variants:
        raise HTTPException(status_code=400, detail="没有有效的实验组")
    if not topics:
        raise HTTPException(status_code=400, detail="至少需要一个测试主题")
    total_runs = len(variants) * len(topics) * req.repetitions
    if total_runs > _ABLATION_MAX_TOTAL_RUNS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"单次实验最多 {_ABLATION_MAX_TOTAL_RUNS} 次运行，"
                f"当前组合为 {total_runs} 次（实验组×主题×重复次数）"
            ),
        )
    experiment = _experiment_service.create(
        _uid(),
        req.name.strip(),
        req.task_type,
        variants,
        topics,
        req.repetitions,
    )
    # 并发护栏：每个实验都会起一个线程循环真实调用大模型，不能无限叠加。
    if not _ablation_slots.acquire(blocking=False):
        raise HTTPException(
            status_code=429,
            detail=f"已有 {_ABLATION_MAX_CONCURRENT} 个消融实验在运行，请稍后再试",
        )
    try:
        threading.Thread(
            target=_execute_ablation_with_slot,
            args=(experiment["id"], _uid(), variants, topics, req.repetitions, req.task_type, req.dry_run),
            daemon=True,
        ).start()
    except Exception:
        _ablation_slots.release()
        raise
    return experiment


@app.get("/api/experiments/ablation")
async def list_ablation_experiments(request: Request):
    _require_teacher(request)
    return {"experiments": _experiment_service.list_for_user(_uid())}


@app.get("/api/experiments/ablation/{experiment_id}")
async def get_ablation_experiment(experiment_id: str, request: Request):
    _require_teacher(request)
    item = _experiment_service.get(experiment_id, _uid())
    if item is None:
        raise HTTPException(status_code=404, detail="实验不存在")
    return item


@app.post("/api/feedback/resource")
async def resource_feedback(req: ResourceFeedbackRequest):
    user_id = _uid()
    rating_reward = {
        "helpful": 1.0,
        "neutral": 0.5,
        "not_helpful": 0.0,
    }[req.rating]
    difficulty_bonus = {
        "appropriate": 0.05,
        "too_easy": -0.05,
        "too_hard": -0.10,
    }[req.difficulty]
    reward = max(0.0, min(1.0, rating_reward + difficulty_bonus))
    latest = _decision_store.latest_for_related(user_id, "resource_generate", req.topic)
    if latest:
        context = (latest.get("details") or {}).get("context")
        action = latest.get("selected_action")
        if context and action:
            _adaptive_policy_for(user_id).update(context, action, reward)
    _decision_store.save(
        user_id,
        "student_feedback",
        knowledge_point=(latest or {}).get("knowledge_point", ""),
        selected_action=(latest or {}).get("selected_action", ""),
        reward=reward,
        related_id=req.topic,
        details={
            "rating": req.rating,
            "difficulty": req.difficulty,
            "source_match": req.source_match,
            "resource_type": req.resource_type,
        },
    )
    return {"status": "ok", "reward": reward}

@app.get("/api/adaptive/decisions")
async def adaptive_decisions(limit: int = 50):
    return {"decisions": _decision_store.list_for_user(_uid(), limit)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)














