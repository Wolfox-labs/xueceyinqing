"""
虚拟课堂工具 — PPT 生成、TTS 音频、题目提取。
"""
from pathlib import Path
from crewai.tools import BaseTool

_OUTPUT_DIR = Path(__file__).parent.parent / "runtime" / "output"


class PptxFromClassroomTool(BaseTool):
    name: str = "PptxFromClassroomTool"
    description: str = (
        "将虚拟课堂脚本生成 PPT 文件。"
        "参数 classroom_json: 课堂脚本 JSON 字符串（符合 ClassroomScript schema）。"
        "参数 filename: 文件名（不含扩展名）。"
        "文件将保存到 output/ 目录，返回生成的文件路径。"
    )

    def _run(self, classroom_json: str, filename: str) -> str:
        from pptx import Presentation
        from pptx.util import Inches, Pt
        from pptx.enum.text import PP_ALIGN
        from schemas import ClassroomScript
        import json as _json

        data = _json.loads(classroom_json)
        classroom = ClassroomScript.model_validate(data)

        _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        safe_name = "".join(c for c in filename if c.isalnum() or c in "._- ()（）")
        if not safe_name:
            safe_name = "untitled"
        filepath = _OUTPUT_DIR / f"{safe_name}.pptx"
        counter = 1
        while filepath.exists():
            filepath = _OUTPUT_DIR / f"{safe_name}_{counter}.pptx"
            counter += 1

        prs = Presentation()
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)

        for slide_data in classroom.slides:
            slide_layout = prs.slide_layouts[1]
            slide = prs.slides.add_slide(slide_layout)

            title_shape = slide.shapes.title
            if title_shape:
                title_shape.text = slide_data.title
                for paragraph in title_shape.text_frame.paragraphs:
                    paragraph.alignment = PP_ALIGN.LEFT
                    for run in paragraph.runs:
                        run.font.name = "Microsoft YaHei"
                        run.font.size = Pt(24)

            if slide.placeholders:
                body_shape = slide.placeholders[1]
                tf = body_shape.text_frame
                tf.clear()
                for i, point in enumerate(slide_data.bullet_points):
                    if i == 0:
                        p = tf.paragraphs[0]
                    else:
                        p = tf.add_paragraph()
                    p.text = point
                    p.level = 0
                    p.alignment = PP_ALIGN.LEFT
                    for run in p.runs:
                        run.font.name = "Microsoft YaHei"
                        run.font.size = Pt(18)

            if slide_data.script:
                notes_slide = slide.notes_slide
                notes_slide.notes_text_frame.text = slide_data.script

        prs.save(str(filepath))
        return str(filepath)


class ScriptToAudioTool(BaseTool):
    name: str = "ScriptToAudioTool"
    description: str = "将演播脚本转为 TTS 音频文件。参数 script_text: 脚本全文，参数 filename: 输出文件名（不含扩展名）。"

    def _run(self, script_text: str, filename: str) -> str:
        return "音频生成功能待接入 TTS 服务（如 edge-tts）"


class QuizExtractTool(BaseTool):
    name: str = "QuizExtractTool"
    description: str = (
        "从课堂脚本中提取三个时间点的题目（课前/课中/课后），以可读文本格式输出。"
        "参数 classroom_json: 课堂脚本 JSON 字符串（符合 ClassroomScript schema）。"
    )

    def _run(self, classroom_json: str) -> str:
        from schemas import ClassroomScript
        import json as _json

        data = _json.loads(classroom_json)
        classroom = ClassroomScript.model_validate(data)

        lines = [f"# 课堂测验: {classroom.title}", ""]
        position_labels = {"pre": "课前", "mid": "课中", "post": "课后"}

        for quiz in classroom.quizzes:
            label = position_labels.get(quiz.position, quiz.position)
            lines.append(f"## {label}测验")
            lines.append("")
            lines.append(f"**题目**：{quiz.question}")
            if quiz.options:
                for j, opt in enumerate(quiz.options):
                    opt_label = chr(65 + j)
                    lines.append(f"  {opt_label}. {opt}")
            lines.append("")
            lines.append(f"**答案**：{quiz.answer}")
            lines.append("")
            lines.append(f"**解析**：{quiz.explanation}")
            lines.append("")

        return "\n".join(lines)
