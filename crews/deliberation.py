"""有限轮次多智能体协商的 Crew 构建器。

每一步使用独立的单任务 Crew，由 DeliberationService 控制调用顺序和停止条件。
这样可以让质疑、审核、修订的输入输出可控，也方便 SSE 返回协作状态。
"""

from __future__ import annotations

from typing import Mapping

from crewai import Crew, Process, Task

from core.deliberation import DeliberationDecision


def _clip(text: str, limit: int = 7000) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[内容已截断]"


def _context_section(context: str) -> str:
    if not context or not context.strip():
        return ""
    return f"\n[对话历史]\n{_clip(context, 3000)}\n---\n"


def _profile_section(profile_text: str) -> str:
    if not profile_text or not profile_text.strip():
        return ""
    return f"\n[学习者画像]\n{_clip(profile_text, 1800)}\n"


def _adaptive_section(decision: DeliberationDecision | None) -> str:
    if not decision or not decision.adaptive_hint:
        return "\n[自适应策略]\n暂无特定知识点策略提示。\n"

    hint: Mapping = decision.adaptive_hint
    parts = []
    for key, label in (
        ("knowledge_point", "优先知识点"),
        ("effective_mastery", "有效掌握度"),
        ("forgetting_risk", "遗忘风险"),
        ("priority", "推荐优先级"),
        ("target_difficulty", "目标难度"),
        ("reason", "策略理由"),
    ):
        value = hint.get(key)
        if value is not None and str(value).strip():
            if isinstance(value, float):
                value = f"{value:.2%}"
            parts.append(f"- {label}: {value}")
    return "\n[自适应策略]\n" + "\n".join(parts) + "\n"


def _single_task_crew(agent, task: Task) -> Crew:
    return Crew(
        agents=[agent],
        tasks=[task],
        process=Process.sequential,
        stream=False,
        verbose=False,
    )


def build_initial_answer_crew(
    teacher,
    question: str,
    *,
    context: str = "",
    profile_text: str = "",
    decision: DeliberationDecision | None = None,
    tools=None,
) -> Crew:
    if tools is not None:
        teacher.tools = tools

    task = Task(
        description=(
            f"用户问题：{question}\n"
            f"{_context_section(context)}"
            f"{_profile_section(profile_text)}"
            f"{_adaptive_section(decision)}"
            "请先调用 ProfileGetTool 获取最新画像，再调用 KnowledgeSearchTool 检索相关知识。\n"
            "给出一版适合当前学习者的初版回答，要求概念准确、结构清晰、难度匹配。\n"
            "直接回答用户问题，不要展示画像分析、工具调用、内部推理或审核过程。\n"
            "如果使用了知识库检索结果，请在回答末尾列出“参考来源：”，只列实际命中的来源和知识点；如果未命中知识库，必须注明“知识库未命中，以下内容为模型补充”。"
        ),
        expected_output="学生可读的初版回答",
        agent=teacher,
    )
    return _single_task_crew(teacher, task)


def build_critique_crew(
    critic,
    question: str,
    draft: str,
    *,
    context: str = "",
    decision: DeliberationDecision | None = None,
    tools=None,
) -> Crew:
    if tools is not None:
        critic.tools = tools

    task = Task(
        description=(
            "你是质疑助手。请严格审视下面的教学初版回答，只找问题，不重写答案。\n\n"
            f"用户问题：{question}\n"
            f"{_context_section(context)}"
            f"{_adaptive_section(decision)}"
            f"\n[初版回答]\n{_clip(draft)}\n\n"
            "重点检查：\n"
            "1. 概念、事实和示例是否准确；\n"
            "2. 推理是否存在逻辑跳跃；\n"
            "3. 是否遗漏必要的前置知识；\n"
            "4. 是否覆盖边界条件、反例和常见误区；\n"
            "5. 讲解难度和表达方式是否匹配画像。\n\n"
            "如果有问题，按“问题编号 + 问题描述 + 修订要求”输出；"
            "如果没有实质性问题，只输出：未发现实质性漏洞。"
        ),
        expected_output="质疑问题清单或“未发现实质性漏洞”",
        agent=critic,
    )
    return _single_task_crew(critic, task)


def build_review_crew(
    reviewer,
    question: str,
    draft: str,
    *,
    critique: str = "",
    profile_text: str = "",
    decision: DeliberationDecision | None = None,
) -> Crew:
    critique_section = f"\n[质疑意见]\n{_clip(critique, 3500)}\n" if critique.strip() else ""
    task = Task(
        description=(
            "请审核下面的教学回答。你不是重写答案，而是判断它是否可以安全展示给学习者。\n\n"
            f"用户问题：{question}\n"
            f"{_profile_section(profile_text)}"
            f"{_adaptive_section(decision)}"
            f"\n[待审核回答]\n{_clip(draft)}\n"
            f"{critique_section}\n"
            "审核流程：\n"
            "1. 核对事实、概念和知识库证据；\n"
            "2. 检查是否存在严重幻觉、违规内容或完全跑题；\n"
            "3. 对有风险的问题调用 ReportIssueTool；\n"
            "4. 严重问题时必须调用 WithdrawOutputTool 撤回；\n"
            "5. 输出一个 JSON 对象，不要输出回答原文。\n\n"
            'JSON 格式：{"status":"pass|revise|withdraw","reason":"一句话原因","must_fix":["需要修订的点"]}'
        ),
        expected_output='审核 JSON：{"status":"pass|revise|withdraw","reason":"...","must_fix":[]}',
        agent=reviewer,
    )
    return _single_task_crew(reviewer, task)


def build_revision_crew(
    teacher,
    question: str,
    draft: str,
    *,
    critique: str = "",
    review: str = "",
    context: str = "",
    profile_text: str = "",
    decision: DeliberationDecision | None = None,
    tools=None,
) -> Crew:
    if tools is not None:
        teacher.tools = tools

    critique_section = f"\n[质疑意见]\n{_clip(critique, 3500)}\n" if critique.strip() else ""
    review_section = f"\n[审核结论]\n{_clip(review, 2200)}\n" if review.strip() else ""
    task = Task(
        description=(
            "请根据质疑意见和审核结论修订教学回答。\n\n"
            f"用户问题：{question}\n"
            f"{_context_section(context)}"
            f"{_profile_section(profile_text)}"
            f"{_adaptive_section(decision)}"
            f"\n[初版回答]\n{_clip(draft)}\n"
            f"{critique_section}"
            f"{review_section}\n"
            "修订要求：\n"
            "- 只修正确有依据的问题；\n"
            "- 删除未经知识库或可靠知识支持的内容；\n"
            "- 补充必要的前置知识、边界条件和例子；\n"
            "- 保持适合当前学习者的难度和表达方式；\n"
            "- 最终只输出学生版回答；保留或补全“参考来源：”信息，不提及质疑、审核、协商或 Agent。"
        ),
        expected_output="学生版最终回答",
        agent=teacher,
    )
    return _single_task_crew(teacher, task)
