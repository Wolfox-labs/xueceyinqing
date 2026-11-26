"""自适应多智能体协商的路由与数据结构。

该模块不直接调用大模型，只负责：
1. 判断问题是否需要进入质疑、审核和修订链路；
2. 记录路由依据，保证决策可解释；
3. 为协商服务提供有限轮次配置。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class DeliberationMode(str, Enum):
    """协商模式。"""

    FAST = "fast"
    STANDARD = "standard"
    DELIBERATE = "deliberate"


@dataclass(frozen=True, slots=True)
class DeliberationDecision:
    """一次问题路由的完整决策。"""

    mode: DeliberationMode
    score: float
    reasons: tuple[str, ...]
    max_rounds: int
    focus_points: tuple[str, ...] = ()
    adaptive_hint: dict[str, Any] = field(default_factory=dict)

    @property
    def requires_critic(self) -> bool:
        return self.mode == DeliberationMode.DELIBERATE

    @property
    def requires_review(self) -> bool:
        # 任何模式都必须过审核：不存在"零成本且不审核"的路径。
        # 路由差异体现在质疑与修订深度（max_rounds），而不是要不要审核。
        return True

    @property
    def label(self) -> str:
        return {
            DeliberationMode.FAST: "快速审核路径",
            DeliberationMode.STANDARD: "标准审核路径",
            DeliberationMode.DELIBERATE: "多智能体协商路径",
        }[self.mode]


@dataclass(slots=True)
class DeliberationStep:
    """协商链路中的一个可审计步骤。"""

    stage: str
    label: str
    content: str
    state: str = "completed"


@dataclass(slots=True)
class DeliberationResult:
    """协商服务的最终结果。"""

    raw: str
    mode: DeliberationMode
    withdrawn: bool = False
    reason: str = ""
    steps: list[DeliberationStep] = field(default_factory=list)
    rounds: int = 0
    decision: DeliberationDecision | None = None


_COMPLEX_TERMS = (
    "为什么", "怎么", "如何", "比较", "区别", "优缺点", "解释", "分析",
    "归纳", "关联", "影响", "条件", "边界", "适用", "举例", "推导",
)
_DEEP_TERMS = {
    "证明": 0.32, "设计": 0.30, "架构": 0.28, "优化": 0.24,
    "综合": 0.22, "论证": 0.28, "开放": 0.20, "评价": 0.20,
    "方案": 0.24, "系统": 0.18, "反例": 0.20,
    "多步骤": 0.20, "完整流程": 0.20,
}
_SIMPLE_PREFIXES = ("什么是", "定义", "怎么读", "是谁", "在哪里", "多少")


class AdaptiveDeliberationRouter:
    """根据问题复杂度、学习风险和学习证据决定协商深度。"""

    def __init__(
        self,
        *,
        standard_threshold: float = 0.24,
        deliberate_threshold: float = 0.68,
    ) -> None:
        self.standard_threshold = standard_threshold
        self.deliberate_threshold = deliberate_threshold

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, value))

    def route(
        self,
        question: str,
        *,
        profile_text: str = "",
        adaptive_hint: Mapping[str, Any] | None = None,
        evidence_conflict: bool = False,
    ) -> DeliberationDecision:
        """返回快速、标准或协商模式，并给出可解释理由。"""
        text = (question or "").strip()
        compact = re.sub(r"\s+", "", text)
        score = 0.08
        reasons: list[str] = []

        # 1. 问题本身的长度与复杂度。
        if len(compact) >= 24:
            score += min(0.22, len(compact) / 260.0)
            reasons.append("问题包含多个语义单元")

        question_marks = compact.count("?") + compact.count("？")
        if question_marks:
            score += min(0.08, question_marks * 0.03)

        complex_hits = [term for term in _COMPLEX_TERMS if term in compact]
        deep_hits = [term for term in _DEEP_TERMS if term in compact]
        deep_weight = sum(_DEEP_TERMS[term] for term in deep_hits)
        if complex_hits:
            score += min(0.32, len(complex_hits) * 0.08)
            reasons.append("包含解释或比较类要求")
        if deep_hits:
            score += min(0.42, deep_weight)
            reasons.append("包含设计、证明或优化类要求")

        if any(term in compact for term in ("一定", "总是", "是否", "真的", "绝对")):
            score += 0.12
            reasons.append("问题包含争议性或绝对化判断")

        if compact.startswith(_SIMPLE_PREFIXES) and len(compact) <= 18:
            score -= 0.16
            reasons.append("简单事实型问题")

        # 2. 画像中的基础风险。这里只做轻量启发式，不替代自适应引擎。
        if profile_text and any(term in profile_text for term in ("初学", "基础薄弱", "薄弱", "入门")):
            score += 0.07
            reasons.append("画像显示基础或薄弱环节风险")

        # 3. 自适应引擎给出的知识点优先级和遗忘风险。
        hint = dict(adaptive_hint or {})
        if hint:
            score += 0.06
            try:
                priority = float(hint.get("priority") or 0.0)
            except (TypeError, ValueError):
                priority = 0.0
            try:
                effective = float(hint.get("effective_mastery") or 1.0)
            except (TypeError, ValueError):
                effective = 1.0
            try:
                forgetting = float(hint.get("forgetting_risk") or 0.0)
            except (TypeError, ValueError):
                forgetting = 0.0

            if priority >= 0.72:
                score += 0.18
                reasons.append("自适应引擎判定为高优先级知识点")
            elif priority >= 0.56:
                score += 0.10
                reasons.append("自适应引擎判定为中高优先级知识点")

            if effective < 0.45:
                score += 0.16
                reasons.append("该知识点有效掌握度偏低")
            elif effective < 0.62:
                score += 0.08
                reasons.append("该知识点掌握度仍不稳定")

            if forgetting >= 0.35:
                score += 0.08
                reasons.append("存在明显遗忘风险")

        # 4. 检索证据冲突时，强制提高审核等级。
        if evidence_conflict:
            score += 0.20
            reasons.append("知识库证据可能存在冲突")

        score = self._clamp(score)
        if score >= self.deliberate_threshold:
            mode = DeliberationMode.DELIBERATE
            max_rounds = 2
        elif score >= self.standard_threshold:
            mode = DeliberationMode.STANDARD
            max_rounds = 1
        else:
            # 简单问题也保留 1 轮审核，只是不做质疑。
            mode = DeliberationMode.FAST
            max_rounds = 1

        focus_points: tuple[str, ...] = ()
        point = str(hint.get("knowledge_point") or "").strip()
        if point:
            focus_points = (point,)

        return DeliberationDecision(
            mode=mode,
            score=round(score, 4),
            reasons=tuple(reasons or ["问题复杂度较低"]),
            max_rounds=max_rounds,
            focus_points=focus_points,
            adaptive_hint=hint,
        )

