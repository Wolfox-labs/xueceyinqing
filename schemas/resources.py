"""
资源生成的结构化输出定义。

每种资源类型对应一个 Pydantic 模型。LLM 按此结构输出 JSON，
下游代码校验后传给工具（DocxGenerateTool 等）或序列化给前端。
"""
from pydantic import BaseModel, Field
from typing import Literal, Optional


# ── 思维导图 ───────────────────────────────────────────

class MindmapBranch(BaseModel):
    label: str
    children: list[str] = Field(default_factory=list)


class MindmapOutput(BaseModel):
    root: str
    branches: list[MindmapBranch] = Field(min_length=1, default_factory=list)


# ── 讲解文档 ───────────────────────────────────────────

class DocumentSection(BaseModel):
    heading: str
    body: str


class DocumentOutput(BaseModel):
    title: str
    sections: list[DocumentSection]


# ── 练习题库 ───────────────────────────────────────────

class ExerciseItem(BaseModel):
    question: str
    options: Optional[list[str]] = None
    answer: str
    explanation: str
    type: Literal["single_choice", "multi_choice", "true_false", "short_answer"] = "single_choice"
    score: int = 10
    knowledge_point: str = ""
    difficulty: Optional[Literal["基础", "进阶", "综合"]] = None


class ExerciseOutput(BaseModel):
    title: str
    items: list[ExerciseItem] = Field(min_length=1)


# ── PPT 演示文稿 ─────────────────────────────────────────

class PPTSlide(BaseModel):
    title: str
    bullet_points: list[str] = Field(default_factory=list)
    notes: str = ""
    layout: Literal[
        "auto", "cover", "agenda", "section", "concept",
        "compare", "code", "summary", "closing",
    ] = "auto"
    subtitle: str = ""
    key_message: str = ""
    code: str = ""


class PPTOutput(BaseModel):
    title: str
    subtitle: str = ""
    theme: str = "dark_tech"
    slides: list[PPTSlide] = Field(min_length=1, default_factory=list)


QUESTION_TAGS = {
    "TYPE":       "￥题型",
    "KNOWLEDGE":  "￥知识点",
    "QUESTION":   "￥题目",
    "OPTION":     "￥选项{}",
    "ANSWER":     "￥答案",
    "EXPLAIN":    "￥解析",
    "DIFFICULTY": "￥难度",
}

DOCUMENT_TAGS = {
    "TITLE":        "￥标题",
    "SECTION_TITLE": "￥段落标题",
    "SECTION_BODY":  "￥段落正文",
}

DOCUMENT_TEMPLATE = """请严格按照以下 ￥标签 格式输出讲解文档，不要输出 JSON，不要用代码块包裹：

￥标题：在此填写文档标题

￥段落标题：在此填写第一个段落的小标题
￥段落正文：在此填写第一个段落的正文内容

￥段落标题：在此填写第二个段落的小标题
￥段落正文：在此填写第二个段落的正文内容

至少包含 3 个段落。每个段落由 ￥段落标题 和 ￥段落正文 组成。
直接输出纯文本，不要加任何说明文字。"""

PPT_TAGS = {
    "TITLE":        "￥标题",
    "SLIDE_TITLE":  "￥幻灯片标题",
    "BULLET":       "￥要点",
    "NOTES":        "￥备注",
}

PPT_TEMPLATE = """请输出一个纯 JSON 对象，不要使用代码块，不要添加任何解释文字。格式如下：

{
  "title": "演示文稿标题",
  "subtitle": "一句话副标题",
  "theme": "dark_tech",
  "slides": [
    {
      "title": "页面标题",
      "layout": "concept",
      "subtitle": "页面副标题或章节说明",
      "key_message": "本页最重要的一句话结论",
      "bullet_points": ["要点一", "要点二", "要点三"],
      "code": "如果本页讲代码，在此填写完整可运行代码；否则为空字符串",
      "notes": "讲稿备注"
    }
  ]
}

layout 只能选择：auto、section、concept、compare、code、summary。
普通知识页使用 concept；代码页使用 code；比较或优缺点页面使用 compare；总结页使用 summary；章节过渡页使用 section。
至少生成 5 页幻灯片。每页 bullet_points 建议 2 到 5 条；代码必须放在 code 字段中，不要混入普通要点。
内容要准确、逻辑递进，并适合课堂讲解、比赛展示或自主学习。"""


