"""
报告生成器 — 聚合 PathStore、AssessmentStore、StudentProfile 数据为统一报告。

原则：**没有真实证据的图一律留空**（radar/pie 为 None），由前端渲染"暂无数据"。
这里曾经有一组 DEFAULT_RADAR / DEFAULT_PIE（"Python 基础 65%、数据结构 45%…
动态规划 3、图论 2…"）。它会在新用户没有任何学习记录时被当作该用户的
真实知识掌握度与薄弱点分布返回并展示，属于凭空编造的学习者特征。
"""
from dataclasses import dataclass, field


@dataclass
class ReportData:
    total_hours: float = 0.0
    completed_nodes: int = 0
    avg_accuracy: float = 0.0
    last_topic: str = ""
    radar: dict | None = None
    line: dict | None = None
    pie: dict | None = None
    suggestions: list = field(default_factory=list)
    profile: dict | None = None
    has_data: bool = False


class ReportBuilder:
    def __init__(self, user_id: str):
        from db.vector_store import get_store
        from core.path_store import PathStore
        from core.assessment_store import AssessmentStore
        from schemas.profile import StudentProfile
        from core.learning_time_service import LearningTimeService

        store = get_store()
        self._user_id = user_id
        self._path_store = PathStore(store, user_id)
        self._assess_store = AssessmentStore(store, user_id)
        self._learning_time = LearningTimeService(user_id, store=store)

        profile_text = store.get_profile(user_id)
        try:
            self._profile = StudentProfile.from_text(profile_text)
        except Exception:
            self._profile = StudentProfile()

    def build(self) -> ReportData:
        result = ReportData()

        path = self._path_store.get_path()
        if path:
            for node in path.nodes:
                if node.status == "completed":
                    result.completed_nodes += 1
                    dur = node.duration or "0分钟"
                    try:
                        result.total_hours += float(''.join(c for c in dur if c.isdigit() or c == '.')) / 60
                    except (ValueError, AttributeError):
                        pass
            result.total_hours = round(result.total_hours, 1)

        learning_summary = self._learning_time.summary()
        result.total_hours = learning_summary["total_hours"]
        if learning_summary["total_seconds"] > 0:
            result.has_data = True

        history = self._assess_store.get_history(limit=20)
        if history:
            result.has_data = True
            result.last_topic = history[0].get("topic", "")

            percentages = [h.get("percentage", 0) for h in history if h.get("percentage") is not None]
            result.avg_accuracy = round(sum(percentages) / len(percentages), 1) if percentages else 0.0

            line_labels = []
            line_values = []
            for h in reversed(history):
                ts = h.get("timestamp", "")[:10]
                pct = h.get("percentage", 0)
                line_labels.append(ts or h.get("topic", ""))
                line_values.append(pct)
            result.line = {"labels": line_labels, "values": line_values}

            wp_count: dict[str, int] = {}
            for h in history:
                for wp in h.get("weak_points", []):
                    if isinstance(wp, dict):
                        name = wp.get("knowledge_point", wp.get("name", ""))
                    else:
                        name = str(wp)
                    if name:
                        wp_count[name] = wp_count.get(name, 0) + 1
            pie_labels = list(wp_count.keys())
            pie_values = list(wp_count.values())
            if pie_labels:
                result.pie = {"labels": pie_labels, "values": pie_values}

            result.suggestions = history[0].get("suggestions", [])

        if self._profile.knowledge_mastery:
            result.radar = {
                "labels": list(self._profile.knowledge_mastery.keys()),
                "values": [v * 100 for v in self._profile.knowledge_mastery.values()]
            }
        elif history:
            latest = history[0]
            labels = []
            values = []
            for wp in latest.get("weak_points", []):
                if isinstance(wp, dict):
                    # 缺 score 的条目直接跳过：原先默认填 50，等于凭空给出
                    # 一个"中等掌握度"的分数，会污染雷达图。
                    score = wp.get("score")
                    if not isinstance(score, (int, float)):
                        continue
                    labels.append(wp.get("knowledge_point", wp.get("name", "")))
                    values.append(score)
            if labels:
                result.radar = {"labels": labels, "values": values}

        # 没有真实证据就留空（原实现在这里回填 DEFAULT_RADAR / DEFAULT_PIE）。

        result.profile = {
            "learning_stage": self._profile.learning_stage,
            "subjects": self._profile.subjects,
            "weak_points": self._profile.weak_points,
            "learning_style": self._profile.learning_style,
            "language_style": self._profile.language_style,
            "knowledge_mastery": self._profile.knowledge_mastery,
        }

        return result
