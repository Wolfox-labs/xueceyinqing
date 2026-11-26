"""有限轮次多智能体协商服务。

流程：
    教学初答 -> 质疑 -> 审核 -> 修订
    -> 必要时进行第二轮质疑与审核
    -> 返回学生版最终回答

本服务只负责编排，不负责 HTTP、SSE 或数据库。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from core.deliberation import (
    AdaptiveDeliberationRouter,
    DeliberationDecision,
    DeliberationMode,
    DeliberationResult,
    DeliberationStep,
)
from core.parsing import _extract_json
from core.runner import CrewRunner
from core.agent_trace import public_summary

# 注意：core.pipeline（→ tools.review_tools）与 crews.deliberation 都会在导入时
# 拉起 crewai。它们改为在使用处局部导入，否则任何 `import core.deliberation_service`
# 都会把整个 LLM 框架拖进来——单元测试无法运行、纯逻辑层与框架强耦合。

StatusCallback = Callable[[dict[str, Any]], None]


@dataclass(slots=True)
class ReviewVerdict:
    status: str
    reason: str
    must_fix: list[str]


def _parse_review_verdict(text: str) -> ReviewVerdict:
    """兼容 JSON 和自然语言审核结论。解析失败时按需修订处理。"""
    raw = (text or "").strip()
    data = _extract_json(raw)
    if isinstance(data, dict):
        status = str(data.get("status") or "").strip().lower()
        if status not in {"pass", "revise", "withdraw"}:
            status = "revise"
        reason = str(data.get("reason") or "").strip()
        must_fix = data.get("must_fix") or []
        if isinstance(must_fix, str):
            must_fix = [must_fix]
        if not isinstance(must_fix, list):
            must_fix = []
        return ReviewVerdict(status=status, reason=reason, must_fix=[str(x) for x in must_fix])

    if any(term in raw for term in ("撤回", "禁止输出", "严重错误", "违规")):
        return ReviewVerdict("withdraw", raw[:180] or "审核要求撤回", [])
    if any(term in raw for term in ("不通过", "需修订", "需要修订", "revise", "must_fix")):
        return ReviewVerdict("revise", raw[:180] or "审核要求修订", [])
    if "通过" in raw or "pass" in raw.lower():
        return ReviewVerdict("pass", raw[:180], [])

    # 审核无法解析时宁可采用保守修订，不直接把初版答案交给学习者。
    return ReviewVerdict("revise", raw[:180] or "审核结论格式无法解析", [])


class DeliberationService:
    """执行有上限的画像、教学、质疑、审核和修订链路。"""

    def __init__(
        self,
        *,
        teacher,
        critic,
        reviewer,
        tools=None,
        runner: CrewRunner | None = None,
        router: AdaptiveDeliberationRouter | None = None,
    ) -> None:
        self.teacher = teacher
        self.critic = critic
        self.reviewer = reviewer
        self.tools = tools
        self.runner = runner or CrewRunner()
        self.router = router or AdaptiveDeliberationRouter()
        from core.pipeline import CrewPipeline  # 局部导入：见文件头说明
        self.review_pipeline = CrewPipeline(reviewer)

    @staticmethod
    def _emit(
        callback: StatusCallback | None,
        *,
        stage: str,
        label: str,
        detail: str,
        state: str = "completed",
        mode: str = "",
        summary: list[str] | None = None,
        handoff: str = "",
        routing: dict[str, Any] | None = None,
    ) -> None:
        if callback:
            callback({
                "stage": stage,
                "label": label,
                "detail": detail,
                "state": state,
                "mode": mode,
                "summary": summary or [detail],
                "handoff": handoff,
                **({"routing": routing} if routing is not None else {}),
            })

    def run(
        self,
        question: str,
        *,
        context: str = "",
        profile_text: str = "",
        adaptive_hint: dict[str, Any] | None = None,
        evidence_conflict: bool = False,
        decision: DeliberationDecision | None = None,
        on_status: StatusCallback | None = None,
    ) -> DeliberationResult:
        # 局部导入：crews.deliberation 会在导入时拉起 crewai（见文件头说明）。
        from crews.deliberation import (
            build_critique_crew,
            build_initial_answer_crew,
            build_review_crew,
            build_revision_crew,
        )

        decision = decision or self.router.route(
            question,
            profile_text=profile_text,
            adaptive_hint=adaptive_hint,
            evidence_conflict=evidence_conflict,
        )
        steps: list[DeliberationStep] = []

        self._emit(
            on_status,
            stage="route",
            label="自适应路由",
            detail=f"{decision.label}，最多核对 {decision.max_rounds} 轮",
            mode=decision.mode.value,
            summary=list(decision.reasons)[:3],
            handoff=f"将问题交给教学 Agent；本次最多核对 {decision.max_rounds} 轮。",
            routing={
                "score": decision.score,
                "reasons": list(decision.reasons),
                "critic_scheduled": decision.requires_critic and decision.max_rounds > 0,
                "max_rounds": decision.max_rounds,
            },
        )

        # 第一步：教学 Agent 生成初版回答。
        self._emit(on_status, stage="initial", label="教学 Agent 生成初答", detail="正在构建个性化初版回答", state="running", mode=decision.mode.value)
        initial = self.runner.run(
            build_initial_answer_crew(
                self.teacher,
                question,
                context=context,
                profile_text=profile_text,
                decision=decision,
                tools=self.tools,
            )
        ).raw.strip()
        steps.append(DeliberationStep("initial", "教学 Agent 初答", initial))
        self._emit(on_status, stage="initial", label="教学 Agent 生成初答", detail="初版回答已生成", mode=decision.mode.value,
                   summary=["已结合当前问题与学习上下文生成初版回答。", "初版内容等待后续核验。"] if decision.max_rounds else ["已完成本次回答；当前配置跳过审核。"],
                   handoff="交给质疑 Agent 检查。" if decision.requires_critic and decision.max_rounds else "交给审核 Agent 核验。" if decision.max_rounds else "直接返回本次回答。")

        # FAST 不再直接返回初答：审核是所有模式的必经关卡（见
        # AdaptiveDeliberationRouter.requires_review）。深度只由 max_rounds 控制——
        # FAST/STANDARD 为 1 轮且不做质疑，DELIBERATE 为 2 轮含质疑。
        # 注意：显式关闭审核时（agent 配置或单 Agent 变体）max_rounds 为 0，
        # 下面的循环不会执行，末尾会原样返回初答，保持该变体可用。
        current_answer = initial
        rounds = 0

        for round_no in range(1, decision.max_rounds + 1):
            critique = ""
            if decision.mode == DeliberationMode.DELIBERATE:
                self._emit(on_status, stage=f"critique_{round_no}", label=f"质疑 Agent 第 {round_no} 轮检查", detail="正在寻找漏洞、反例和前置知识缺口", state="running", mode=decision.mode.value)
                critique = self.runner.run(
                    build_critique_crew(
                        self.critic,
                        question,
                        current_answer,
                        context=context,
                        decision=decision,
                        tools=self.tools,
                    )
                ).raw.strip()
                steps.append(DeliberationStep(f"critique_{round_no}", f"质疑 Agent 第 {round_no} 轮", critique))
                self._emit(on_status, stage=f"critique_{round_no}", label=f"质疑 Agent 第 {round_no} 轮检查", detail="质疑检查完成", mode=decision.mode.value,
                           summary=public_summary(critique), handoff="将当前回答与质疑意见一起交给审核 Agent。")

            self._emit(on_status, stage=f"review_{round_no}", label=f"审核 Agent 第 {round_no} 轮核验", detail="正在核验事实、证据和适用边界", state="running", mode=decision.mode.value)
            review_pipeline_result = self.review_pipeline.execute(
                build_review_crew(
                    self.reviewer,
                    question,
                    current_answer,
                    critique=critique,
                    profile_text=profile_text,
                    decision=decision,
                )
            )
            if review_pipeline_result.withdrawn:
                self._emit(on_status, stage=f"review_{round_no}", label=f"审核 Agent 第 {round_no} 轮核验", detail="审核要求撤回", state="error", mode=decision.mode.value,
                           summary=public_summary(review_pipeline_result.reason), handoff="停止交付本次回答。")
                return DeliberationResult(
                    raw=current_answer,
                    mode=decision.mode,
                    withdrawn=True,
                    reason=review_pipeline_result.reason,
                    steps=steps,
                    rounds=round_no,
                    decision=decision,
                )

            verdict = _parse_review_verdict(review_pipeline_result.raw)
            steps.append(DeliberationStep(f"review_{round_no}", f"审核 Agent 第 {round_no} 轮", review_pipeline_result.raw))
            needs_revision = verdict.status != "pass" or bool(verdict.must_fix)
            verdict_label = "撤回" if verdict.status == "withdraw" else "需修订" if needs_revision else "通过"
            review_summary = public_summary("\n".join([verdict.reason, *verdict.must_fix]))
            self._emit(on_status, stage=f"review_{round_no}", label=f"审核 Agent 第 {round_no} 轮核验", detail=f"核验结果：{verdict_label}", mode=decision.mode.value,
                       state="error" if verdict.status == "withdraw" else "completed",
                       summary=review_summary,
                       handoff="停止交付本次回答。" if verdict.status == "withdraw" else "把审核意见交回同一个教学 Agent 修订。" if needs_revision else "审核通过，返回当前回答。")

            if verdict.status == "withdraw":
                return DeliberationResult(
                    raw=current_answer,
                    mode=decision.mode,
                    withdrawn=True,
                    reason=verdict.reason or "审核要求撤回",
                    steps=steps,
                    rounds=round_no,
                    decision=decision,
                )
            if verdict.status == "pass" and not verdict.must_fix:
                return DeliberationResult(
                    raw=current_answer,
                    mode=decision.mode,
                    steps=steps,
                    rounds=round_no,
                    decision=decision,
                )

            self._emit(on_status, stage=f"revision_{round_no}", label=f"教学 Agent 第 {round_no} 轮修订", detail="正在根据质疑与审核意见修订", state="running", mode=decision.mode.value,
                       summary=["已收到审核回传，正在修订原回答。", *review_summary[:2]])
            current_answer = self.runner.run(
                build_revision_crew(
                    self.teacher,
                    question,
                    current_answer,
                    critique=critique,
                    review=review_pipeline_result.raw,
                    context=context,
                    profile_text=profile_text,
                    decision=decision,
                    tools=self.tools,
                )
            ).raw.strip()
            steps.append(DeliberationStep(f"revision_{round_no}", f"教学 Agent 第 {round_no} 轮修订", current_answer))
            self._emit(on_status, stage=f"revision_{round_no}", label=f"教学 Agent 第 {round_no} 轮修订", detail="修订完成", mode=decision.mode.value,
                       summary=["已根据本轮意见生成修订稿。", *review_summary[:2]],
                       handoff="将修订稿交给下一轮质疑与审核。" if round_no < decision.max_rounds else "已达本次轮数上限，返回修订稿；修订后未再次核验。")
            rounds = round_no

        return DeliberationResult(
            raw=current_answer,
            mode=decision.mode,
            steps=steps,
            rounds=rounds,
            decision=decision,
        )
