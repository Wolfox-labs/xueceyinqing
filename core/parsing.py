"""
core/parsing.py — LLM 输出 JSON 提取与资源类型解析。

提供：
  _extract_json(raw)        → 从 LLM 原始输出中提取第一个有效资源 JSON
  parse_resource(rtype, raw) → 按资源类型解析并返回展示文本
  _parse_mindmap / _parse_document / _parse_exercise  → 各类型的解析辅助函数

所有函数签名与行为与 main.py 原定义保持一致。
依赖放在函数体内部（懒 import）以避免 core 层的循环依赖。
"""
import json
import logging
import re

from schemas import MindmapOutput, DocumentOutput, ExerciseOutput, PPTOutput
from schemas.resources import DOCUMENT_TAGS, PPT_TAGS, QUESTION_TAGS

logger = logging.getLogger(__name__)


def _load_json(segment: str) -> dict | None:
    """尝试解析 JSON，失败时用 json_repair 修复常见的 LLM 输出问题。

    LLM 经常在 JSON 值中包含未转义的双引号（如 "他说"你好""），
    json_repair 专门处理这类非标准 JSON。
    """
    try:
        return json.loads(segment)
    except json.JSONDecodeError:
        pass
    try:
        from json_repair import repair_json
        repaired = repair_json(segment)
        return json.loads(repaired)
    except Exception:
        return None


def _extract_json(raw: str) -> dict | None:
    """从包含额外文本的输出中提取第一个有效资源 JSON，跳过工具调用记录。"""
    pos = 0
    while True:
        start = raw.find("{", pos)
        if start == -1:
            return None
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(raw)):
            ch = raw[i]
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if in_string:
                if ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    segment = raw[start : i + 1]
                    data = _load_json(segment)
                    if data is None:
                        pos = i + 1
                        break
                    if set(data.keys()) == {"query"}:
                        pos = i + 1
                        break
                    return data
        else:
            break
    return None


def _json_to_mindmap_md(data: dict) -> str:
    """将 MindmapOutput JSON 转为 markdown 标题格式，供 markmap 渲染。"""
    lines = [f"# {data.get('root', '主题')}"]
    for branch in data.get("branches", []):
        lines.append(f"## {branch.get('label', '')}")
        for child in branch.get("children", []):
            lines.append(f"### {child}")
    return "\n".join(lines)


def _parse_mindmap(raw: str) -> str:
    """解析 mindmap 输出：优先 JSON → markdown 标题 → 写 .md 文件，失败则透传原文。"""
    data = _extract_json(raw)
    if data:
        try:
            MindmapOutput.model_validate(data)
            md = _json_to_mindmap_md(data)
            from pathlib import Path
            output_dir = Path(__file__).parent.parent / "runtime" / "output"
            output_dir.mkdir(parents=True, exist_ok=True)
            title = data.get("root", "思维导图")
            safe_name = "".join(c for c in title if c.isalnum() or c in "._- ()（）") or "mindmap"
            filepath = output_dir / f"{safe_name}.md"
            counter = 1
            while filepath.exists():
                filepath = output_dir / f"{safe_name}_{counter}.md"
                counter += 1
            filepath.write_text(md, encoding="utf-8")
            return f"文件已生成: {filepath}\n\n{md}"
        except Exception as exc:
            logger.warning("思维导图 JSON 校验失败：%s", exc)
    return _format_failure("mindmap", raw, "未找到合法的思维导图 JSON")


def _format_failure(rtype: str, raw: str, reason: str = "") -> str:
    """格式解析失败时显式降级：保留原文，但明确说明没有生成文件。

    旧实现对 mindmap/document/exercise/ppt 一律直接 `return raw`，用户拿到
    一段未格式化文本、没有文件、也没有任何错误提示。
    """
    logger.warning("资源格式解析失败 type=%s reason=%s", rtype, reason or "-")
    detail = f"（{reason}）" if reason else ""
    return (
        f"⚠️ 格式解析失败{detail}：模型输出不符合 {rtype} 的格式要求，"
        f"未生成文件。以下为原始输出，可重试生成。\n\n{raw}"
    )


def _format_document_to_md(doc: DocumentOutput) -> str:
    """将 DocumentOutput 转换回 Markdown 文本。"""
    lines = [f"# {doc.title}", ""]
    for section in doc.sections:
        lines.append(f"## {section.heading}")
        lines.append("")
        lines.append(section.body)
        lines.append("")
    return "\n".join(lines)


