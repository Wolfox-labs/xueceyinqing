"""
ChromaDB 实现层 — 实现 StorageBackend 接口。

管理三个 collection: knowledge_base / user_profiles / conversations。
首次运行时自动索引 knowledge/ 目录下的文本文档。
"""
import os

os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

import chromadb
import hashlib
import json
import logging
import re
from collections import Counter
from pathlib import Path
from typing import Optional

from db.interface import StorageBackend, ConversationRecord
from db.kv_store import SQLiteKVStore

logger = logging.getLogger(__name__)

# 使用绝对路径，避免 uv run 等不同工作目录下找不到数据库文件
_PROJECT_ROOT = Path(__file__).parent.parent
CHROMA_PATH = _PROJECT_ROOT / "runtime" / "chroma_data"
KNOWLEDGE_DIR = _PROJECT_ROOT / "knowledge"

_client: Optional[chromadb.PersistentClient] = None


def _get_client() -> chromadb.PersistentClient:
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    return _client


def _get_collection(name: str):
    return _get_client().get_or_create_collection(name)


def _retrieval_tokens(text: str) -> Counter:
    """中文按字和双字词、英文按单词提取检索特征。"""
    normalized = (text or "").lower()
    tokens = re.findall(r"[a-z0-9_]+", normalized)
    cjk = re.findall(r"[\u4e00-\u9fff]", normalized)
    tokens.extend(cjk)
    tokens.extend("".join(cjk[index:index + 2]) for index in range(max(0, len(cjk) - 1)))
    return Counter(tokens)


def _lexical_rank_documents(documents: list[str], query: str, n_results: int) -> list[str]:
    """轻量词法排序，解决默认英文 embedding 对中文检索不敏感的问题。"""
    query_tokens = _retrieval_tokens(query)
    if not query_tokens:
        return []
    scored = []
    for document in documents:
        doc_tokens = _retrieval_tokens(document)
        overlap = sum(min(count, doc_tokens.get(token, 0)) for token, count in query_tokens.items())
        if overlap:
            length_penalty = 1.0 / (1.0 + len(document) / 1200.0)
            scored.append((overlap * length_penalty, document))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [document for _, document in scored[:n_results]]


def _parse_front_matter(text: str) -> tuple[dict, str]:
    """解析知识卡 YAML 风格 front matter，不引入额外 YAML 依赖。"""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    metadata = {}
    for line in parts[1].splitlines():
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        value = raw_value.strip()
        try:
            if value.startswith("["):
                value = json.loads(value)
            else:
                value = json.loads(value) if value.startswith('"') else value
        except Exception:
            pass
        metadata[key.strip()] = value
    return metadata, parts[2].strip()


def _chunk_markdown(text: str, limit: int = 600) -> list[str]:
    """按段落聚合为 300~600 字片段，优先保留标题上下文。"""
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for paragraph in paragraphs:
        paragraph_len = len(paragraph)
        if current and current_len + paragraph_len > limit:
            chunks.append("\n\n".join(current))
            current = []
            current_len = 0
        current.append(paragraph)
        current_len += paragraph_len
    if current:
        chunks.append("\n\n".join(current))
    return chunks


