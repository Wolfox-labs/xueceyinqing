"""
Docx 工具 — 文档生成和解析，.docx 格式。

- DocxGenerateTool：将 Markdown 内容生成 .docx 文件
- DocxParseTool：读取 .docx 文件，提取文本内容
"""
import re
from pathlib import Path
from crewai.tools import BaseTool

_OUTPUT_DIR = Path(__file__).parent.parent / "runtime" / "output"


def _add_rich_paragraph(doc, text, style=None):
    """解析内联 Markdown 并添加带格式的段落。"""
    p = doc.add_paragraph(style=style) if style else doc.add_paragraph()
    tokens = re.split(r"(\*\*.*?\*\*|\*[^*].*?\*|`.*?`)", text)
    for token in tokens:
        if not token:
            continue
        from docx.shared import Pt
        if token.startswith("**") and token.endswith("**"):
            run = p.add_run(token[2:-2])
            run.bold = True
        elif token.startswith("*") and token.endswith("*") and len(token) > 2:
            run = p.add_run(token[1:-1])
            run.italic = True
        elif token.startswith("`") and token.endswith("`"):
            run = p.add_run(token[1:-1])
            run.font.name = "Courier New"
            run.font.size = Pt(10)
        else:
            p.add_run(token)
    return p


class DocxGenerateTool(BaseTool):
    name: str = "DocxGenerateTool"
    description: str = (
        "将 Markdown 内容生成 .docx 文档文件。"
        "参数 content: 文档正文（Markdown 格式）。"
        "参数 filename: 文件名（不含扩展名，不含路径），例如 'python入门'。"
        "文件将保存到 output/ 目录，返回生成的文件路径。"
    )

    def _run(self, content: str, filename: str) -> str:
        from docx import Document
        from docx.shared import Pt, Cm
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        safe_name = "".join(c for c in filename if c.isalnum() or c in "._- ()（）")
        if not safe_name:
            safe_name = "untitled"
        filepath = _OUTPUT_DIR / f"{safe_name}.docx"
        counter = 1
        while filepath.exists():
            filepath = _OUTPUT_DIR / f"{safe_name}_{counter}.docx"
            counter += 1

        doc = Document()
        style = doc.styles["Normal"]
        style.font.name = "Microsoft YaHei"
        style.font.size = Pt(11)

        lines = content.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i]

            if not line.strip():
                i += 1
                continue

            # 代码块
            if line.strip().startswith("```"):
                i += 1
                code_lines = []
                while i < len(lines) and not lines[i].strip().startswith("```"):
                    code_lines.append(lines[i])
                    i += 1
                i += 1  # 跳过结束 ```
                if code_lines:
                    p = doc.add_paragraph()
                    run = p.add_run("\n".join(code_lines))
                    run.font.name = "Courier New"
                    run.font.size = Pt(9)
                continue

            # 标题
            if line.startswith("# "):
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run = p.add_run(line[2:])
                run.bold = True
                run.font.size = Pt(18)
            elif line.startswith("## "):
                p = doc.add_paragraph()
                run = p.add_run(line[3:])
                run.bold = True
                run.font.size = Pt(15)
            elif line.startswith("### "):
                p = doc.add_paragraph()
                run = p.add_run(line[4:])
                run.bold = True
                run.font.size = Pt(13)

            # 有序列表
            elif re.match(r"^\d+\.\s", line):
                _add_rich_paragraph(doc, re.sub(r"^\d+\.\s", "", line), style="List Number")

            # 无序列表
            elif line.startswith("- ") or line.startswith("* "):
                _add_rich_paragraph(doc, line[2:], style="List Bullet")

            # 引用
            elif line.startswith("> "):
                p = _add_rich_paragraph(doc, line[2:])
                p.paragraph_format.left_indent = Cm(1)

            # 普通段落
            else:
                _add_rich_paragraph(doc, line)

            i += 1

        doc.save(str(filepath))
        return str(filepath)


class DocxParseTool(BaseTool):
    name: str = "DocxParseTool"
    description: str = (
        "读取 .docx 文件并提取其中的文本内容。"
        "参数 filepath: 文件的完整路径。"
        "返回文件的文本内容。"
    )

    def _run(self, filepath: str) -> str:
        from docx import Document

        path = Path(filepath)
        if not path.exists():
            return f"错误：文件不存在 — {filepath}"

        try:
            doc = Document(str(path))
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            return "\n".join(paragraphs)
        except Exception as e:
            return f"解析失败：{e}"
