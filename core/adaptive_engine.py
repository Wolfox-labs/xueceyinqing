"""可解释自适应学习引擎。

核心能力：
1. 根据测评证据更新知识点掌握度。
2. 使用遗忘曲线估计当前有效掌握度。
3. 融合前置依赖、错误频率和知识重要度计算优先级。
4. 使用上下文 UCB 在线选择教学动作，平衡利用与探索。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import exp, log, log1p, sqrt
from typing import Iterable, Mapping


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _as_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@dataclass(slots=True)
class MasteryState:
    """单个学习者的知识点状态。"""

    knowledge_point: str
    mastery: float = 0.5
    evidence_count: int = 0
    last_practiced: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        self.mastery = _clamp(self.mastery)
        self.last_practiced = _as_utc(self.last_practiced)


@dataclass(frozen=True, slots=True)
class KnowledgeNode:
    """知识图谱节点。"""

    name: str
    importance: float = 0.5
    prerequisites: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Recommendation:
    """面向教学策略层的推荐结果。"""

    knowledge_point: str
    effective_mastery: float
    forgetting_risk: float
    priority: float
    target_difficulty: float
    reason: str


@dataclass(slots=True)
class BanditStat:
    pulls: int = 0
    reward_sum: float = 0.0

    @property
    def mean_reward(self) -> float:
        return self.reward_sum / self.pulls if self.pulls else 0.0


class AdaptiveLearningEngine:
    """可解释的知识状态更新与推荐引擎。"""

    def __init__(self, default_half_life_days: float = 14.0) -> None:
        self.default_half_life_days = max(1.0, default_half_life_days)

    @staticmethod
    def evidence_weight(evidence_count: int) -> float:
        """答题证据越多，单次更新越接近稳定估计，同时设置上下限。"""
        return _clamp(0.20 + 0.08 * sqrt(max(0, evidence_count)), 0.20, 0.55)

    def update_mastery(
        self,
        state: MasteryState,
        score: float,
        *,
        observed_at: datetime | None = None,
    ) -> MasteryState:
        """使用指数移动平均更新掌握度。score 必须在 0~1。"""
        score = _clamp(score)
        observed_at = _as_utc(observed_at)
        alpha = self.evidence_weight(state.evidence_count)
        state.mastery = _clamp(state.mastery + alpha * (score - state.mastery))
        state.evidence_count += 1
        state.last_practiced = observed_at
        return state

    def effective_mastery(
        self,
        state: MasteryState,
        *,
        now: datetime | None = None,
        half_life_days: float | None = None,
    ) -> float:
        """将遗忘曲线应用到最近一次掌握度记录。"""
        now = _as_utc(now)
        elapsed_days = max(0.0, (now - state.last_practiced).total_seconds() / 86400.0)
        half_life = max(1.0, half_life_days or self.default_half_life_days)
        return _clamp(state.mastery * (2.0 ** (-elapsed_days / half_life)))

    def priority_score(
        self,
        state: MasteryState,
        *,
        importance: float = 0.5,
        dependency_count: int = 0,
        recent_errors: int = 0,
        now: datetime | None = None,
    ) -> float:
        """计算推荐优先级，输出范围 0~1。"""
        effective = self.effective_mastery(state, now=now)
        mastery_gap = 1.0 - effective
        forgetting_risk = _clamp(1.0 - effective / max(state.mastery, 1e-6))
        dependency_urgency = _clamp(log1p(max(0, dependency_count)) / log(9.0))
        error_signal = _clamp(1.0 - exp(-0.7 * max(0, recent_errors)))
        importance = _clamp(importance)
        return _clamp(
            0.40 * mastery_gap
            + 0.20 * forgetting_risk
            + 0.15 * dependency_urgency
            + 0.15 * error_signal
            + 0.10 * importance
        )

    @staticmethod
    def target_difficulty(effective_mastery: float) -> float:
        """选择略高于当前水平的挑战难度，维持约 65%~75% 成功率。"""
        return round(_clamp(effective_mastery + 0.14, 0.15, 0.92), 3)

    def recommend(
        self,
        states: Iterable[MasteryState],
        graph: Mapping[str, KnowledgeNode] | None = None,
        *,
        recent_errors: Mapping[str, int] | None = None,
        now: datetime | None = None,
        limit: int | None = None,
    ) -> list[Recommendation]:
        """按教学优先级排序知识点，并给出可解释推荐原因。"""
        graph = graph or {}
        recent_errors = recent_errors or {}
        rows: list[Recommendation] = []

        for state in states:
            node = graph.get(state.knowledge_point, KnowledgeNode(state.knowledge_point))
            effective = self.effective_mastery(state, now=now)
            dependent_count = sum(
                1 for graph_node in graph.values()
                if state.knowledge_point in graph_node.prerequisites
            )
            priority = self.priority_score(
                state,
                importance=node.importance,
                dependency_count=dependent_count,
                recent_errors=recent_errors.get(state.knowledge_point, 0),
                now=now,
            )
            forgetting_risk = _clamp(1.0 - effective / max(state.mastery, 1e-6))
            reason_bits = [f"有效掌握度 {effective:.0%}"]
            if forgetting_risk >= 0.25:
                reason_bits.append(f"遗忘风险 {forgetting_risk:.0%}")
            if recent_errors.get(state.knowledge_point, 0):
                reason_bits.append(f"近期错误 {recent_errors[state.knowledge_point]} 次")
            if dependent_count:
                reason_bits.append(f"影响 {dependent_count} 个后续节点")

            rows.append(Recommendation(
                knowledge_point=state.knowledge_point,
                effective_mastery=round(effective, 4),
                forgetting_risk=round(forgetting_risk, 4),
                priority=round(priority, 4),
                target_difficulty=self.target_difficulty(effective),
                reason="；".join(reason_bits),
            ))

        rows.sort(key=lambda item: (-item.priority, item.effective_mastery))
        return rows[:limit] if limit else rows


class ContextualUCBPolicy:
    """轻量上下文多臂老虎机策略，在线学习哪种教学动作最有效。"""

    def __init__(self, exploration: float = 1.15) -> None:
        self.exploration = max(0.0, exploration)
        self._stats: dict[str, dict[str, BanditStat]] = {}
        self._total_pulls = 0
        # 同一个 policy 实例按用户共享，并被事件循环与执行线程并发访问，
        # 所有对 _stats / _total_pulls 的读写都必须串行化。
        self._lock = threading.RLock()

    @staticmethod
    def context_key(
        *,
        mastery: float,
        urgency: float,
        learning_style: str = '',
    ) -> str:
        """构造上下文键。

        learning_style 缺省为空串而不是 'reading'：调用方没提供偏好时，
        应当归入 unknown 桶，而不是替学习者假定一种学习风格。
        """
        mastery_bucket = 'low' if mastery < 0.4 else 'mid' if mastery < 0.72 else 'high'
        urgency_bucket = 'hot' if urgency >= 0.55 else 'cold'
        return f"{mastery_bucket}:{urgency_bucket}:{learning_style or 'unknown'}"

    def select(self, context: str, actions: Iterable[str]) -> str:
        actions = list(actions)
        if not actions:
            raise ValueError('actions must not be empty')

        with self._lock:
            bucket = self._stats.setdefault(context, {})
            for action in actions:
                stat = bucket.setdefault(action, BanditStat())
                if stat.pulls == 0:
                    return action

            # 探索项必须按**该上下文**的累计拉动次数计算。用全局 pulls 会让
            # log(total) 系统性偏大，探索过度、收敛变慢。
            context_pulls = sum(stat.pulls for stat in bucket.values())
            total = max(1, context_pulls)
            return max(
                actions,
                key=lambda action: (
                    bucket[action].mean_reward
                    + self.exploration * sqrt(log(total + 1) / bucket[action].pulls)
                ),
            )

    def update(self, context: str, action: str, reward: float) -> None:
        """reward 建议归一化到 0~1，例如测评增益 × 完成度。"""
        reward = _clamp(reward)
        with self._lock:
            bucket = self._stats.setdefault(context, {})
            stat = bucket.setdefault(action, BanditStat())
            stat.pulls += 1
            stat.reward_sum += reward
            self._total_pulls += 1

    def snapshot(self) -> dict[str, dict[str, dict[str, float | int]]]:
        with self._lock:
            return {
                context: {
                    action: {
                        'pulls': stat.pulls,
                        'mean_reward': round(stat.mean_reward, 4),
                    }
                    for action, stat in bucket.items()
                }
                for context, bucket in self._stats.items()
            }


