"""PPT 自动版式渲染器。

职责：
1. 将 PPTOutput 转成 16:9 演示文稿；
2. 根据页面内容自动选择封面、目录、概念、对比、代码、总结等版式；
3. 使用主题 token 绘制背景、卡片、强调线、页码和讲稿备注。

所有视觉元素都使用 PPT 原生形状，不依赖外部图片，保证离线演示和跨设备打开。
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Inches, Pt

from schemas import PPTOutput, PPTSlide
from tools.ppt_themes import PPTTheme, get_theme


SW = 13.333
SH = 7.5
MARGIN = 0.62
CONTENT_TOP = 1.46
FOOTER_Y = 7.08


def _rgb(value: str) -> RGBColor:
    return RGBColor.from_string(value.replace("#", "").upper())


def _shape(
    slide,
    kind: MSO_SHAPE,
    x: float,
    y: float,
    w: float,
    h: float,
    fill: str,
    line: str | None = None,
    line_width: float = 0.8,
):
    shape = slide.shapes.add_shape(kind, Inches(x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid()
    shape.fill.fore_color.rgb = _rgb(fill)
    if line:
        shape.line.color.rgb = _rgb(line)
        shape.line.width = Pt(line_width)
    else:
        shape.line.fill.background()
    try:
        shape.shadow.inherit = False
    except Exception:
        pass
    return shape


def _rect(slide, x: float, y: float, w: float, h: float, fill: str, line: str | None = None):
    return _shape(slide, MSO_SHAPE.RECTANGLE, x, y, w, h, fill, line)


def _round(slide, x: float, y: float, w: float, h: float, fill: str, line: str | None = None):
    return _shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h, fill, line)


def _line(slide, x1: float, y1: float, x2: float, y2: float, color: str, width: float = 1.0):
    connector = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    connector.line.color.rgb = _rgb(color)
    connector.line.width = Pt(width)
    return connector


def _style_run(run, font_name: str, size: float, color: str, bold: bool = False, italic: bool = False):
    run.font.name = font_name
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = _rgb(color)
    rpr = run._r.get_or_add_rPr()
    for tag in ("a:latin", "a:ea", "a:cs"):
        element = rpr.find(qn(tag))
        if element is None:
            element = OxmlElement(tag)
            rpr.append(element)
        element.set("typeface", font_name)


def _text(
    slide,
    x: float,
    y: float,
    w: float,
    h: float,
    text: str,
    theme: PPTTheme,
    *,
    size: float = 16,
    color: str | None = None,
    bold: bool = False,
    align=PP_ALIGN.LEFT,
    font: str | None = None,
    anchor=MSO_ANCHOR.TOP,
    line_spacing: float = 1.08,
):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    frame = box.text_frame
    frame.clear()
    frame.word_wrap = True
    frame.vertical_anchor = anchor
    frame.margin_left = 0
    frame.margin_right = 0
    frame.margin_top = 0
    frame.margin_bottom = 0
    paragraph = frame.paragraphs[0]
    paragraph.alignment = align
    paragraph.line_spacing = line_spacing
    run = paragraph.add_run()
    run.text = text or ""
    _style_run(run, font or theme.font_body, size, color or theme.text, bold)
    return box


def _paragraphs(
    slide,
    x: float,
    y: float,
    w: float,
    h: float,
    items: Iterable[str],
    theme: PPTTheme,
    *,
    size: float = 16,
    color: str | None = None,
    bullet: bool = True,
    font: str | None = None,
    line_spacing: float = 1.14,
):
    rows = [str(item).strip() for item in items if str(item).strip()]
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    frame = box.text_frame
    frame.clear()
    frame.word_wrap = True
    frame.margin_left = 0
    frame.margin_right = 0
    frame.margin_top = 0
    frame.margin_bottom = 0
    for index, item in enumerate(rows):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.alignment = PP_ALIGN.LEFT
        paragraph.line_spacing = line_spacing
        paragraph.space_after = Pt(5)
        run = paragraph.add_run()
        run.text = f"•  {item}" if bullet else item
        _style_run(run, font or theme.font_body, size, color or theme.text)
    return box


def _label(slide, text: str, theme: PPTTheme, x: float = MARGIN, y: float = 0.34, color: str | None = None):
    return _text(slide, x, y, 6.2, 0.24, text.upper(), theme, size=8.5, color=color or theme.primary, bold=True, font=theme.font_code)


def _title(slide, text: str, theme: PPTTheme, *, y: float = 0.68, size: float = 25, color: str | None = None):
    return _text(slide, MARGIN, y, 11.4, 0.58, text, theme, size=size, color=color or theme.text, bold=True, font=theme.font_title)


def _header(slide, label: str, title: str, theme: PPTTheme, *, accent: str | None = None):
    _label(slide, label, theme)
    _title(slide, title, theme)
    _rect(slide, MARGIN, 1.28, 1.0, 0.045, accent or theme.primary, None)


def _footer(slide, theme: PPTTheme, page: int, total: int, *, label: str = "学策引擎 · 多智能体自适应学习"):
    _line(slide, MARGIN, FOOTER_Y, SW - MARGIN, FOOTER_Y, theme.border, 0.6)
    _text(slide, MARGIN, FOOTER_Y + 0.08, 6.5, 0.22, label, theme, size=8, color=theme.muted, font=theme.font_code)
    _text(slide, SW - MARGIN - 1.4, FOOTER_Y + 0.08, 1.4, 0.22, f"{page:02d} / {total:02d}", theme, size=8, color=theme.muted, font=theme.font_code, align=PP_ALIGN.RIGHT)


def _slide_bg(slide, theme: PPTTheme, *, cover: bool = False):
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = _rgb(theme.bg_deep if cover else theme.bg)
    if theme.is_dark:
        _shape(slide, MSO_SHAPE.OVAL, 10.2, -1.45, 5.2, 5.2, theme.surface, None)
        _shape(slide, MSO_SHAPE.OVAL, -1.8, 5.2, 4.2, 4.2, theme.surface_alt, None)
    else:
        _shape(slide, MSO_SHAPE.OVAL, 10.5, -1.5, 4.8, 4.8, theme.bg_deep, None)
        _rect(slide, 0, 0, SW, 0.13, theme.primary, None)
    if cover:
        _rect(slide, 0, 0, 0.18, SH, theme.primary, None)
        _shape(slide, MSO_SHAPE.OVAL, 9.8, 1.05, 4.4, 4.4, theme.surface, None)
        _shape(slide, MSO_SHAPE.OVAL, 10.55, 1.8, 2.9, 2.9, theme.primary, None)
    else:
        _rect(slide, 0, 0, SW, 0.055, theme.primary, None)
        for index in range(5):
            _line(slide, 9.5 + index * 0.82, 0.22, 9.1 + index * 0.82, 6.95, theme.surface_alt, 0.45)


def _card(slide, x: float, y: float, w: float, h: float, theme: PPTTheme, *, fill: str | None = None, line: str | None = None):
    _rect(slide, x + 0.055, y + 0.075, w, h, theme.bg_deep, None)
    return _round(slide, x, y, w, h, fill or theme.surface, line or theme.border)


def _pill(slide, x: float, y: float, w: float, h: float, text: str, theme: PPTTheme, *, fill: str | None = None, color: str | None = None):
    _round(slide, x, y, w, h, fill or theme.surface_alt, theme.border)
    _text(slide, x + 0.12, y + 0.035, w - 0.24, h - 0.07, text, theme, size=8.5, color=color or theme.muted, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)


def _notes(slide, text: str):
    if text.strip():
        slide.notes_slide.notes_text_frame.text = text.strip()


def _body_size(items: list[str], base: float = 17) -> float:
    total = sum(len(item) for item in items)
    if total > 420 or len(items) >= 7:
        return max(11.5, base - 5)
    if total > 260 or len(items) >= 5:
        return max(13, base - 3)
    if total > 160:
        return max(14, base - 1)
    return base


def _infer_layout(slide: PPTSlide, index: int) -> str:
    if slide.layout != "auto":
        return slide.layout
    title = slide.title.strip()
    bullets = " ".join(slide.bullet_points)
    if any(word in title for word in ("对比", "比较", "区别", "优缺点", "差异")):
        return "compare"
    if slide.code or any(token in bullets for token in ("def ", "class ", "import ", "print(", "for ", "while ")):
        return "code"
    if any(word in title for word in ("总结", "小结", "回顾", "结论")):
        return "summary"
    if any(word in title for word in ("章节", "过渡", "下一步")):
        return "section"
    if index == 0 and any(word in title for word in ("封面", "演示文稿")):
        return "cover"
    return "concept"


def _split_code(slide: PPTSlide) -> tuple[str, list[str]]:
    if slide.code.strip():
        return slide.code.strip(), slide.bullet_points
    code_lines: list[str] = []
    notes: list[str] = []
    for item in slide.bullet_points:
        if "\n" in item or any(token in item for token in ("def ", "class ", "import ", "print(", "=", "for ", "while ", "return")):
            code_lines.append(item.strip())
        else:
            notes.append(item.strip())
    if not code_lines and slide.bullet_points:
        code_lines = [slide.bullet_points[0]]
        notes = slide.bullet_points[1:]
    return "\n".join(code_lines), notes


def _split_compare(items: list[str]) -> tuple[str, list[str], str, list[str]]:
    left: list[str] = []
    right: list[str] = []
    labels = ["方案 A", "方案 B"]
    for item in items:
        if "：" in item or ":" in item:
            head, _, tail = item.partition("：" if "：" in item else ":")
            if len(head.strip()) <= 12:
                labels[0 if not left else 1] = head.strip()
                (left if not left else right).append(tail.strip())
                continue
        (left if len(left) <= len(right) else right).append(item)
    if not left and right:
        left, right = right, []
    return labels[0], left, labels[1], right


class PptRenderer:
    """可复用的 PPT 渲染器。"""

    def __init__(self, output_dir: Path | str | None = None):
        self.output_dir = Path(output_dir) if output_dir else Path(__file__).parent.parent / "runtime" / "output"

    def render(self, output: PPTOutput, theme_key: str | None = None) -> Path:
        theme = get_theme(theme_key or output.theme)
        deck_title = output.title.strip() or "学习资源演示"
        content_slides = [
            slide for slide in output.slides
            if slide.title.strip() and slide.layout not in {"cover", "closing"}
        ]
        if not content_slides:
            content_slides = output.slides

        has_agenda = len(content_slides) >= 4
        total = 1 + (1 if has_agenda else 0) + len(content_slides) + 1

        prs = Presentation()
        prs.slide_width = Inches(SW)
        prs.slide_height = Inches(SH)
        blank = prs.slide_layouts[6]

        page = 1
        self._cover(prs, blank, output, theme, page, total)
        page += 1
        if has_agenda:
            self._agenda(prs, blank, content_slides[:8], theme, page, total)
            page += 1

        for index, slide_data in enumerate(content_slides):
            slide = prs.slides.add_slide(blank)
            _slide_bg(slide, theme)
            layout = _infer_layout(slide_data, index)
            if layout == "section":
                self._section(slide, slide_data, theme, page, total)
            elif layout == "compare":
                self._compare(slide, slide_data, theme, page, total)
            elif layout == "code":
                self._code(slide, slide_data, theme, page, total)
            elif layout == "summary":
                self._summary(slide, slide_data, theme, page, total)
            else:
                self._concept(slide, slide_data, theme, page, total)
            _notes(slide, slide_data.notes)
            page += 1

        self._closing(prs, blank, output, theme, page, total)
        prs.core_properties.title = deck_title
        prs.core_properties.subject = "学策引擎自动生成演示文稿"
        prs.core_properties.author = "学策引擎"
        prs.core_properties.comments = f"主题：{theme.name}；版式：自动生成；页数：{total}"
        filepath = self._safe_path(deck_title)
        prs.save(str(filepath))
        return filepath

    def _safe_path(self, filename: str) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        safe_name = "".join(c for c in filename if c.isalnum() or c in "._- ()（）")
        if safe_name.lower().endswith(".pptx"):
            safe_name = safe_name[:-5]
        if not safe_name:
            safe_name = "untitled"
        filepath = self.output_dir / f"{safe_name}.pptx"
        counter = 1
        while filepath.exists():
            filepath = self.output_dir / f"{safe_name}_{counter}.pptx"
            counter += 1
        return filepath

    def _cover(self, prs, blank, output: PPTOutput, theme: PPTTheme, page: int, total: int):
        slide = prs.slides.add_slide(blank)
        _slide_bg(slide, theme, cover=True)
        _text(slide, MARGIN + 0.2, 0.55, 6.4, 0.25, "XUECE ENGINE / ADAPTIVE LEARNING", theme, size=9, color=theme.primary, bold=True, font=theme.font_code)
        _text(slide, MARGIN + 0.2, 1.35, 8.6, 1.25, output.title or "学习资源演示", theme, size=35, color=theme.text, bold=True, font=theme.font_title, line_spacing=0.98)
        subtitle = output.subtitle or "算法驱动的多智能体自适应学习系统"
        _text(slide, MARGIN + 0.2, 2.9, 7.7, 0.55, subtitle, theme, size=16, color=theme.muted, line_spacing=1.15)
        _rect(slide, MARGIN + 0.2, 3.75, 1.55, 0.06, theme.primary, None)
        _text(slide, MARGIN + 0.2, 4.0, 6.8, 0.3, "由教学 Agent、审核 Agent 与自适应策略引擎共同生成", theme, size=10.5, color=theme.muted)
        for index, (label, color) in enumerate((("知识图谱", theme.primary), ("多智能体", theme.secondary), ("自适应策略", theme.accent))):
            _pill(slide, MARGIN + 0.2 + index * 1.72, 4.72, 1.55, 0.35, label, theme, fill=theme.surface, color=color)
        _text(slide, SW - 3.55, 5.94, 2.7, 0.25, "SYSTEM GENERATED DECK", theme, size=8, color=theme.muted, font=theme.font_code, align=PP_ALIGN.RIGHT)
        _text(slide, SW - 3.55, 6.27, 2.7, 0.25, f"主题：{theme.name}", theme, size=9, color=theme.primary, bold=True, align=PP_ALIGN.RIGHT)
        _text(slide, MARGIN + 0.2, 6.86, 4.3, 0.2, "01 / PRESENTATION", theme, size=8, color=theme.muted, font=theme.font_code)

    def _agenda(self, prs, blank, slides: list[PPTSlide], theme: PPTTheme, page: int, total: int):
        slide = prs.slides.add_slide(blank)
        _slide_bg(slide, theme)
        _header(slide, "CONTENTS / 目录", "本次学习路线", theme)
        columns = [slides[:4], slides[4:8]]
        for col, items in enumerate(columns):
            for row, item in enumerate(items):
                x = MARGIN + col * 6.18
                y = 1.72 + row * 1.02
                _card(slide, x, y, 5.65, 0.78, theme)
                _text(slide, x + 0.18, y + 0.16, 0.45, 0.35, f"{col * 4 + row + 1:02d}", theme, size=16, color=theme.primary, bold=True, font=theme.font_code)
                _text(slide, x + 0.78, y + 0.17, 4.5, 0.35, item.title, theme, size=12, color=theme.text, bold=True)
        _footer(slide, theme, page, total)

    def _section(self, slide, data: PPTSlide, theme: PPTTheme, page: int, total: int):
        _rect(slide, 0.0, 0.0, 4.35, SH, theme.surface, None)
        _text(slide, 0.78, 2.05, 2.4, 1.1, f"{page - 1:02d}", theme, size=46, color=theme.primary, bold=True, font=theme.font_code)
        _text(slide, 0.78, 3.22, 2.8, 0.2, "SECTION", theme, size=9, color=theme.muted, bold=True, font=theme.font_code)
        _text(slide, 5.05, 2.0, 7.1, 0.75, data.title, theme, size=27, color=theme.text, bold=True)
        _text(slide, 5.05, 2.92, 6.5, 0.6, data.subtitle or data.key_message or "继续进入下一部分的核心内容。", theme, size=13, color=theme.muted)
        _rect(slide, 5.05, 3.85, 1.4, 0.06, theme.primary, None)
        _footer(slide, theme, page, total)

    def _concept(self, slide, data: PPTSlide, theme: PPTTheme, page: int, total: int):
        _header(slide, "CONCEPT / 概念解析", data.title, theme)
        bullets = [item for item in data.bullet_points if item.strip()]
        font_size = _body_size(bullets, 17)
        y = 1.62
        if data.key_message:
            _card(slide, MARGIN, y, SW - MARGIN * 2, 0.78, theme, fill=theme.surface_alt, line=theme.primary)
            _rect(slide, MARGIN, y, 0.07, 0.78, theme.primary, None)
            _text(slide, MARGIN + 0.28, y + 0.16, SW - MARGIN * 2 - 0.55, 0.45, data.key_message, theme, size=13, color=theme.text, bold=True)
            y += 1.05
        if not bullets:
            _text(slide, MARGIN, y + 0.5, SW - MARGIN * 2, 0.5, data.subtitle or "本页内容等待补充。", theme, size=16, color=theme.muted)
        elif len(bullets) <= 3:
            card_h = 0.92 if len(bullets) == 3 else 1.1
            for index, item in enumerate(bullets):
                card_y = y + index * (card_h + 0.16)
                _card(slide, MARGIN, card_y, SW - MARGIN * 2, card_h, theme)
                _text(slide, MARGIN + 0.24, card_y + 0.2, 0.42, 0.35, f"{index + 1:02d}", theme, size=13, color=theme.primary, bold=True, font=theme.font_code)
                _text(slide, MARGIN + 0.86, card_y + 0.18, SW - MARGIN * 2 - 1.2, card_h - 0.3, item, theme, size=font_size, color=theme.text, anchor=MSO_ANCHOR.MIDDLE)
        else:
            columns = 2
            card_w = (SW - MARGIN * 2 - 0.18) / 2
            card_h = 1.22 if len(bullets) <= 4 else 1.02
            for index, item in enumerate(bullets[:6]):
                col = index % columns
                row = index // columns
                x = MARGIN + col * (card_w + 0.18)
                card_y = y + row * (card_h + 0.16)
                _card(slide, x, card_y, card_w, card_h, theme)
                _text(slide, x + 0.2, card_y + 0.16, 0.36, 0.3, f"{index + 1:02d}", theme, size=11, color=theme.primary, bold=True, font=theme.font_code)
                _text(slide, x + 0.67, card_y + 0.14, card_w - 0.86, card_h - 0.26, item, theme, size=font_size - 1, color=theme.text, anchor=MSO_ANCHOR.MIDDLE)
        _footer(slide, theme, page, total)

    def _compare(self, slide, data: PPTSlide, theme: PPTTheme, page: int, total: int):
        _header(slide, "COMPARE / 对比分析", data.title, theme)
        left_label, left, right_label, right = _split_compare(data.bullet_points)
        panel_y = 1.68
        panel_h = 4.93
        panel_w = 5.65
        _card(slide, MARGIN, panel_y, panel_w, panel_h, theme)
        _card(slide, SW - MARGIN - panel_w, panel_y, panel_w, panel_h, theme)
        _rect(slide, MARGIN, panel_y, panel_w, 0.62, theme.primary, None)
        _rect(slide, SW - MARGIN - panel_w, panel_y, panel_w, 0.62, theme.secondary, None)
        _text(slide, MARGIN + 0.24, panel_y + 0.16, panel_w - 0.48, 0.3, left_label, theme, size=14, color=theme.bg_deep, bold=True)
        _text(slide, SW - MARGIN - panel_w + 0.24, panel_y + 0.16, panel_w - 0.48, 0.3, right_label, theme, size=14, color=theme.bg_deep, bold=True)
        _paragraphs(slide, MARGIN + 0.28, panel_y + 0.92, panel_w - 0.56, panel_h - 1.15, left or ["等待补充"], theme, size=_body_size(left, 15), line_spacing=1.18)
        _paragraphs(slide, SW - MARGIN - panel_w + 0.28, panel_y + 0.92, panel_w - 0.56, panel_h - 1.15, right or ["等待补充"], theme, size=_body_size(right, 15), line_spacing=1.18)
        _line(slide, 6.42, 3.26, 6.92, 3.26, theme.accent, 2.0)
        _shape(slide, MSO_SHAPE.CHEVRON, 6.80, 3.06, 0.32, 0.4, theme.accent, None)
        _footer(slide, theme, page, total)

    def _code(self, slide, data: PPTSlide, theme: PPTTheme, page: int, total: int):
        _header(slide, "CODE / 实践", data.title, theme, accent=theme.secondary)
        code, notes = _split_code(data)
        code_box_y = 1.62
        code_box_h = 4.95
        code_box_w = 8.05
        _card(slide, MARGIN, code_box_y, code_box_w, code_box_h, theme, fill=theme.bg_deep, line=theme.border)
        for index, color in enumerate((theme.accent, theme.warning, theme.success)):
            _shape(slide, MSO_SHAPE.OVAL, MARGIN + 0.24 + index * 0.2, code_box_y + 0.2, 0.1, 0.1, color, None)
        code_size = 13 if len(code.splitlines()) <= 12 else 10
        _paragraphs(slide, MARGIN + 0.28, code_box_y + 0.54, code_box_w - 0.56, code_box_h - 0.74, code.splitlines() or ["# 暂无代码"], theme, size=code_size, color=theme.text, bullet=False, font=theme.font_code, line_spacing=1.12)
        side_x = MARGIN + code_box_w + 0.28
        side_w = SW - MARGIN - side_x
        _text(slide, side_x, code_box_y, side_w, 0.3, "讲解要点", theme, size=13, color=theme.primary, bold=True)
        _paragraphs(slide, side_x, code_box_y + 0.48, side_w, code_box_h - 0.5, notes or [data.key_message or "先理解代码结构，再关注边界条件。"], theme, size=_body_size(notes, 13), line_spacing=1.18)
        _footer(slide, theme, page, total)

    def _summary(self, slide, data: PPTSlide, theme: PPTTheme, page: int, total: int):
        _header(slide, "SUMMARY / 总结", data.title, theme, accent=theme.accent)
        if data.key_message:
            _card(slide, MARGIN, 1.58, SW - MARGIN * 2, 0.82, theme, fill=theme.surface_alt, line=theme.accent)
            _text(slide, MARGIN + 0.28, 1.76, SW - MARGIN * 2 - 0.56, 0.48, data.key_message, theme, size=14, color=theme.text, bold=True)
            card_y = 2.68
        else:
            card_y = 1.68
        bullets = [item for item in data.bullet_points if item.strip()][:5]
        if not bullets:
            bullets = ["掌握核心概念", "理解关键步骤", "完成一次实践"]
        card_w = (SW - MARGIN * 2 - 0.18 * (len(bullets) - 1)) / len(bullets)
        for index, item in enumerate(bullets):
            x = MARGIN + index * (card_w + 0.18)
            _card(slide, x, card_y, card_w, 2.65, theme)
            _text(slide, x + 0.2, card_y + 0.2, 0.6, 0.45, f"{index + 1:02d}", theme, size=23, color=theme.primary, bold=True, font=theme.font_code)
            _text(slide, x + 0.2, card_y + 0.88, card_w - 0.4, 1.45, item, theme, size=_body_size([item], 14), color=theme.text, anchor=MSO_ANCHOR.MIDDLE)
        _footer(slide, theme, page, total)

    def _closing(self, prs, blank, output: PPTOutput, theme: PPTTheme, page: int, total: int):
        slide = prs.slides.add_slide(blank)
        _slide_bg(slide, theme, cover=True)
        _text(slide, MARGIN + 0.2, 1.6, 10.8, 0.7, "THANKS FOR LEARNING", theme, size=29, color=theme.text, bold=True, font=theme.font_code)
        _text(slide, MARGIN + 0.2, 2.5, 9.8, 0.5, output.subtitle or "让每一次学习都有算法依据", theme, size=17, color=theme.muted)
        _rect(slide, MARGIN + 0.2, 3.32, 1.7, 0.06, theme.primary, None)
        _text(slide, MARGIN + 0.2, 4.0, 10.4, 0.4, "知识图谱 · 遗忘曲线 · Contextual UCB · 多智能体协商", theme, size=11, color=theme.primary, font=theme.font_code)
        _text(slide, MARGIN + 0.2, 6.52, 6.2, 0.26, "学策引擎——算法驱动的多智能体自适应学习系统", theme, size=9, color=theme.muted)
        _text(slide, SW - 2.6, 6.52, 1.98, 0.26, f"{page:02d} / {total:02d}", theme, size=9, color=theme.muted, align=PP_ALIGN.RIGHT, font=theme.font_code)