class ChromaDBStorage(StorageBackend):
    """知识向量使用 ChromaDB，通用业务状态使用 SQLite。"""

    # 词法命中的相关度下限：查询词条中被文档覆盖的比例。低于它即视为"弱命中"，
    # 不能拿来短路向量检索——否则一个共用汉字就能占满 top-n，向量检索几乎
    # 永不触发，展示给用户的"引用来源"也可能是无关文档。
    LEXICAL_MIN_RELEVANCE = 0.15

    def __init__(self) -> None:
        self._kv = SQLiteKVStore()
        # 知识库文档快照缓存：(集合条数, 条目列表)。集合条数变化即失效。
        self._docs_cache: tuple[int | None, list[dict]] | None = None

    # ---- 知识库 ----

    def _knowledge_documents(self) -> list[dict]:
        """知识库文档快照（带缓存）。

        原先每次检索都 collection.get() 把整个集合拉进 Python 再逐条算词法分，
        每次查询都是 O(N) 全量传输。这里按集合条数判断是否失效。
        """
        collection = _get_collection("knowledge_base")
        try:
            count = collection.count()
        except Exception:
            logger.debug("读取知识库条数失败，跳过缓存", exc_info=True)
            count = None
        cached = self._docs_cache
        if cached is not None and count is not None and cached[0] == count:
            return cached[1]

        results = collection.get(include=["documents", "metadatas"])
        docs = results.get("documents") or []
        metas = results.get("metadatas") or []
        entries = [
            {"text": doc, "metadata": meta or {}}
            for doc, meta in zip(docs, metas)
            if doc and (meta or {}).get("type") != "index_version"
        ]
        self._docs_cache = (count, entries)
        return entries

    def _vector_search(self, query: str, n_results: int) -> list[dict]:
        """向量检索。

        与旧实现的区别：它现在会真正参与结果合并。旧实现只在词法命中数
        < n_results 时才调用，而中文单字重合几乎总能凑够 3 条，因此这一路
        实际从未生效——README 宣称的"混合检索"名不副实。
        """
        collection = _get_collection("knowledge_base")
        try:
            result = collection.query(
                query_texts=[query],
                n_results=max(1, n_results),
                include=["documents", "metadatas"],
            )
        except Exception:
            logger.warning("向量检索失败，本次仅返回词法结果", exc_info=True)
            return []
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        return [
            {"text": text, "metadata": meta or {}}
            for text, meta in zip(documents, metadatas)
            if text
        ]

    @staticmethod
    def _diversify(entries: list[dict], n_results: int) -> list[dict]:
        """同一来源文件最多占一个名额，名额不足时再回填。

        原先同一文件的多个片段可以占满 top-3（评测报告里 graph_search.md
        就出现了两次），把其他来源挤掉。回填保证了召回不下降。
        """
        picked: list[dict] = []
        deferred: list[dict] = []
        seen_text: set[str] = set()
        seen_paths: set[str] = set()
        for entry in entries:
            text = entry["text"]
            if text in seen_text:
                continue
            seen_text.add(text)
            path = str((entry.get("metadata") or {}).get("path") or "")
            if path and path in seen_paths:
                deferred.append(entry)
                continue
            if path:
                seen_paths.add(path)
            picked.append(entry)
            if len(picked) >= n_results:
                return picked
        for entry in deferred:
            picked.append(entry)
            if len(picked) >= n_results:
                break
        return picked

    def search_knowledge_details(self, query: str, n_results: int = 3) -> list[dict]:
        entries = self._knowledge_documents()
        query_tokens = _retrieval_tokens(query)
        if not query_tokens:
            return entries[:n_results]

        total_query_tokens = max(1, sum(query_tokens.values()))
        strong: list[dict] = []
        weak: list[dict] = []
        for entry in entries:
            doc_tokens = _retrieval_tokens(entry["text"])
            overlap = sum(
                min(count, doc_tokens.get(token, 0))
                for token, count in query_tokens.items()
            )
            if not overlap:
                continue
            metadata = entry.get("metadata") or {}
            point_tokens = _retrieval_tokens(str(metadata.get("knowledge_point", "")))
            point_overlap = sum(
                min(count, point_tokens.get(token, 0))
                for token, count in query_tokens.items()
            )
            title_bonus = 1.0 + 0.45 * (point_overlap / total_query_tokens)
            length_penalty = 1.0 / (1.0 + len(entry["text"]) / 1200.0)
            relevance = overlap / total_query_tokens
            item = (overlap * length_penalty * title_bonus, entry)
            (strong if relevance >= self.LEXICAL_MIN_RELEVANCE else weak).append(item)

        strong.sort(key=lambda pair: pair[0], reverse=True)
        weak.sort(key=lambda pair: pair[0], reverse=True)
        strong_entries = [entry for _, entry in strong]
        weak_entries = [entry for _, entry in weak]

        if len(strong_entries) >= n_results:
            return self._diversify(strong_entries, n_results)

        # 词法证据不足时才动用向量检索，并让两路结果一起排序：
        # 强词法 > 向量 > 弱词法。弱词法不再挤在向量结果前面。
        merged = strong_entries + self._vector_search(query, n_results) + weak_entries
        return self._diversify(merged, n_results)

    def search_knowledge(self, query: str, n_results: int = 3) -> list[str]:
        return [entry["text"] for entry in self.search_knowledge_details(query, n_results)]

    # ---- 用户画像 ----

    def get_profile(self, user_id: str) -> str:
        value = self._kv.get_text(f"user_{user_id}")
        return value if value else "暂无用户画像信息。"

    def update_profile(self, user_id: str, profile_text: str) -> None:
        self._kv.set_text(f"user_{user_id}", profile_text)

    # ---- 对话记忆 ----

    def save_conversation(self, record: ConversationRecord) -> None:
        collection = _get_collection("conversations")
        meta = {
            "user_id": record.user_id,
            "session_id": record.session_id,
            "turn": record.turn,
            "question": record.question,
            "answer_summary": record.answer_summary,
            "answer_full": record.answer_full,
            "timestamp": record.timestamp or "",
        }
        collection.upsert(
            ids=[record.record_id],
            documents=[record.search_text],
            metadatas=[meta],
        )

    def get_recent_conversations(
        self, user_id: str, session_id: str, current_turn: int, n: int = 5
    ) -> list[ConversationRecord]:
        collection = _get_collection("conversations")
        result: list[ConversationRecord] = []

        if current_turn > n * 10:
            test_turn = 1
            while True:
                rid = f"{user_id}_{session_id}_{test_turn:04d}"
                res = collection.get(ids=[rid])
                if res.get("documents") and res["documents"][0]:
                    test_turn += 1
                else:
                    break
            current_turn = test_turn

        oldest = max(0, current_turn - n)
        for turn in range(current_turn - 1, oldest - 1, -1):
            rid = f"{user_id}_{session_id}_{turn:04d}"
            res = collection.get(ids=[rid])
            docs = res.get("documents", [])
            metas = res.get("metadatas", [])
            if docs and docs[0] and metas:
                meta = metas[0]
                result.append(ConversationRecord(
                    user_id=user_id,
                    session_id=session_id,
                    turn=turn,
                    question=meta.get("question", ""),
                    answer_summary=meta.get("answer_summary", docs[0]),
                    answer_full=meta.get("answer_full", docs[0]),
                    timestamp=meta.get("timestamp", ""),
                ))
        return list(reversed(result))

    def search_conversations(
        self, user_id: str, query: str, n_results: int = 3
    ) -> list[str]:
        collection = _get_collection("conversations")
        results = collection.query(
            query_texts=[query],
            n_results=n_results,
            where={"user_id": user_id},
        )
        docs = results.get("documents", [[]])[0]
        return docs

    # ---- 通用键值存储 ----

    def save_data(self, key: str, data: dict) -> None:
        self._kv.save_data(key, data)

    def get_data(self, key: str) -> dict | None:
        return self._kv.get_data(key)

    def list_data_by_prefix(self, prefix: str) -> list[dict]:
        return self._kv.list_data_by_prefix(prefix)

    # ---- 会话列表 ----

    def list_sessions(self, user_id: str) -> list[dict]:
        # TODO: 大数据量时需迁移到 SQL（ChromaDB 不支持按 metadata 过滤 get）
        collection = _get_collection("conversations")
        results = collection.get()
        metas = results.get("metadatas", [])
        ids = results.get("ids", [])

        sessions: dict[str, dict] = {}
        for meta in metas:
            if not meta or meta.get("user_id") != user_id:
                continue
            sid = meta.get("session_id", "")
            if not sid:
                continue
            ts = meta.get("timestamp", "")
            if sid not in sessions or ts > sessions[sid].get("updatedAt", ""):
                sessions[sid] = {
                    "id": sid,
                    "title": "对话",
                    "updatedAt": ts,
                }

        return list(sessions.values())

    # ---- 题库管理 ----

    def question_bank_add(self, topic: str, question_text: str,
                          meta: dict | None = None) -> str:
        import uuid
        collection = _get_collection("question_bank")
        qid = f"qb_{uuid.uuid4().hex[:8]}"
        metadata = meta or {}
        metadata.setdefault("topic", topic)
        collection.upsert(
            ids=[qid],
            documents=[question_text],
            metadatas=[metadata],
        )
        return qid

    def question_bank_list_topics(self) -> list[str]:
        collection = _get_collection("question_bank")
        results = collection.get()
        topics: set[str] = set()
        for meta in (results.get("metadatas") or []):
            if meta and meta.get("topic"):
                topics.add(meta["topic"])
        return sorted(topics)

    def question_bank_get_by_topic(self, topic: str) -> list[dict]:
        collection = _get_collection("question_bank")
        results = collection.get()
        ids = results.get("ids", [])
        docs = results.get("documents", [])
        metas = results.get("metadatas", [])
        items = []
        for id_, doc, meta in zip(ids, docs, metas):
            if meta and meta.get("topic") == topic:
                items.append({
                    "id": id_,
                    "text": doc,
                    "metadata": meta,
                })
        return items

    def question_bank_delete(self, topic: str) -> int:
        collection = _get_collection("question_bank")
        results = collection.get()
        ids_to_delete = []
        for id_, meta in zip(results.get("ids", []), results.get("metadatas", [])):
            if meta and meta.get("topic") == topic:
                ids_to_delete.append(id_)
        if ids_to_delete:
            collection.delete(ids=ids_to_delete)
        return len(ids_to_delete)


