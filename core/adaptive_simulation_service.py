"""算法实验室虚拟学习者状态服务。

实验室滑块不直接修改真实学生数据，而是创建一个隔离的虚拟学习者。
问答接口通过 simulation_id 使用该状态，从而演示个性化差异。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from core.adaptive_engine import AdaptiveLearningEngine, ContextualUCBPolicy, MasteryState
from db.vector_store import get_store


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


class AdaptiveSimulationService:
    def __init__(self, user_id: str, store=None) -> None:
        self.user_id = user_id
        self._store = store or get_store()
        self._engine = AdaptiveLearningEngine(default_half_life_days=14.0)

    def _key(self, simulation_id: str) -> str:
        return f"adaptive_simulation_{self.user_id}_{simulation_id}"

    def create(self, payload: dict[str, Any]) -> dict:
        knowledge_point = str(payload.get("knowledge_point") or "算法基础").strip()
        mastery = _clamp(payload.get("mastery", 0.5))
        forgetting = _clamp(payload.get("forgetting", 0.4))
        dependency = _clamp(payload.get("dependency", 0.5))
        errors = _clamp(payload.get("errors", 0.3))
        importance = _clamp(payload.get("importance", 0.7))
        now = datetime.now(timezone.utc)
        # 遗忘风险越高，模拟状态距离上次学习越久。
        days_ago = 1.0 + forgetting * 28.0
        state = MasteryState(
            knowledge_point=knowledge_point,
            mastery=mastery,
            evidence_count=max(1, int(errors * 8)),
            last_practiced=now - timedelta(days=days_ago),
        )
        effective = self._engine.effective_mastery(state, now=now)
        forgetting_risk = _clamp(1.0 - effective / max(mastery, 1e-6))
        priority = self._engine.priority_score(
            state,
            importance=importance,
            dependency_count=max(0, int(dependency * 5)),
            recent_errors=max(0, int(errors * 5)),
            now=now,
        )
        target_difficulty = self._engine.target_difficulty(effective)

        if forgetting_risk >= 0.60:
            action = "review"
        elif mastery < 0.40:
            action = "explain"
        elif errors >= 0.60:
            action = "practice"
        elif mastery >= 0.75:
            action = "challenge"
        else:
            action = "example"
        labels = {
            "explain": "概念讲解",
            "example": "示例驱动讲解",
            "practice": "基础练习",
            "review": "间隔复习",
            "challenge": "挑战任务",
        }
        context = ContextualUCBPolicy.context_key(
            mastery=effective,
            urgency=priority,
            learning_style="reading",
        )
        hint = {
            "knowledge_point": knowledge_point,
            "effective_mastery": round(effective, 4),
            "forgetting_risk": round(forgetting_risk, 4),
            "priority": round(priority, 4),
            "target_difficulty": target_difficulty,
            "reason": (
                f"虚拟学习者有效掌握度 {effective:.0%}；"
                f"遗忘风险 {forgetting_risk:.0%}；"
                f"近期错误信号 {errors:.0%}；"
                f"知识重要度 {importance:.0%}"
            ),
            "action": action,
            "action_label": labels[action],
            "context": context,
        }
        simulation_id = uuid.uuid4().hex[:12]
        data = {
            "simulation_id": simulation_id,
            "user_id": self.user_id,
            "created_at": now.isoformat(),
            "inputs": {
                "knowledge_point": knowledge_point,
                "mastery": mastery,
                "forgetting": forgetting,
                "dependency": dependency,
                "errors": errors,
                "importance": importance,
            },
            "hint": hint,
            "profile_text": (
                f"算法实验室虚拟学习者：当前关注知识点「{knowledge_point}」，"
                f"有效掌握度 {effective:.0%}，遗忘风险 {forgetting_risk:.0%}，"
                f"推荐动作「{labels[action]}」，目标难度 {target_difficulty:.0%}。"
                "请根据该虚拟状态调整讲解深度、例子数量和练习建议。"
            ),
        }
        self._store.save_data(self._key(simulation_id), data)
        return data

    def get(self, simulation_id: str) -> dict | None:
        if not simulation_id:
            return None
        data = self._store.get_data(self._key(simulation_id))
        if not data or data.get("user_id") != self.user_id:
            return None
        return data