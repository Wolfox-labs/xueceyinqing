"""
Token 用量追踪 — 格式化输出 crew.usage_metrics
"""


def format_metrics(metrics) -> str:
    if metrics is None:
        return ""
    try:
        return (
            f"\n{'─' * 40}\n"
            f"Token 用量 | 总计: {metrics.total_tokens:,}"
            f"  输入: {metrics.prompt_tokens:,}"
            f"  输出: {metrics.completion_tokens:,}"
            f"  请求: {metrics.successful_requests} 次"
            f"\n{'─' * 40}"
        )
    except AttributeError:
        return ""
