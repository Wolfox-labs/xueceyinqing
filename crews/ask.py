"""/ask 命令的 Crew — 画像更新 → 个性化问答。"""
from crewai import Task, Crew, Process


def _build_context_section(context: str) -> str:
    if not context.strip():
        return ""
    return f"\n[对话历史]\n{context}\n---\n"


def _build_profile_task(profile_agent, question: str, context: str = "") -> Task:
    ctx = _build_context_section(context)
    return Task(
        description=(
            "根据用户当前的问题，分析其背景特征，更新用户画像。\n\n"
            f"用户当前问题：{question}\n\n"
            f"{ctx}"
            "请先调用 ProfileGetTool 获取当前画像，然后分析问题中可能隐含的：\n"
            "1. 学习阶段（入门/进阶/高级）\n"
            "2. 关注的学科或主题\n"
            "3. 可能的薄弱环节\n"
            "4. 学习偏好\n"
            "5. 语言风格偏好（简洁/详细、严肃/幽默等）\n"
            "6. 知识掌握度\n"
            "将这些信息融合后调用 ProfileUpdateTool 更新画像。\n"
            "只需要用一两句话简述你的分析判断，不要输出 JSON 数据或 Schema。"
        ),
        expected_output="分析判断简述",
        agent=profile_agent,
    )


def _build_answer_task(teacher, question: str, context: str = "") -> Task:
    ctx = _build_context_section(context)
    return Task(
        description=(
            f"用户问题：{question}\n\n"
            f"{ctx}"
            "请先调用 ProfileGetTool 获取最新用户画像，然后调用 KnowledgeSearchTool 检索相关知识。\n"
            "基于检索到的知识和用户画像，给出个性化回答。\n"
            "直接开始回答用户的问题，不要展示画像分析、内部操作或工具调用过程。\n\n"
            "回答格式要求：\n"
            "- 直接回答用户问题\n"
            "- 用 Markdown 组织内容，但不要过度使用 emoji\n"
            "- 根据用户学习阶段调整解释深度\n"
            "- 根据画像中的语言风格偏好调整语气\n"
            "- 如果知识库没有相关内容，可基于你的知识回答，但必须注明“知识库未命中，以下内容为模型补充”\n"
            "- 如果使用了 KnowledgeSearchTool 返回的内容，请在回答末尾增加“参考来源：”，只列检索结果中出现过的来源和知识点"
        ),
        expected_output="清晰、简洁、个性化的回答",
        agent=teacher,
    )


def build_profile_crew(profile_agent, question: str, context: str = "") -> Crew:
    """不输出中间过程的画像更新 Crew。"""
    return Crew(
        agents=[profile_agent],
        tasks=[_build_profile_task(profile_agent, question, context)],
        process=Process.sequential,
        stream=False,
        verbose=False,
    )


def build_ask_crew(profile_agent, teacher, question: str, context: str = "", tools=None) -> Crew:
    """兼容 CLI 与 Streamlit 的完整组合 Crew。"""
    if tools is not None:
        teacher.tools = tools
    return Crew(
        agents=[profile_agent, teacher],
        tasks=[
            _build_profile_task(profile_agent, question, context),
            _build_answer_task(teacher, question, context),
        ],
        process=Process.sequential,
        stream=True,
        verbose=False,
    )


