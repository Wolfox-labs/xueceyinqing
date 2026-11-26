"""
/gen 命令的 Crew — 资源生成 → 质量审核。
"""
import json

from crewai import Task, Crew, Process
from schemas import MindmapOutput
from schemas.resources import QUESTION_TAGS, DOCUMENT_TEMPLATE, PPT_TEMPLATE
from agents.quiz_crafter import create_quiz_crafter_agent


# ── 辅助函数 ────────────────────────────────────────────

def schema_to_prompt(schema_class) -> str:
    """从 Pydantic schema 生成占位符示例 JSON，供 LLM 理解输出格式。"""
    schema = schema_class.model_json_schema()

    def _example(props, defs):
        result = {}
        for key, prop in props.items():
            ref = prop.get("$ref", "")
            if ref:
                ref_name = ref.split("/")[-1]
                ref_props = defs[ref_name]["properties"]
                result[key] = [_example(ref_props, defs)] if prop.get("type") == "array" else _example(ref_props, defs)
            elif prop.get("type") == "array":
                items = prop.get("items", {})
                if items.get("type") == "string":
                    result[key] = [f"<{key}_内容>"]
                elif "$ref" in items:
                    ref_name = items["$ref"].split("/")[-1]
                    result[key] = [_example(defs[ref_name]["properties"], defs)]
                else:
                    result[key] = ["<内容>"]
            elif prop.get("type") == "string":
                result[key] = prop.get("enum", [None])[0] or f"<{key}>"
            elif prop.get("type") == "integer":
                result[key] = 0
            elif prop.get("type") == "number":
                result[key] = 0.0
        return result

    example = _example(schema["properties"], schema.get("$defs", {}))
    return (
        "请输出一个纯 JSON 对象（不要用 ```json 包裹，不要加任何说明文字），格式如下：\n"
        f"{json.dumps(example, ensure_ascii=False, indent=2)}"
    )


# ── 资源类型描述 ───────────────────────────────────────

TYPE_MAP = {}


# ── JSON → Mermaid mindmap 转换器 ─────────────────────

def json_to_mindmap_html(data: dict) -> str:
    """将 JSON 结构转为 HTML 树形思维导图。"""
    def _esc(text: str) -> str:
        return str(text).strip().replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    lines = ['<div class="mindmap">']
    root = _esc(data.get("root", "主题"))
    lines.append(f'<div class="mindmap-root">{root}</div>')
    lines.append('<ul class="mindmap-branches">')
    for branch in data.get("branches", []):
        label = _esc(branch.get("label", ""))
        lines.append(f'<li class="mindmap-branch"><strong>{label}</strong>')
        children = branch.get("children", [])
        if children:
            lines.append('<ul>')
            for child in children:
                lines.append(f'<li>{_esc(child)}</li>')
            lines.append('</ul>')
        lines.append('</li>')
    lines.append('</ul>')
    lines.append('</div>')
    return '\n'.join(lines)


def _build_context_section(context: str) -> str:
    if not context.strip():
        return ""
    return f"\n[参考资料与上下文]\n{context}\n---\n"


