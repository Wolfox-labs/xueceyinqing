"""
工具注册中心 — 根据资源类型返回对应的工具集合。
"""
from tools.knowledge import KnowledgeSearchTool
from tools.profile_store import ProfileGetTool
from tools.docx_tools import DocxGenerateTool, DocxParseTool
from tools.pptx_tools import PptxGenerateTool
from tools.exam_tools import ScoreTool, WeakPointAnalyzer
from tools.classroom_tools import PptxFromClassroomTool, QuizExtractTool


def get_tools(user_id: str = "default", resource_type: str = None):
    """根据资源类型返回工具列表。"""
    common = [KnowledgeSearchTool(), ProfileGetTool(user_id)]
    if resource_type == "document":
        return common + [DocxGenerateTool(), DocxParseTool()]
    elif resource_type == "ppt":
        return common + [PptxGenerateTool()]
    elif resource_type == "exercise":
        return common + [ScoreTool(), WeakPointAnalyzer()]
    elif resource_type == "classroom":
        return common + [PptxFromClassroomTool(), QuizExtractTool()]
    elif resource_type == "assessment":
        return common + [ScoreTool(), WeakPointAnalyzer()]
    return common
