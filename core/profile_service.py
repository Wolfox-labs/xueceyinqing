"""学习者动态档案聚合服务。

将画像、问答、测评、学习路径和资源生成信号聚合为前端可直接渲染的卡片数据。
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from core.assessment_store import AssessmentStore
from core.path_store import PathStore
from db.vector_store import get_store
from schemas.learning_path import LearningPath
from schemas.profile import StudentProfile
from schemas.profile_dashboard import (
    ProfileActivity,
    ProfileCard,
    ProfileCardItem,
    ProfileDashboardResponse,
)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _normalize_score(value: Any) -> float | None:
    if value is None:
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    if score > 1.0:
        score /= 100.0
    return _clamp(score)


def _weak_point_name(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("knowledge_point") or item.get("name") or "").strip()
    return str(item or "").strip()


class ProfileService:
    """聚合并维护一个学习者的动态数字画像。"""

    def __init__(self, user_id: str = "default"):
        self.user_id = user_id
        self.store = get_store()
        self.path_store = PathStore(self.store, user_id)
        self.assessment_store = AssessmentStore(self.store, user_id)

    @property
    def _state_key(self) -> str:
        return f"profile_dashboard_state_{self.user_id}"

    def _load_state(self) -> dict:
        try:
            state = self.store.get_data(self._state_key) or {}
        except Exception:
            state = {}
        return {
            "signals": list(state.get("signals") or []),
            "update_log": list(state.get("update_log") or []),
        }

    def _save_state(self, state: dict) -> None:
        state["signals"] = list(state.get("signals") or [])[-300:]
        state["update_log"] = list(state.get("update_log") or [])[-120:]
        self.store.save_data(self._state_key, state)

    def _append_signal(
        self,
        *,
        source: str,
        kind: str,
        value: str,
        detail: str = "",
        confidence: float | None = None,
        score: float | None = None,
    ) -> None:
        state = self._load_state()
        timestamp = datetime.now().isoformat()
        state["signals"].append({
            "timestamp": timestamp,
            "source": source,
            "kind": kind,
            "value": value,
            "detail": detail,
            "confidence": confidence,
            "score": score,
        })
        state["update_log"].append({
            "timestamp": timestamp,
            "source": source,
            "title": detail or f"{source} 更新",
            "detail": value,
        })
        self._save_state(state)

    def record_qa(
        self,
        question: str,
        answer: str,
        *,
        knowledge_point: str | None = None,
        mode: str = "fast",
    ) -> None:
        """记录一次问答对画像的潜在影响。"""
        topic = (knowledge_point or question or "").strip()
        if not topic:
            return
        display_topic = topic if len(topic) <= 30 else topic[:30] + "..."
        self._append_signal(
            source="qa",
            kind="topic",
            value=display_topic,
            detail=f"问答（{mode}）发现关注主题",
            confidence=0.68,
        )
        if len(question) > 80:
            self._append_signal(
                source="qa",
                kind="preference",
                value="详细解释",
                detail="问答中出现复杂问题，偏好深度解释",
                confidence=0.55,
            )

    def record_assessment(self, result: dict) -> None:
        """记录测评产生的掌握度、薄弱点和优势信号。"""
        topic = str(result.get("topic") or "诊断测评").strip()
        self._append_signal(
            source="assessment",
            kind="topic",
            value=topic,
            detail=f"完成测评，正确率 {result.get('percentage', 0)}%",
            confidence=0.95,
        )
        for item in result.get("weak_points") or []:
            name = _weak_point_name(item)
            if not name:
                continue
            score = _normalize_score(item.get("score") if isinstance(item, dict) else None)
            self._append_signal(
                source="assessment",
                kind="weak_point",
                value=name,
                detail=f"测评确认薄弱点：{name}",
                confidence=0.92,
                score=score,
            )
        for strength in result.get("strengths") or []:
            name = str(strength).strip()
            if not name:
                continue
            self._append_signal(
                source="assessment",
                kind="strength",
                value=name,
                detail=f"测评确认优势：{name}",
                confidence=0.9,
                score=0.9,
            )

    def record_learning_path(self, path: LearningPath | dict) -> None:
        """记录学习路径目标和节点完成情况。"""
        if isinstance(path, LearningPath):
            topic = path.topic
            nodes = path.nodes
        else:
            topic = str(path.get("topic") or "学习路径")
            nodes = path.get("nodes") or []
        completed = sum(1 for node in nodes if getattr(node, "status", None) == "completed" or (isinstance(node, dict) and node.get("status") == "completed"))
        self._append_signal(
            source="path",
            kind="topic",
            value=topic,
            detail=f"生成学习路径，完成度 {completed}/{len(nodes)}",
            confidence=0.86,
        )

    def record_resource(self, resource_type: str, topic: str) -> None:
        """记录资源类型偏好和关注主题。"""
        labels = {
            "document": "讲解文档",
            "mindmap": "思维导图",
            "exercise": "练习题",
            "ppt": "演示文稿",
        }
        resource_label = labels.get(resource_type, resource_type)
        self._append_signal(
            source="resource",
            kind="topic",
            value=topic,
            detail=f"生成资源：{resource_label}",
            confidence=0.72,
        )
        self._append_signal(
            source="resource",
            kind="preference",
            value=resource_label,
            detail=f"资源偏好倾向：{resource_label}",
            confidence=0.66,
        )

    def _topic_counter(self, signals: list[dict]) -> Counter:
        counter: Counter = Counter()
        for signal in signals:
            if signal.get("kind") != "topic":
                continue
            value = str(signal.get("value") or "").strip()
            if value:
                counter[value] += 1
        return counter

    def _preference_values(self, signals: list[dict]) -> dict[str, str]:
        preferences: dict[str, str] = {}
        for signal in reversed(signals):
            if signal.get("kind") != "preference":
                continue
            value = str(signal.get("value") or "").strip()
            if value and value not in preferences:
                preferences[value] = str(signal.get("source") or "system")
        return preferences

    def _weak_points(self, profile: StudentProfile, history: list[dict], signals: list[dict]) -> list[dict]:
        rows: dict[str, dict] = {}
        for name in profile.weak_points:
            if name:
                rows[name] = {"name": name, "score": None, "source": "profile"}
        for item in history[0].get("weak_points", []) if history else []:
            name = _weak_point_name(item)
            if not name:
                continue
            rows[name] = {
                "name": name,
                "score": _normalize_score(item.get("score") if isinstance(item, dict) else None),
                "source": "assessment",
            }
        for signal in signals:
            if signal.get("kind") != "weak_point":
                continue
            name = str(signal.get("value") or "").strip()
            if not name:
                continue
            rows.setdefault(name, {
                "name": name,
                "score": _normalize_score(signal.get("score")),
                "source": signal.get("source") or "signal",
            })
        result = list(rows.values())
        result.sort(key=lambda row: (row.get("score") is None, row.get("score") or 0.5))
        return result

    def _mastery(self, profile: StudentProfile, history: list[dict], signals: list[dict]) -> dict[str, float]:
        mastery = {str(k): _clamp(float(v)) for k, v in profile.knowledge_mastery.items()}
        for signal in signals:
            kind = signal.get("kind")
            value = str(signal.get("value") or "").strip()
            score = _normalize_score(signal.get("score"))
            if not value or score is None:
                continue
            if kind in {"weak_point", "strength", "assessment"}:
                mastery[value] = score
        if history:
            for item in history[0].get("weak_points", []):
                name = _weak_point_name(item)
                score = _normalize_score(item.get("score") if isinstance(item, dict) else None)
                if name and score is not None:
                    mastery[name] = score
        return mastery

    def _activities(self, state: dict, history: list[dict], profile: StudentProfile) -> list[ProfileActivity]:
        activities: list[ProfileActivity] = []
        for entry in reversed(state.get("update_log", [])):
            activities.append(ProfileActivity(
                timestamp=str(entry.get("timestamp") or ""),
                source=str(entry.get("source") or "system"),
                title=str(entry.get("title") or "画像更新"),
                detail=str(entry.get("detail") or ""),
            ))
        for item in history[:3]:
            activities.append(ProfileActivity(
                timestamp=str(item.get("timestamp") or ""),
                source="assessment",
                title=f"测评：{item.get('topic', '未命名主题')}",
                detail=f"正确率 {item.get('percentage', 0)}%",
            ))
        if not activities:
            activities.append(ProfileActivity(
                timestamp="",
                source="system",
                title="等待第一次学习证据",
                detail="完成问答、测评或学习路径后，这里会自动更新。",
            ))
        activities.sort(key=lambda item: item.timestamp, reverse=True)
        return activities[:8]

    def _cards(
        self,
        profile: StudentProfile,
        mastery: dict[str, float],
        weak_points: list[dict],
        topics: Counter,
        preferences: dict[str, str],
        activities: list[ProfileActivity],
    ) -> list[ProfileCard]:
        top_topics = [name for name, _ in topics.most_common(8)] or profile.subjects
        mastery_items = [
            ProfileCardItem(
                label=name,
                value=f"{score:.0%}",
                source="adaptive",
                status="stable" if score >= 0.8 else "confirmed" if score >= 0.55 else "inferred",
                confidence=0.8,
                score=score * 100,
            )
            for name, score in sorted(mastery.items(), key=lambda item: item[1], reverse=True)[:6]
        ]
        weak_items = [
            ProfileCardItem(
                label=row["name"],
                value=f"{row['score']:.0%}" if row.get("score") is not None else "待验证",
                source=row.get("source") or "profile",
                status="confirmed" if row.get("source") == "assessment" else "inferred",
                confidence=0.85 if row.get("source") == "assessment" else 0.6,
                score=(row["score"] * 100) if row.get("score") is not None else None,
            )
            for row in weak_points[:6]
        ]

        return [
            ProfileCard(
                id="identity",
                title="学习者名片",
                subtitle="当前身份与学习阶段",
                kind="identity",
                items=[
                    ProfileCardItem(label="学习阶段", value=profile.learning_stage, source="profile", status="stable", confidence=0.9),
                    ProfileCardItem(label="关注学科", value="、".join(profile.subjects) or "待完善", source="profile", status="default"),
                    ProfileCardItem(label="历史会话", value=f"{len(self.store.list_sessions(self.user_id))} 个", source="qa", status="confirmed"),
                ],
            ),
            ProfileCard(
                id="preferences",
                title="学习偏好",
                subtitle="从问答和资源使用中持续推断",
                kind="preferences",
                items=[
                    # 空值统一显示"未知"，不要留白。
                    # StudentProfile 里 learning_style 默认 ""、language_style 默认
                    # "未知"，两个字段默认值不一致，页面上就是一条空白一条"未知"，
                    # 看着像渲染坏了。这里只在**展示层**兜底，不改画像文本本身
                    # （改默认值会把"未知"写进给大模型的提示词）。
                    ProfileCardItem(label="学习风格", value=profile.learning_style or "未知", source="profile", status="stable"),
                    ProfileCardItem(label="语言风格", value=profile.language_style or "未知", source="profile", status="stable"),
                    *[
                        ProfileCardItem(label="资源偏好", value=value, source=source, status="inferred", confidence=0.66)
                        for value, source in list(preferences.items())[:2]
                    ],
                ],
            ),
            ProfileCard(
                id="knowledge",
                title="知识掌握度",
                subtitle="画像、测评和自适应证据的综合估计",
                kind="knowledge",
                items=mastery_items,
            ),
            ProfileCard(
                id="weak_points",
                title="薄弱知识点与风险",
                subtitle="按掌握度和测评证据排序",
                kind="weak_points",
                items=weak_items,
            ),
            ProfileCard(
                id="topics",
                title="关注主题与兴趣",
                subtitle="来自问答、测评、路径和资源生成",
                kind="topics",
                items=[],
                tags=top_topics,
            ),
            ProfileCard(
                id="activity",
                title="最近学习活动",
                subtitle="最近发生的学习证据",
                kind="activity",
                items=[
                    ProfileCardItem(
                        label=activity.title,
                        value=activity.detail,
                        source=activity.source,
                        status="confirmed",
                        confidence=0.75,
                    )
                    for activity in activities[:5]
                ],
            ),
        ]

    def build_dashboard(self) -> ProfileDashboardResponse:
        """构建档案页所需的完整聚合数据。"""
        profile_text = self.store.get_profile(self.user_id)
        try:
            profile = StudentProfile.from_text(profile_text)
        except Exception:
            profile = StudentProfile()

        state = self._load_state()
        history = self.assessment_store.get_history(limit=20)
        signals = state.get("signals", [])
        topics = self._topic_counter(signals)
        preferences = self._preference_values(signals)
        mastery = self._mastery(profile, history, signals)
        weak_points = self._weak_points(profile, history, signals)
        activities = self._activities(state, history, profile)
        update_log = [entry for entry in activities if entry.source in {"qa", "assessment", "path", "resource"}]
        latest_topic = topics.most_common(1)[0][0] if topics else (profile.subjects[0] if profile.subjects else "待完善")
        mastery_avg = sum(mastery.values()) / len(mastery) if mastery else 0.0
        # 完整度 = 有数据的维度数 / 维度总数。
        #
        # 旧实现是 `min(100, 42 + 证据源种类数 * 12)`：凭空给 42% 的底数，
        # 于是刚注册、什么都没做的新账号也显示 54% —— 这是编出来的数字。
        # 现在改为按"六个画像维度里究竟有几个真的填上了"如实计算：
        # 全空就是 0%，每多一个真实维度就多一份，含义可解释、也不会骗人。
        sessions = self.store.list_sessions(self.user_id)
        dimensions = (
            bool((profile_text or "").strip()),   # 画像文本
            bool(profile.subjects),               # 关注学科
            bool(signals),                        # 学习行为信号
            bool(history),                        # 测评记录
            bool(mastery),                        # 知识掌握度
            bool(sessions),                       # 问答会话
        )
        completeness = round(sum(1 for filled in dimensions if filled) / len(dimensions) * 100)

        cards = self._cards(profile, mastery, weak_points, topics, preferences, activities)
        return ProfileDashboardResponse(
            user_id=self.user_id,
            identity={
                # 不要回退成 user_id：那是一串 uuid4 十六进制，当人名显示毫无意义。
                # 留空让前端用登录用户名兜底（见 ProfilePage 的 displayName）。
                # display_name 由调用方（路由层，知道认证用户名）覆盖写入。
                "display_name": "",
                "learning_stage": profile.learning_stage,
                "subjects": profile.subjects,
                "last_active": activities[0].timestamp if activities else "",
            },
            summary={
                "mastery_avg": round(mastery_avg * 100, 1),
                "weak_point_count": len(weak_points),
                "topic_count": len(topics),
                "conversation_count": len(sessions),
                "profile_completeness": completeness,
                "latest_topic": latest_topic,
            },
            cards=cards,
            knowledge={
                "labels": list(mastery.keys()),
                "values": [round(value * 100, 1) for value in mastery.values()],
            },
            activities=activities,
            update_log=update_log,
        )
