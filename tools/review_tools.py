"""
审核工具 — 供 Reviewer Agent 调用。

- ReportIssueTool：上报问题到 runtime/logs/review_log.jsonl
- WithdrawOutputTool：撤回/拦截输出，阻止内容展示给用户
- ReviewContext：撤回状态容器，消除模块级全局状态
"""
import json
import logging
import threading
import warnings
from datetime import datetime
from pathlib import Path
from crewai.tools import BaseTool

logger = logging.getLogger(__name__)


# ── 审核判词契约 ───────────────────────────────────────
#
# 审核任务的输出契约（crews/generate.py 的 review_task 同样约定）：
#     审核结果：通过。<一句简评>
#     审核结果：不通过。<具体理由>
#
# 交付与否由 WithdrawOutputTool 决定，判词用于审计、实验统计与兜底拦截。
# "不通过"必须在"通过"之前匹配，否则会被后者的子串命中。

VERDICT_PASS = "pass"
VERDICT_FAIL = "fail"
VERDICT_UNKNOWN = "unknown"
#: 判词为"不通过"，但理由只是措辞/深度这类**可发布**的问题。
#: 单独成一档：内容照常交付，问题照样上报，避免把可用内容整篇丢掉。
VERDICT_PASS_WITH_NOTES = "pass_with_notes"

_VERDICT_FAIL_MARKERS = ("审核结果：不通过", "审核结果:不通过", "审核结果：不合格")
_VERDICT_PASS_MARKERS = ("审核结果：通过", "审核结果:通过", "审核结果：合格")

#: 把这些词视为"必须拦截"的硬问题。只有命中它们才真的撤回内容。
_BLOCKING_MARKERS = (
    "critical",
    "严重事实错误",
    "事实性错误",
    "完全跑题",
    "违规",
    "不当内容",
    "胡言乱语",
    "幻觉",
)


def is_blocking_reason(reason: str) -> bool:
    """判断"不通过"的理由是否严重到必须拦截整篇内容。

    背景（真实故障）：审核提示词把"建议、需注意、必须修复"都归到"不通过"，
    而旧代码只要看到"不通过"就整篇撤回——于是一句"这句表述有点绝对"就能让
    一次 60 多秒的生成成果全部作废，用户什么也拿不到。
    现在只有硬问题（严重错误/跑题/违规/幻觉）才拦截，其余按"通过但有意见"交付。
    """
    if not reason:
        return False
    text = reason.replace(" ", "")
    return any(marker in text for marker in _BLOCKING_MARKERS)


def parse_verdict(text: str) -> str:
    """从审核 Agent 的输出里解析判词，认不出来时返回 VERDICT_UNKNOWN。"""
    if not text:
        return VERDICT_UNKNOWN
    compact = text.replace(" ", "")
    if any(marker in compact for marker in _VERDICT_FAIL_MARKERS):
        return VERDICT_FAIL
    if any(marker in compact for marker in _VERDICT_PASS_MARKERS):
        return VERDICT_PASS
    return VERDICT_UNKNOWN


# ── ReviewContext ──────────────────────────────────────

class ReviewContext:
    """撤回状态与审核判词容器，替代模块级全局变量。"""

    def __init__(self):
        self._withdrawn = False
        self._reason = ""
        self._verdict = VERDICT_UNKNOWN

    def withdraw(self, reason: str):
        self._withdrawn = True
        self._reason = reason
        self._verdict = VERDICT_FAIL

    def is_withdrawn(self) -> bool:
        return self._withdrawn

    def reason(self) -> str:
        return self._reason

    def set_verdict(self, verdict: str, reason: str = ""):
        """记录解析出的判词，并决定是否拦截交付。

        拦截规则（改动原因见 is_blocking_reason）：
          · WithdrawOutputTool 被显式调用 -> 拦截（工具是权威信号，最先判断）；
          · 判词"不通过" + 理由是硬问题（严重错误/跑题/违规/幻觉）-> 拦截；
          · 判词"不通过" + 理由只是措辞、深度、结构建议 -> 降级为
            "通过但有意见"，内容照常交付，意见保留在 review_text 里给用户看。
        """
        if not verdict:
            return
        if self._withdrawn:
            # 已经通过工具明确撤回：工具是权威信号，不能降级。
            return
        if verdict == VERDICT_FAIL:
            if is_blocking_reason(reason):
                self._verdict = VERDICT_FAIL
                self._withdrawn = True
                self._reason = self._reason or "内容存在严重问题，已拦截"
            else:
                self._verdict = VERDICT_PASS_WITH_NOTES
            return
        self._verdict = verdict

    def verdict(self) -> str:
        return self._verdict

    def reset(self):
        self._withdrawn = False
        self._reason = ""
        self._verdict = VERDICT_UNKNOWN


