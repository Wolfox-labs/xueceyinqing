"""自适应知识图谱：合并「种子/配置图谱」与「真实学习路径」。

为什么需要它：
    _ADAPTIVE_GRAPH 原先硬编码在 api_server/main.py 里，只有 9 个 Python
    知识点；而真实使用记录下来的知识点是操作系统、计算机网络、算法等
    （实测库内 30 个知识点与该图谱精确匹配数为 0），于是 KnowledgeNode 的
    importance 与 prerequisites 全部退化为默认值，"知识图谱 + 前置依赖"
    这条设计在真实数据上是空转的。

图谱来源（后者覆盖前者）：
    1. 内置种子图谱：Python 入门 9 个节点，保持向后兼容；
    2. runtime/adaptive_graph.json：使用者可为本学科提供节点与别名；
    3. 该用户已生成的学习路径：prerequisites 取自节点的 deps（真实数据），
       节点名取 knowledge_point，回退 title。

诚实声明：
    importance 没有真实测量信号。除配置文件显式给出外一律取中性 0.5，
    即该项不产生排序差异——不再用手写的高重要度数字冒充测量结果。
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

from core.adaptive_engine import KnowledgeNode

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "runtime" / "adaptive_graph.json"

NEUTRAL_IMPORTANCE = 0.5

# Python 入门种子图谱（沿用历史内置值，仅供向后兼容）。
# 需要其他学科请写 runtime/adaptive_graph.json。
SEED_NODES: tuple[tuple[str, float, tuple[str, ...]], ...] = (
    ("变量与类型", 0.80, ()),
    ("函数", 0.90, ("变量与类型",)),
    ("列表与迭代", 0.82, ("变量与类型",)),
    ("面向对象", 0.88, ("函数", "变量与类型")),
    ("异常处理", 0.68, ("函数",)),
    ("算法基础", 0.95, ("函数", "列表与迭代")),
    ("动态规划", 0.92, ("算法基础",)),
    ("图搜索", 0.86, ("算法基础", "列表与迭代")),
    ("工程实践", 0.72, ("面向对象", "异常处理")),
)


def seed_graph() -> dict[str, KnowledgeNode]:
    """内置种子图谱。"""
    return {
        name: KnowledgeNode(name=name, importance=importance, prerequisites=prereqs)
        for name, importance, prereqs in SEED_NODES
    }


def _field(node: Any, name: str, default: Any = None) -> Any:
    if isinstance(node, Mapping):
        return node.get(name, default)
    return getattr(node, name, default)


def _clean_terms(values: Any) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple, set)):
        return ()
    cleaned = [str(item).strip() for item in values if str(item).strip()]
    return tuple(dict.fromkeys(cleaned))


def load_config(path: Path | str | None = None) -> dict:
    """读取 runtime/adaptive_graph.json；缺失或损坏时返回空配置。"""
    target = Path(path) if path else CONFIG_PATH
    if not target.is_file():
        return {}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("自适应图谱配置读取失败 %s: %s", target, exc)
        return {}
    return data if isinstance(data, dict) else {}


def load_configured_graph(path: Path | str | None = None) -> dict[str, KnowledgeNode]:
    """从配置读取图谱节点。

    配置格式::

        {
          "nodes": {
            "TCP 三次握手": {"importance": 0.7, "prerequisites": ["网络协议分层"]}
          },
          "aliases": {"TCP 三次握手": ["握手", "SYN"]}
        }
    """
    raw_nodes = load_config(path).get("nodes") or {}
    if not isinstance(raw_nodes, Mapping):
        return {}
    graph: dict[str, KnowledgeNode] = {}
    for name, raw in raw_nodes.items():
        key = str(name).strip()
        if not key:
            continue
        if not isinstance(raw, Mapping):
            continue
        try:
            importance = float(raw.get("importance", NEUTRAL_IMPORTANCE))
        except (TypeError, ValueError):
            importance = NEUTRAL_IMPORTANCE
        graph[key] = KnowledgeNode(
            name=key,
            importance=min(1.0, max(0.0, importance)),
            prerequisites=_clean_terms(raw.get("prerequisites")),
        )
    return graph


def load_hint_aliases(path: Path | str | None = None) -> dict[str, tuple[str, ...]]:
    """读取可选的手工别名（配置里的 aliases 段），用于补充自动切分。"""
    raw = load_config(path).get("aliases") or {}
    if not isinstance(raw, Mapping):
        return {}
    aliases: dict[str, tuple[str, ...]] = {}
    for name, terms in raw.items():
        key = str(name).strip()
        cleaned = _clean_terms(terms)
        if key and cleaned:
            aliases[key] = cleaned
    return aliases


def graph_from_path_nodes(nodes: Iterable[Any] | None) -> dict[str, KnowledgeNode]:
    """从学习路径节点推导图谱。

    节点名取 knowledge_point（回退 title）；prerequisites 由 deps 指向的
    节点名构成。这些是用户真实生成过的路径数据，不是猜的。
    """
    items = [item for item in (nodes or []) if item is not None]
    if not items:
        return {}

    def key_of(node: Any) -> str:
        return str(_field(node, "knowledge_point") or _field(node, "title") or "").strip()

    by_id: dict[str, str] = {}
    for node in items:
        node_id = str(_field(node, "id") or "").strip()
        key = key_of(node)
        if node_id and key:
            by_id[node_id] = key

    graph: dict[str, KnowledgeNode] = {}
    for node in items:
        key = key_of(node)
        if not key:
            continue
        prereqs: list[str] = []
        for dep in _field(node, "deps") or ():
            mapped = by_id.get(str(dep).strip())
            if mapped and mapped != key:
                prereqs.append(mapped)
        graph[key] = KnowledgeNode(
            name=key,
            importance=NEUTRAL_IMPORTANCE,
            prerequisites=tuple(dict.fromkeys(prereqs)),
        )
    return graph


def build_graph(
    path_nodes: Iterable[Any] | None = None,
    *,
    config_path: Path | str | None = None,
) -> dict[str, KnowledgeNode]:
    """种子图谱 → 配置图谱 → 学习路径节点（不覆盖已存在的节点）。"""
    graph = seed_graph()
    graph.update(load_configured_graph(config_path))
    for key, node in graph_from_path_nodes(path_nodes).items():
        graph.setdefault(key, node)
    return graph


# ── 问题 ↔ 知识点匹配 ──────────────────────────────────
#
# 原实现是一张手写的 Python 术语别名表（变量/函数/列表…），对操作系统、
# 计算机网络等真实知识点完全命中不了，导致自适应提示注入不进去。
# 现在一律从知识点名称自身切分，任何学科都能用；配置里的 aliases 作为补充。

_HINT_STOPWORDS = frozenset({
    "对比", "基础", "概念", "机制", "原理", "入门", "进阶", "综合", "概述",
    "与", "和", "及", "或", "的", "等", "问题", "方法", "使用", "实现", "应用",
    "相互", "关系", "特点", "特性", "作用", "总结",
})

_HINT_SPLIT = re.compile(
    r"[^\w\u4e00-\u9fff]+"                                        # 标点、空白
    r"|(?<=[\u4e00-\u9fff])(?:与|和|及|或|、)(?=[\u4e00-\u9fff])"  # 中文连词
)


def knowledge_point_terms(name: str) -> tuple[str, ...]:
    """把知识点名称切成可用于匹配问题的词条。"""
    text = (name or "").strip()
    if not text:
        return ()
    terms: list[str] = []
    for part in _HINT_SPLIT.split(text):
        part = (part or "").strip()
        if len(part) < 2 or part in _HINT_STOPWORDS:
            continue
        terms.append(part)
    compact = re.sub(r"[^\w\u4e00-\u9fff]+", "", text)
    if len(compact) >= 2:
        terms.append(compact)
    return tuple(dict.fromkeys(terms))


def match_terms(name: str, aliases: Mapping[str, Iterable[str]] | None = None) -> tuple[str, ...]:
    """知识点名称的自动词条，加上配置中为该知识点提供的手工别名。"""
    auto = knowledge_point_terms(name)
    extra = _clean_terms((aliases or {}).get(name))
    return tuple(dict.fromkeys(auto + extra))