def build_gen_crew(teacher, reviewer, resource_type: str, topic: str,
                   context: str = "", tools=None, user_id: str = "default",
                   use_quiz_agent: bool = True, enable_reviewer: bool = True) -> Crew:
    ctx = _build_context_section(context)

    # ── 按资源类型选择生成代理 ──
    if resource_type == "exercise" and use_quiz_agent:
        gen_agent = create_quiz_crafter_agent(user_id)
    else:
        gen_agent = teacher

    if tools is not None:
        gen_agent.tools = tools

    # ── 按资源类型构建 schema 提示 ──
    if resource_type == "mindmap":
        type_desc = f"思维导图 — {schema_to_prompt(MindmapOutput)}"
    elif resource_type == "document":
        type_desc = DOCUMENT_TEMPLATE
    elif resource_type == "exercise":
        type_desc = (
            f"练习题库 — 请严格按照以下 $标签 格式输出题目，每题以 ### 第N题 分隔：\n"
            f"### 第1题\n"
            f"{QUESTION_TAGS['TYPE']}：单选题\n"
            f"{QUESTION_TAGS['KNOWLEDGE']}：知识点名称\n"
            f"{QUESTION_TAGS['QUESTION']}：题目内容\n"
            f"{QUESTION_TAGS['OPTION'].format('A')}：选项内容\n"
            f"{QUESTION_TAGS['OPTION'].format('B')}：选项内容\n"
            f"{QUESTION_TAGS['ANSWER']}：A\n"
            f"{QUESTION_TAGS['EXPLAIN']}：解析内容\n"
            f"{QUESTION_TAGS['DIFFICULTY']}：基础\n\n"
            f"必须包含至少3道题，题型多样化（单选题、多选题、判断题、简答题）。"
            f"知识点字段填写具体的知识点名称（如'列表推导式'）。"
            f"难度可选：基础/进阶/综合。"
            f"不要输出JSON，不要输出代码块，直接输出纯文本。"
        )
    elif resource_type == "ppt":
        type_desc = PPT_TEMPLATE
    else:
        type_desc = resource_type

    gen_task = Task(
        description=(
            f"生成一份个性化学习资源。\n"
            f"资源类型：{type_desc}\n"
            f"主题：{topic}\n\n"
            f"{ctx}"
            "请先调用 ProfileGetTool 获取当前用户画像，根据用户的水平调整内容难度和深度。\n"
            "如果提供了用户上传的参考资料，必须优先依据这些资料生成内容，并在正文中自然标注对应资料名称。\n"
            "不要编造参考资料中不存在的数据、结论或出处。\n"
            "确保内容准确、结构清晰、适合自学。\n"
            "严格按照指定的格式输出内容。"
        ),
        expected_output=f"围绕'{topic}'的个性化{type_desc}",
        agent=gen_agent,
    )

    review_task = Task(
        description=(
            "审核刚才生成的学习资源内容。\n\n"
            "你有两个工具可用：\n"
            "- ReportIssueTool(severity, description)：上报发现的问题到日志\n"
            "  severity 取值：low（小建议）/ medium（需注意）/ high（必须修复）/ critical（禁止输出）\n"
            "- WithdrawOutputTool(reason)：撤回/拦截内容，阻止展示给用户\n\n"
            "审查流程：\n"
            "1. 检查内容是否有事实性错误或幻觉 → 有则调用 ReportIssueTool 上报\n"
            "2. 检查是否包含不当内容（违规、跑题、胡言乱语）→ 是则立即调用 WithdrawOutputTool 撤回\n"
            "3. 检查难度是否匹配用户水平、结构是否完整、表述是否清晰\n"
            "4. 汇总审核结论\n\n"
            "⚠ 判词与后果（务必按此区分，不要把【可以发布】的内容判成不通过）：\n"
            "- 只有出现**严重问题**（事实性错误、幻觉、违规、完全跑题）才写"
            "'审核结果：不通过。'——这会拦截整篇内容，用户什么都拿不到。\n"
            "- 如果内容本身可以发布，只是措辞可以更严谨、深度可以调整、结构可以更好，"
            "请写'审核结果：通过。'，然后把建议用 ReportIssueTool 以 low/medium 上报，"
            "并在简评里点明。这类意见不影响交付。\n"
            "- 把'不通过'留给真正不能给学生看的内容。\n\n"
            "输出要求：\n"
            "- 只输出审核结论，格式固定为'审核结果：通过/不通过'加一行理由\n"
            "- 如果合格，输出'审核结果：通过。'加一句简评（不超过30字）\n"
            "- 如果发现问题，输出'审核结果：不通过。'加具体理由\n"
            "- 绝对不要重复输出资源原文，绝对不要输出 JSON 数据\n"
            "- 如果调用了 WithdrawOutputTool，只输出撤回原因"
        ),
        expected_output="审核结论（一行通过/不通过 + 简短理由，无原文）",
        agent=reviewer,
    )

    if not enable_reviewer:
        return Crew(
            agents=[gen_agent],
            tasks=[gen_task],
            process=Process.sequential,
            stream=True,
            verbose=False,
        )

    crew_agents = [gen_agent] if resource_type == "exercise" and use_quiz_agent else [teacher]

    return Crew(
        agents=[*crew_agents, reviewer],
        tasks=[gen_task, review_task],
        process=Process.sequential,
        stream=True,
        verbose=False,
    )
