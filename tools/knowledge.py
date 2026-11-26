"""
知识库检索工具 — CrewAI Tool 层。
"""
from crewai.tools import BaseTool
from db.vector_store import get_store


class KnowledgeSearchTool(BaseTool):
    name: str = "knowledge_search"
    description: str = (
        "搜索知识库获取相关内容。输入中文或英文查询字符串，"
        "返回最匹配的知识片段文本。当需要引用准确知识点时使用。"
    )

    def _run(self, query: str) -> str:
        store = get_store()
        details = store.search_knowledge_details(query, n_results=3)
        if not details:
            return "未在知识库中找到相关内容。"
        blocks = []
        for item in details:
            metadata = item.get("metadata") or {}
            source = metadata.get("source") or metadata.get("path") or "学策引擎知识库"
            point = metadata.get("knowledge_point") or metadata.get("title") or "未标注知识点"
            blocks.append(
                f"[来源: {source} | 知识点: {point}]\n{item.get('text', '').strip()}"
            )
        return "\n\n---\n\n".join(blocks)