# ---- 全局单例 ----

_store: Optional[ChromaDBStorage] = None


def get_store() -> ChromaDBStorage:
    global _store
    if _store is None:
        _store = ChromaDBStorage()
    return _store


# ---- 启动初始化 ----

KNOWLEDGE_SCHEMA_VERSION = "2"


def _load_knowledge_documents() -> list[dict]:
    documents: list[dict] = []
    paths = sorted(
        path for path in KNOWLEDGE_DIR.glob("**/*.md")
        if "_legacy" not in path.parts and path.name != "manifest.json"
    )
    for path in paths:
        raw = path.read_text(encoding="utf-8")
        meta, body = _parse_front_matter(raw)
        if not body.strip():
            continue
        relative = path.relative_to(KNOWLEDGE_DIR).as_posix()
        chunks = _chunk_markdown(body)
        for index, chunk in enumerate(chunks):
            doc_id = "kb_" + hashlib.sha1(f"{relative}:{index}:{chunk[:80]}".encode("utf-8")).hexdigest()
            documents.append({
                "id": doc_id,
                "text": chunk,
                "metadata": {
                    "type": "knowledge",
                    "source": str(meta.get("source", relative)),
                    "source_url": str(meta.get("source_url", "")),
                    "module": str(meta.get("module", "")),
                    "title": str(meta.get("title", path.stem)),
                    "knowledge_point": str(meta.get("knowledge_point", path.stem)),
                    "difficulty": str(meta.get("difficulty", "")),
                    "prerequisites": json.dumps(meta.get("prerequisites", []), ensure_ascii=False),
                    "path": relative,
                    "chunk_index": index,
                },
            })
    return documents


