"""面向学习者的短摘要，只处理任务公开产出，不读取模型推理流。"""

from __future__ import annotations

import re
from typing import Any, Mapping


def agent_trigger_rules(config: Mapping[str, Any]) -> dict[str, Any]:
    """学习者可读的触发规则，不暴露实验配置的写入接口。"""
    return {key: config[key] for key in (
        "critic_enabled", "quiz_agent_enabled", "reviewer_enabled",
        "orchestration_mode", "deliberate_threshold", "max_rounds",
    )}


def public_summary(text: str, *, max_items: int = 3, max_chars: int = 110) -> list[str]:
    """提取有长度上限的纯文本要点，排除推理标签和工具记录。"""
    text = re.sub(r"<(think|analysis)\b[^>]*>.*?(?:</\1\s*>|$)", "", text or "", flags=re.I | re.S)
    points: list[str] = []
    for line in re.split(r"\n+", text):
        line = re.sub(r"^\s*(?:[-*#]+|\d+[.、)])\s*", "", line).strip()
        if not line or re.match(r"(?:Thought|Action|Action Input|Observation)\s*:", line, flags=re.I):
            continue
        line = re.sub(r"[*`#]", "", line)
        points.append(line if len(line) <= max_chars else line[:max_chars - 1] + "…")
        if len(points) >= max_items:
            break
    return points