def _parse_document(raw: str) -> str:
    """解析 document 输出：优先 ￥标签 模板 → 降级 JSON → 透传原文。"""
    import re

    title_match = re.search(rf"{DOCUMENT_TAGS['TITLE']}：(.+)", raw)
    title = title_match.group(1).strip() if title_match else "未命名文档"

    sections = []
    section_blocks = re.split(rf"{DOCUMENT_TAGS['SECTION_TITLE']}：", raw)
    for block in section_blocks[1:]:
        parts = re.split(rf"{DOCUMENT_TAGS['SECTION_BODY']}：", block, maxsplit=1)
        heading = parts[0].strip()
        body_text = parts[1].strip() if len(parts) > 1 else ""
        if heading:
            sections.append({"heading": heading, "body": body_text})

    if sections:
        from schemas import DocumentOutput
        doc = DocumentOutput(title=title, sections=sections)
        from tools.docx_tools import DocxGenerateTool
        tool = DocxGenerateTool()
        md = _format_document_to_md(doc)
        filepath = tool._run(content=md, filename=doc.title)
        return f"文件已生成: {filepath}\n\n{md}"

    data = _extract_json(raw)
    if not data:
        return _format_failure("document", raw, "未找到 ￥段落标题/￥段落正文 结构")
    try:
        from schemas import DocumentOutput
        doc = DocumentOutput.model_validate(data)
    except Exception as e:
        return _format_failure("document", raw, f"JSON 校验失败: {e}")
    from tools.docx_tools import DocxGenerateTool
    tool = DocxGenerateTool()
    md = _format_document_to_md(doc)
    filepath = tool._run(content=md, filename=doc.title)
    return f"文件已生成: {filepath}\n\n{md}"


def _render_exercise_model(ex: ExerciseOutput) -> str:
    lines = [f"# {ex.title}", ""]
    for i, item in enumerate(ex.items, 1):
        lines.append(f"## 第{i}题")
        lines.append("")
        lines.append(f"**题目**：{item.question}")
        if item.options:
            for j, opt in enumerate(item.options):
                label = chr(65 + j)
                lines.append(f"  {label}. {opt}")
        lines.append("")
        lines.append(f"**答案**：{item.answer}")
        lines.append("")
        lines.append(f"**解析**：{item.explanation}")
        if item.difficulty:
            lines.append(f"  _难度：{item.difficulty}_")
        lines.append("")
    return "\n".join(lines)


def _render_exercise_tags(items: list[dict]) -> str:
    """渲染 ￥标签 格式的题目（crews/generate.py 的提示词要求的正是这种格式）。"""
    lines = [f"# 练习题库（{len(items)} 题）", ""]
    for i, item in enumerate(items, 1):
        lines.append(f"## 第{i}题")
        lines.append("")
        header = item.get("type") or "题目"
        knowledge_point = item.get("knowledge_point") or ""
        lines.append(f"**{header}**" + (f"（{knowledge_point}）" if knowledge_point else ""))
        lines.append("")
        lines.append(f"**题目**：{item.get('question', '')}")
        for opt in item.get("options") or []:
            lines.append(f"  {opt.get('label', '')}. {opt.get('text', '')}")
        lines.append("")
        lines.append(f"**答案**：{item.get('answer', '')}")
        if item.get("explanation"):
            lines.append("")
            lines.append(f"**解析**：{item['explanation']}")
        if item.get("difficulty"):
            lines.append(f"  _难度：{item['difficulty']}_")
        lines.append("")
    return "\n".join(lines)


def _parse_exercise(raw: str) -> str:
    """解析 exercise 输出：先试 JSON，再试 ￥标签。

    提示词（crews/generate.py）要求的是 ￥标签 纯文本，而旧实现只用
    _extract_json 解析 JSON —— 于是 /gen exercise 永远解析失败并静默透传原文。
    现在两种格式都支持。
    """
    data = _extract_json(raw)
    if data:
        try:
            return _render_exercise_model(ExerciseOutput.model_validate(data))
        except Exception as exc:
            logger.warning("练习题库 JSON 校验失败，改试 ￥标签 格式：%s", exc)

    try:
        from core.question_parser import parse_questions
        tagged = [item for item in parse_questions(raw) if item.get("question")]
    except Exception:
        logger.warning("￥标签 题库解析失败", exc_info=True)
        tagged = []

    if tagged:
        return _render_exercise_tags(tagged)
    return _format_failure("exercise", raw, "未找到可识别的题目结构（JSON 或 ￥标签）")


