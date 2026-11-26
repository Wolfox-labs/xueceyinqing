"""
用户画像的数据结构定义。
"""
import json
import re
from pydantic import BaseModel, Field


class StudentProfile(BaseModel):
    """学习者画像。

    默认值一律表示"未知/未采集"，不再预填任何看起来像测量结果的数字或结论。
    原先的默认值（学习阶段"入门"、薄弱环节 5 项、6 个知识掌握度分数）会在
    用户还没有画像时被当作真实数据展示，并驱动自适应引擎的推荐与提示词，
    属于凭空编造的学习者特征。
    """
    learning_stage: str = Field(
        default="未知",
        description="学习阶段，如\"入门\"/\"进阶\"/\"高级\"；未知时不要猜"
    )
    subjects: list[str] = Field(
        default_factory=list,
        description="关注学科"
    )
    weak_points: list[str] = Field(
        default_factory=list,
        description="薄弱环节（知识点名称）；必须来自真实测评或对话证据"
    )
    learning_style: str = Field(
        default="",
        description="学习偏好，如\"visual\"/\"auditory\"/\"reading\"/\"kinesthetic\"；未知时留空"
    )
    language_style: str = Field(
        default="未知",
        description="语言风格偏好，如\"简洁\"/\"详细\"；未知时不要猜"
    )
    knowledge_mastery: dict[str, float] = Field(
        default_factory=dict,
        description="知识掌握度，{知识点名: 0.0~1.0}；必须来自真实答题证据"
    )

    @classmethod
    def from_text(cls, text: str) -> "StudentProfile":
        text = text.strip()
        if text.startswith("{"):
            try:
                data = json.loads(text)
                return cls.model_validate(data)
            except (json.JSONDecodeError, Exception):
                pass

        data: dict = {}
        in_mastery = False
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue

            if in_mastery and line.startswith(("-", "•")):
                body = line.lstrip("-•").strip()
                sep = "：" if "：" in body else ":" if ":" in body else ""
                if sep:
                    name, _, raw_score = body.partition(sep)
                    try:
                        mastery = data.setdefault("knowledge_mastery", {})
                        mastery[name.strip()] = float(raw_score.strip())
                    except (TypeError, ValueError):
                        pass
                continue

            if "：" in line or ":" in line:
                sep = "：" if "：" in line else ":"
                key, _, value = line.partition(sep)
                key = key.strip()
                value = value.strip()
                if any(kw in key for kw in ("学习阶段", "阶段")):
                    data["learning_stage"] = value
                    in_mastery = False
                elif any(kw in key for kw in ("学科", "主题")):
                    data["subjects"] = [s.strip() for s in re.split(r"[、,，]", value) if s.strip()]
                    in_mastery = False
                elif any(kw in key for kw in ("薄弱", "弱点")):
                    data["weak_points"] = [s.strip() for s in re.split(r"[、,，]", value) if s.strip()]
                    in_mastery = False
                elif any(kw in key for kw in ("学习偏好", "偏好")):
                    data["learning_style"] = value
                    in_mastery = False
                elif any(kw in key for kw in ("语言风格", "风格")):
                    data["language_style"] = value
                    in_mastery = False
                elif "知识掌握" in key or "掌握度" in key:
                    in_mastery = True
                    data.setdefault("knowledge_mastery", {})
                else:
                    in_mastery = False
            else:
                in_mastery = False
        return cls(**data)

    @classmethod
    def to_text(cls, profile: "StudentProfile") -> str:
        parts = []
        parts.append(f"学习阶段：{profile.learning_stage}")
        parts.append(f"关注学科：{'、'.join(profile.subjects) if profile.subjects else '暂无'}")
        parts.append(f"薄弱环节：{'、'.join(profile.weak_points) if profile.weak_points else '暂无'}")
        parts.append(f"学习偏好：{profile.learning_style}")
        parts.append(f"语言风格：{profile.language_style}")
        if profile.knowledge_mastery:
            parts.append("知识掌握度：")
            for k, v in profile.knowledge_mastery.items():
                parts.append(f"  - {k}: {v:.2f}")
        else:
            parts.append("知识掌握度：暂无")
        return "\n".join(parts)
