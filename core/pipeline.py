"""
Crew 执行管线 — 封装 ReviewContext 注入、Crew 执行、审核判词解析、撤回检查、记忆保存。

职责：
1. 每次执行前创建新的 ReviewContext 注入到 reviewer 的 WithdrawOutputTool
2. 执行 Crew；审核 Agent 的产出被隔离，不进入交付内容
3. 解析审核判词，检查撤回状态
4. 只有未被撤回的内容才会通过 on_chunk 交付，并在 session_id 非空时保存记忆

交付语义（重要）：
    内容先缓冲、后放行。Crew 执行完成、审核结论确定之后才调用 on_chunk，
    因此被撤回的内容不会流到用户侧；旧实现把 on_chunk 透传给 runner，
    回调在撤回检查之前就触发了，撤回只能追加一句提示而收不回正文。

消除 main.py / streamlit_app.py / api_server/main.py 中 7 处重复的手写管线。
"""
import logging
from typing import Callable, Optional, Sequence

from core.runner import CrewRunner, PipelineResult
from tools.review_tools import (
    VERDICT_UNKNOWN,
    ReviewContext,
    WithdrawOutputTool,
    parse_verdict,
)

logger = logging.getLogger(__name__)

__all__ = ["CrewPipeline", "PipelineResult"]


class CrewPipeline:
    """标准执行管线，封装 ReviewContext 注入、执行、审核、撤回、记忆写入。

    用法::

        pipeline = CrewPipeline(reviewer, memory)
        result = pipeline.execute(crew,
            session_id=sid, turn=n, question=q,
            runner=runner, on_chunk=cb)

        if result.withdrawn:
            # 处理撤回
        else:
            # 使用 result.raw
    """

    def __init__(self, reviewer_agent, memory=None, exclude_agent_roles: Sequence[str] = ()):
        self._reviewer = reviewer_agent
        self._memory = memory
        tools = list(getattr(reviewer_agent, "tools", []) or [])
        self._withdraw_tools = [t for t in tools if isinstance(t, WithdrawOutputTool)]

        # 审核 Agent 的产出不是交付内容，按角色隔离。
        roles = [role for role in exclude_agent_roles if role]
        reviewer_role = getattr(reviewer_agent, "role", None)
        if isinstance(reviewer_role, str) and reviewer_role.strip():
            roles.append(reviewer_role)
        self._exclude_roles = tuple(dict.fromkeys(roles))

    def execute(self, crew, *,
                session_id: str = None,
                turn: int = 0,
                question: str = "",
                runner: CrewRunner = None,
                on_chunk: Optional[Callable[[str], None]] = None) -> PipelineResult:
        """执行标准管线。

        Args:
            crew: 已构建好的 Crew 实例。
            session_id: 会话 ID，非空时在正常输出后自动保存到记忆。
            turn: 当前轮次。
            question: 用户问题文本，作为记忆的 question 字段。
            runner: 可选的 CrewRunner；为 None 时内部创建。
            on_chunk: 交付回调。只在内容通过审核之后触发一次，
                被撤回时不会被调用。

        Returns:
            PipelineResult(raw, withdrawn, reason, metrics, verdict, review_text, agent_roles)
        """
        review_ctx = ReviewContext()
        for tool in self._withdraw_tools:
            object.__setattr__(tool, '_ctx', review_ctx)

        # 不把 on_chunk 透传给 runner：先拿到完整结果与审核判词，再决定是否放行。
        r = runner or CrewRunner()
        crew_result = r.run(crew, exclude_agent_roles=self._exclude_roles)

        review_text = getattr(crew_result, "review_text", "") or ""
        verdict = parse_verdict(review_text)
        # 把判词原文一起交出去：只有它才能判断"不通过"是硬问题还是措辞建议。
        review_ctx.set_verdict(verdict, review_text)

        if self._exclude_roles and verdict == VERDICT_UNKNOWN and not review_ctx.is_withdrawn():
            # 只有在被隔离的 Agent 确实产出了文本、却认不出判词时才告警；
            # 不含审核任务的 Crew（如 /ask）不会有这个角色的产出。
            roles = getattr(crew_result, "agent_roles", ()) or ()
            if any(role in roles for role in self._exclude_roles):
                logger.warning(
                    "审核 Agent 未产出可识别判词，按旧行为放行；review_text=%r",
                    review_text[:200],
                )

        if review_ctx.is_withdrawn():
            return PipelineResult(
                raw=crew_result.raw,
                withdrawn=True,
                reason=review_ctx.reason(),
                metrics=crew_result.metrics,
                verdict=review_ctx.verdict(),
                review_text=review_text,
                agent_roles=getattr(crew_result, "agent_roles", ()),
            )

        # 审核通过后才交付。
        if on_chunk and crew_result.raw:
            on_chunk(crew_result.raw)

        if session_id and self._memory:
            self._memory.save_turn(session_id, turn, question, crew_result.raw)

        return PipelineResult(
            raw=crew_result.raw,
            withdrawn=False,
            reason="",
            metrics=crew_result.metrics,
            verdict=review_ctx.verdict(),
            review_text=review_text,
            agent_roles=getattr(crew_result, "agent_roles", ()),
        )