def _render_ppt_data(data: dict, ppt_theme: str = "dark_tech") -> str:
    """校验 PPT 数据、调用主题渲染器，并返回前端可读的结果摘要。"""
    from tools.pptx_tools import PptxGenerateTool

    ppt = PPTOutput.model_validate(data)
    theme_key = ppt_theme or ppt.theme or "dark_tech"
    tool = PptxGenerateTool()
    filepath = tool._run(
        slides_json=json.dumps(data, ensure_ascii=False),
        filename=ppt.title,
        theme=theme_key,
    )
    lines = [f"文件已生成: {filepath}", "", f"主题风格：{theme_key}", ""]
    for i, slide in enumerate(ppt.slides, 1):
        lines.append(f"  {i}. {slide.title}")
    return "\n".join(lines)


def _parse_ppt(raw: str, ppt_theme: str = "dark_tech") -> str:
    """解析 PPT 输出：优先新版 JSON，兼容旧版 ￥标签 模板。"""
    # 新版模型按 Pydantic schema 输出纯 JSON；优先走自动版式渲染。
    data = _extract_json(raw)
    if data:
        try:
            return _render_ppt_data(data, ppt_theme)
        except Exception:
            # JSON 可能来自无关的工具调用，继续尝试旧版标签格式。
            pass

    # 兼容历史数据：￥标题 / ￥幻灯片标题 / ￥要点 / ￥备注
    title_match = re.search(rf"{PPT_TAGS['TITLE']}：(.+)", raw)
    title = title_match.group(1).strip() if title_match else "未命名PPT"

    slides = []
    slide_blocks = re.split(rf"{PPT_TAGS['SLIDE_TITLE']}：", raw)
    for block in slide_blocks[1:]:
        slide_title = block.split(PPT_TAGS['BULLET'], 1)[0].split("\n")[0].strip()
        bullets = re.findall(rf"{PPT_TAGS['BULLET']}：(.*)", block)
        notes_match = re.search(rf"{PPT_TAGS['NOTES']}：(.*)", block)
        notes = notes_match.group(1).strip() if notes_match else ""
        if slide_title:
            slides.append({
                "title": slide_title,
                "bullet_points": [b.strip() for b in bullets],
                "notes": notes,
            })

    if slides:
        try:
            return _render_ppt_data(
                {"title": title, "slides": slides},
                ppt_theme,
            )
        except Exception as exc:
            logger.warning("PPT 旧版标签渲染失败：%s", exc)

    return _format_failure("ppt", raw, "未找到幻灯片结构")


def parse_resource(rtype: str, raw: str, ppt_theme: str = "dark_tech") -> str:
    """根据资源类型解析并返回展示文本。"""
    if rtype == "mindmap":
        return _parse_mindmap(raw)
    elif rtype == "document":
        return _parse_document(raw)
    elif rtype == "exercise":
        return _parse_exercise(raw)
    elif rtype == "ppt":
        return _parse_ppt(raw, ppt_theme)
    else:
        return raw


# ── 资源格式契约校验（无副作用） ────────────────────────
#
# 供消融实验等需要真实 format_pass 的场景使用：只判断产出是否符合该资源类型
# 声明的结构，不写文件、不实例化生成工具。format_pass 必须基于这里的结果，
# 而不是"raw 非空"——后者会把任何一段文本都算成格式通过。

def validate_resource_format(rtype: str, raw: str) -> bool:
    """判断 LLM 产出是否符合该资源类型的格式契约。"""
    text = (raw or "").strip()
    if not text:
        return False
    if rtype == "document":
        return _valid_document(text)
    if rtype == "mindmap":
        return _valid_mindmap(text)
    if rtype == "exercise":
        return _valid_exercise(text)
    if rtype == "ppt":
        return _valid_ppt(text)
    return True


def _valid_document(text: str) -> bool:
    """￥标题 + 至少一组 ￥段落标题/￥段落正文；兼容 JSON 降级格式。"""
    has_title = bool(re.search(rf"{DOCUMENT_TAGS['TITLE']}：\s*\S", text))
    headings = re.findall(rf"{DOCUMENT_TAGS['SECTION_TITLE']}：\s*(\S[^\n]*)", text)
    bodies = re.findall(rf"{DOCUMENT_TAGS['SECTION_BODY']}：\s*(\S)", text)
    if has_title and headings and bodies:
        return True
    data = _extract_json(text)
    if not data:
        return False
    try:
        DocumentOutput.model_validate(data)
        return True
    except Exception:
        return False


