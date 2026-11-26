"""
PPT 工具 — 生成带自动版式和主题系统的 .pptx 演示文稿。

- PptxGenerateTool：将结构化幻灯片内容交给 PptRenderer 渲染
- 渲染结果使用 PowerPoint 原生形状，保证离线、跨设备可编辑
"""
import json
from pathlib import Path

from crewai.tools import BaseTool

from schemas import PPTOutput
from tools.ppt_renderer import PptRenderer


# ── 输出目录 ───────────────────────────────────────────

_OUTPUT_DIR = Path(__file__).parent.parent / "runtime" / "output"


# ── 工具：生成 .pptx ───────────────────────────────────

class PptxGenerateTool(BaseTool):
    name: str = "PptxGenerateTool"
    description: str = (
        "根据结构化幻灯片内容生成带自动版式和主题风格的 .pptx 演示文稿文件。"
        "参数 slides_json: 幻灯片内容 JSON 字符串（符合 PPTOutput schema）。"
        "参数 filename: 文件名（不含扩展名，不含路径），例如 'python入门'。"
        "参数 theme: 主题 key，可选 dark_tech / academic_clean / education_fresh / business_blue。"
        "文件将保存到 output/ 目录，返回生成的文件路径。"
    )

    def _run(
        self,
        slides_json: str,
        filename: str = "",
        theme: str = "dark_tech",
    ) -> str:
        data = json.loads(slides_json)
        output = PPTOutput.model_validate(data)

        # 文件名优先使用调用方传入的安全名称；为空时沿用演示文稿标题。
        if filename and filename.strip():
            output = output.model_copy(update={"title": filename.strip()})

        renderer = PptRenderer(_OUTPUT_DIR)
        return str(renderer.render(output, theme_key=theme or output.theme))