# ── 线程局部默认上下文（向后兼容模块级函数和硬编码工具）──

_thread_local = threading.local()

def _get_default_context():
    if not hasattr(_thread_local, 'review_context'):
        _thread_local.review_context = ReviewContext()
    return _thread_local.review_context


# ── 已弃用的模块级函数 ────────────────────────────────

def reset_withdraw():
    """[已弃用] 每个请求前重置撤回信号。请使用 ReviewContext.reset()。"""
    warnings.warn(
        "reset_withdraw() is deprecated, use ReviewContext.reset() instead",
        DeprecationWarning, stacklevel=2
    )
    _get_default_context().reset()


def is_withdrawn() -> bool:
    """[已弃用] 检查是否需要撤回当前输出。请使用 ReviewContext.is_withdrawn()。"""
    warnings.warn(
        "is_withdrawn() is deprecated, use ReviewContext.is_withdrawn() instead",
        DeprecationWarning, stacklevel=2
    )
    return _get_default_context().is_withdrawn()


def get_withdraw_reason() -> str:
    """[已弃用] 获取撤回原因。请使用 ReviewContext.reason()。"""
    warnings.warn(
        "get_withdraw_reason() is deprecated, use ReviewContext.reason() instead",
        DeprecationWarning, stacklevel=2
    )
    return _get_default_context().reason()


# ── 日志路径 ───────────────────────────────────────────
#
# 这里曾写作 ".../runtime/logs/runtime/logs/review_log.jsonl"，多出一层
# runtime/logs，open() 必然抛 FileNotFoundError，审核问题全部丢失。

_LOG_PATH = Path(__file__).parent.parent / "runtime" / "logs" / "review_log.jsonl"


# ── 工具 1：上报问题 ───────────────────────────────────

class ReportIssueTool(BaseTool):
    name: str = "ReportIssueTool"
    description: str = (
        "上报审核中发现的问题。调用此工具可以将问题记录到日志文件。"
        "参数 severity: 严重度 — low（建议）/ medium（需注意）/ high（必须修复）/ critical（阻止输出）。"
        "参数 description: 问题的具体描述。"
    )

    def _run(self, severity: str, description: str) -> str:
        entry = {
            "timestamp": datetime.now().isoformat(),
            "severity": severity,
            "description": description,
        }
        try:
            _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            return f"问题已记录（严重度: {severity}）"
        except Exception as e:
            logger.exception("审核问题日志写入失败: %s", _LOG_PATH)
            return f"日志写入失败: {e}"


# ── 工具 2：撤回输出 ───────────────────────────────────

class WithdrawOutputTool(BaseTool):
    name: str = "WithdrawOutputTool"
    description: str = (
        "撤回/拦截当前生成的内容，阻止其展示给用户。"
        "当内容存在严重事实错误、不当内容、或完全跑题时调用此工具。"
        "参数 reason: 撤回原因，会展示给用户。"
    )

    def __init__(self, review_context=None, **kwargs):
        super().__init__(**kwargs)
        object.__setattr__(
            self, '_ctx',
            review_context if review_context is not None else _get_default_context()
        )

    def _run(self, reason: str) -> str:
        self._ctx.withdraw(reason)
        return f"输出已撤回。原因: {reason}"
