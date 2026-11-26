"""
core 层 — 项目业务逻辑的统一入口。

模块：
  runner              → CrewRunner           : 流式执行 Crew + 收集结果
  memory              → MemoryManager        : 向后兼容的对话记忆管理
  conversation_memory → ConversationMemory   : 对话压缩 + 上下文注入 + 对话存取
  path_store          → PathStore            : 学习路径存取
  assessment_store    → AssessmentStore      : 评估结果存取
  assessment_service  → AssessmentService    : 评估业务编排（出题 + 评分）
  session             → SessionManager       : 会话生命周期 + 轮次追踪
  pipeline            → CrewPipeline         : 统一执行管线（注入审核上下文、执行、记忆保存）
  deliberation        → AdaptiveDeliberationRouter : 自适应协商路由
  deliberation_service→ DeliberationService  : 有限轮次多智能体协商编排

调用方只需:
  from core import CrewRunner, MemoryManager, SessionManager
  from core import CrewPipeline, PipelineResult
  from core import ConversationMemory, PathStore, AssessmentStore
  from core import AssessmentService
  from core import AdaptiveDeliberationRouter, DeliberationService

导入策略（重要）：
    这里**不再**在导入 core 时立即加载全部子模块。旧实现是 eager import，其中
        core.pipeline            → tools.review_tools     → crewai.tools
        core.deliberation_service→ crews.deliberation     → crewai
        core.assessment_service  → crews.assessment       → crewai
    于是任何一句 `from core import ...`（哪怕只想拿 SessionManager）都会把整个
    LLM 框架拉进来：单元测试无法在不初始化框架的情况下运行、启动变慢、纯逻辑层
    与框架强耦合。

    现改为 PEP 562 的模块级 __getattr__ 惰性导出：
        from core import CrewRunner     # 只加载 core.runner
        from core import CrewPipeline   # 这时才加载 core.pipeline
    行为对调用方完全兼容。
"""
from __future__ import annotations

import importlib
from typing import Any

__all__ = [
    "CrewRunner", "CrewResult",
    "MemoryManager",
    "ConversationMemory", "PathStore", "AssessmentStore",
    "AssessmentService",
    "ReportBuilder", "ReportData",
    "SessionManager",
    "CrewPipeline", "PipelineResult",
    "AdaptiveDeliberationRouter", "DeliberationDecision",
    "DeliberationMode", "DeliberationResult", "DeliberationStep",
    "DeliberationService",
]

# 公开名 → 定义它的子模块
_EXPORTS: dict[str, str] = {
    "CrewRunner": "core.runner",
    "CrewResult": "core.runner",
    "MemoryManager": "core.memory",
    "ConversationMemory": "core.conversation_memory",
    "PathStore": "core.path_store",
    "AssessmentStore": "core.assessment_store",
    "AssessmentService": "core.assessment_service",
    "ReportBuilder": "core.report_builder",
    "ReportData": "core.report_builder",
    "SessionManager": "core.session",
    "CrewPipeline": "core.pipeline",
    "PipelineResult": "core.pipeline",
    "AdaptiveDeliberationRouter": "core.deliberation",
    "DeliberationDecision": "core.deliberation",
    "DeliberationMode": "core.deliberation",
    "DeliberationResult": "core.deliberation",
    "DeliberationStep": "core.deliberation",
    "DeliberationService": "core.deliberation_service",
}


def __getattr__(name: str) -> Any:
    """惰性导出公开名，并允许 `from core import <子模块>`。"""
    module_path = _EXPORTS.get(name)
    if module_path is not None:
        module = importlib.import_module(module_path)
        value = getattr(module, name)
        globals()[name] = value  # 缓存：后续访问不再走 __getattr__
        return value

    # 兼容 `from core import short_answer_grader` 这类子模块导入。
    try:
        module = importlib.import_module(f"{__name__}.{name}")
    except ImportError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    globals()[name] = module
    return module


def __dir__() -> list[str]:
    return sorted(set(list(globals()) + __all__))
