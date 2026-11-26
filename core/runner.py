"""
Crew 执行器 — 兼容 CrewAI 的普通输出与流式输出。

职责：
- 普通模式：读取 CrewOutput.raw 或 str(CrewOutput)
- 流式模式：逐条读取 StreamChunk.content 并回调
- 两种模式都统一返回 CrewResult

审核隔离：
    审核 Agent 的产出不是交付内容。调用方通过 exclude_agent_roles 指定需要
    隔离的 Agent 角色后，这些角色的文本会单独放进 CrewResult.review_text，
    既不会进入 raw，也不会经 on_chunk 流出，避免"审核结果：通过。"这类判词
    被拼进交付给用户的资源里。

本模块刻意不 import crewai，靠 getattr 鸭子类型读取 StreamChunk 字段，
以便 core 层可以在不初始化 LLM 框架的情况下被导入与单测。
"""
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence


@dataclass
class CrewResult:
    """一次 Crew 执行的完整产出。"""

    raw: str
    metrics: Any = field(default=None)
    review_text: str = ""
    agent_roles: tuple[str, ...] = ()
    task_count: int = 0


@dataclass
class PipelineResult:
    """一次 CrewPipeline 执行的完整产出。

    刻意定义在本模块（而非 core.pipeline）：core.pipeline 会经
    tools.review_tools 拉起 crewai，而 API 层只需要这个结果类型来做 SSE 哨兵
    与 isinstance 判断。放在这里让"不初始化 LLM 框架也能导入 API 层"成立。
    core.pipeline 仍然再导出它，保持既有导入路径可用。
    """

    raw: str
    withdrawn: bool
    reason: str
    metrics: Any = field(default=None)
    verdict: str = "unknown"
    review_text: str = ""
    agent_roles: tuple[str, ...] = ()


def _usage_metrics(crew) -> Any:
    try:
        return crew.usage_metrics
    except Exception:
        return None


def extract_token_usage(metrics: Any) -> Optional[int]:
    """从 CrewAI usage_metrics 之类的对象里取总 token 数，取不到返回 None。

    消融实验原先用"字符数 // 4"估算 token，而真实用量其实就在 CrewResult.metrics
    里。优先用真实值，只有拿不到时才回退估算。
    """
    if metrics is None:
        return None
    if isinstance(metrics, dict):
        for name in ("total_tokens", "total_token_count", "tokens"):
            value = metrics.get(name)
            if isinstance(value, (int, float)) and value > 0:
                return int(value)
        return None
    for name in ("total_tokens", "total_token_count", "tokens"):
        value = getattr(metrics, name, None)
        if isinstance(value, (int, float)) and value > 0:
            return int(value)
    return None


def _extract_text(value: Any) -> str:
    """从 CrewOutput、StreamChunk、字符串或兼容对象中提取文本。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value

    # CrewOutput.raw 是普通 kickoff 的标准文本字段。
    raw = getattr(value, "raw", None)
    if isinstance(raw, str):
        return raw

    content = getattr(value, "content", None)
    if isinstance(content, str):
        return content

    if isinstance(value, dict):
        for key in ("raw", "content", "text", "output"):
            item = value.get(key)
            if isinstance(item, str):
                return item

    if isinstance(value, (tuple, list)):
        return "".join(_extract_text(item) for item in value)

    return str(value)


def _chunk_role(chunk: Any) -> str:
    """读取 StreamChunk 的 agent_role，兼容字段改名。"""
    for name in ("agent_role", "agent_name", "role"):
        role = getattr(chunk, name, None)
        if isinstance(role, str) and role.strip():
            return role.strip()
    return ""


def _is_text_chunk(chunk: Any) -> bool:
    """只接受文本 chunk；tool_call 之类的结构化 chunk 不进正文。

    没有 chunk_type 字段时按文本处理（兼容普通字符串 chunk）。
    """
    chunk_type = getattr(chunk, "chunk_type", None)
    if chunk_type is None:
        return True
    value = getattr(chunk_type, "value", chunk_type)
    return str(value).strip().lower() == "text"


class CrewRunner:
    """无状态的 Crew 执行器。同一实例可重复调用 run()。"""

    @staticmethod
    def run(
        crew,
        on_chunk: Optional[Callable[[str], None]] = None,
        *,
        exclude_agent_roles: Sequence[str] = (),
    ) -> CrewResult:
        """执行 Crew，兼容 stream=True 和 stream=False 两种返回类型。

        Args:
            crew: 待执行的 Crew。
            on_chunk: 交付内容的回调，**逐块触发**（保持流式语义）。被隔离
                Agent 的文本不会经它流出。
            exclude_agent_roles: 需要隔离的 Agent 角色（通常是审核助手）。
                其文本进入 CrewResult.review_text，不进入 raw / on_chunk。

        Returns:
            CrewResult(raw, metrics, review_text, agent_roles, task_count)
        """
        excluded = {role.strip() for role in exclude_agent_roles if role and role.strip()}
        result = crew.kickoff()

        # stream=False 时 CrewAI 返回 CrewOutput；不能再按 chunk 迭代。
        # 这类 Crew 是单任务或不存在审核任务，raw 即交付内容。
        if isinstance(result, str) or hasattr(result, "raw"):
            raw = _extract_text(result)
            if on_chunk and raw:
                on_chunk(raw)
            return CrewResult(raw=raw, metrics=_usage_metrics(crew))

        # stream=True 时返回 CrewStreamingOutput，逐 chunk 处理。
        if hasattr(result, "__iter__"):
            kept: list[str] = []
            review_parts: list[str] = []
            roles: list[str] = []
            task_indexes: set[int] = set()

            for chunk in result:
                if not _is_text_chunk(chunk):
                    continue
                chunk_text = _extract_text(chunk)
                if chunk_text in ("", "{}"):
                    continue

                role = _chunk_role(chunk)
                if role and role not in roles:
                    roles.append(role)
                task_index = getattr(chunk, "task_index", None)
                if isinstance(task_index, int):
                    task_indexes.add(task_index)

                if role and role in excluded:
                    review_parts.append(chunk_text)
                    continue

                kept.append(chunk_text)
                # 逐块回调，保持原有流式语义：调用方可以边收边渲染。
                if on_chunk:
                    on_chunk(chunk_text)

            return CrewResult(
                raw="".join(kept),
                metrics=_usage_metrics(crew),
                review_text="".join(review_parts),
                agent_roles=tuple(roles),
                task_count=len(task_indexes),
            )

        # 最后的兜底：兼容第三方返回的自定义对象。
        raw = _extract_text(result)
        if on_chunk and raw:
            on_chunk(raw)
        return CrewResult(raw=raw, metrics=_usage_metrics(crew))