def init_knowledge_base():
    """初始化或升级结构化知识库；通用业务状态已迁移到 SQLite。"""
    client = _get_client()
    try:
        client.delete_collection("user_profiles")
        print("已清理旧 user_profiles 向量集合，业务状态改用 SQLite")
    except Exception:
        pass
    try:
        collection = client.get_collection("knowledge_base")
        version_docs = collection.get(ids=["__index_version__"]).get("documents") or []
        if version_docs and version_docs[0] == KNOWLEDGE_SCHEMA_VERSION:
            print(f"知识库已有 {collection.count()} 条记录（schema {KNOWLEDGE_SCHEMA_VERSION}）")
            return
        client.delete_collection("knowledge_base")
    except Exception:
        pass

    collection = client.get_or_create_collection("knowledge_base")
    documents = _load_knowledge_documents()
    for document in documents:
        collection.add(
            ids=[document["id"]],
            documents=[document["text"]],
            metadatas=[document["metadata"]],
        )
    collection.upsert(
        ids=["__index_version__"],
        documents=[KNOWLEDGE_SCHEMA_VERSION],
        metadatas=[{"type": "index_version"}],
    )
    print(f"已索引 {len(documents)} 条结构化知识片段（schema {KNOWLEDGE_SCHEMA_VERSION}）")