def _valid_mindmap(text: str) -> bool:
    data = _extract_json(text)
    if not data:
        return False
    try:
        mindmap = MindmapOutput.model_validate(data)
    except Exception:
        return False
    # 注意：MindmapOutput.branches 的 Field(min_length=1) 不校验缺省值，
    # 缺失 branches 时会退化成空列表，所以这里显式要求至少一个分支。
    return len(mindmap.branches) >= 1


def _valid_exercise(text: str) -> bool:
    """￥题目 + ￥答案（提示词要求的纯文本契约）；兼容 JSON 路径。"""
    has_question = bool(re.search(rf"{QUESTION_TAGS['QUESTION']}：\s*\S", text))
    has_answer = bool(re.search(rf"{QUESTION_TAGS['ANSWER']}：\s*\S", text))
    if has_question and has_answer:
        return True
    data = _extract_json(text)
    if not data:
        return False
    try:
        ex = ExerciseOutput.model_validate(data)
        return len(ex.items) >= 1
    except Exception:
        return False


def _valid_ppt(text: str) -> bool:
    data = _extract_json(text)
    if data:
        try:
            ppt = PPTOutput.model_validate(data)
            if ppt.slides:
                return True
        except Exception:
            pass
    # 兼容旧版 ￥标签 模板
    blocks = re.split(rf"{PPT_TAGS['SLIDE_TITLE']}：", text)
    return len(blocks) > 1 and any(block.strip() for block in blocks[1:])


def _topological_sort(nodes: list[dict]) -> list[dict]:
    """按依赖关系稳定排序；存在环或缺失依赖时保留原顺序。"""
    order = {node["id"]: index for index, node in enumerate(nodes)}
    ids = set(order)
    indegree = {node["id"]: 0 for node in nodes}
    edges: dict[str, list[str]] = {node["id"]: [] for node in nodes}

    for node in nodes:
        for dep in node.get("deps", []):
            if dep in ids:
                edges[dep].append(node["id"])
                indegree[node["id"]] += 1

    queue = sorted((node_id for node_id, degree in indegree.items() if degree == 0), key=order.get)
    result: list[dict] = []
    by_id = {node["id"]: node for node in nodes}
    while queue:
        node_id = queue.pop(0)
        result.append(by_id[node_id])
        for child in sorted(edges[node_id], key=order.get):
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
        queue.sort(key=order.get)

    return result if len(result) == len(nodes) else nodes


def _parse_path_nodes(raw: str) -> list[dict]:
    """解析学习路径 ￥节点 格式输出，返回结构化节点列表。"""
    import re
    
    nodes = []
    node_blocks = re.split(r"￥节点：", raw)
    
    for block in node_blocks:
        block = block.strip()
        if not block:
            continue
        
        # Extract node number and title before the （
        m = re.match(r"(\d+)\.(.+?)(?:（|$)", block)
        if not m:
            continue
        node_num = m.group(1)
        title = m.group(2).strip()
        
        # Extract fields from （...）
        type_val = "document"
        duration = ""
        knowledge_point = ""
        deps_str = "无"
        
        paren_match = re.search(r"（(.+?)）", block)
        if paren_match:
            content = paren_match.group(1)
            for part in content.split("，"):
                part = part.strip()
                if part.startswith("类型：") or part.startswith("类型:"):
                    type_val = part.split("：", 1)[-1].split(":", 1)[-1].strip() or "document"
                elif part.startswith("时长：") or part.startswith("时长:"):
                    duration = part.split("：", 1)[-1].split(":", 1)[-1].strip()
                elif part.startswith("知识点：") or part.startswith("知识点:"):
                    knowledge_point = part.split("：", 1)[-1].split(":", 1)[-1].strip()
                elif part.startswith("依赖：") or part.startswith("依赖:"):
                    deps_str = part.split("：", 1)[-1].split(":", 1)[-1].strip()
        
        deps = []
        if deps_str and deps_str != "无":
            deps = [d.strip() for d in deps_str.split(",") if d.strip()]
        deps = [f"node{d}" for d in deps if d.isdigit()]
        
        nodes.append({
            "id": f"node{node_num}",
            "title": title,
            "type": type_val,
            "duration": duration,
            "status": "pending",
            "deps": deps,
            "knowledge_point": knowledge_point,
            "resource_type": "",
            "resource_ref": "",
        })
    
    return _topological_sort(nodes)

