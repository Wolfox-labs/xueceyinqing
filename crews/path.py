"""
/path 命令的 Crew — 学习路径生成。
"""
from crewai import Task, Crew, Process


def build_path_crew(teacher, user_id: str, topic: str,
                    profile_text: str = "", tools=None) -> Crew:
    if tools is not None:
        teacher.tools = tools

    profile_section = ""
    if profile_text.strip():
        profile_section = f"用户画像：{profile_text}\n"

    task = Task(
        description=(
            f"基于以下信息生成个性化学习路径：\n"
            f"{profile_section}"
            f"主题：{topic}\n\n"
            f"请先调用 KnowledgeSearchTool 查看知识库中与主题相关的知识点，"
            f"规划一条从基础到进阶的学习路径。\n\n"
            f"请严格按照以下格式输出每个节点（纯文本，不要输出JSON）：\n\n"
            f"￥节点：1.节点标题（类型：资源类型，时长：学习时长，知识点：具体知识点名称，依赖：前置节点序号）\n"
            f"￥节点：2.节点标题（类型：资源类型，时长：学习时长，知识点：具体知识点名称，依赖：前置节点序号）\n"
            f"￥节点：3.节点标题（类型：资源类型，时长：学习时长，知识点：具体知识点名称，依赖：前置节点序号）\n\n"
            f"要求：\n"
            f"- 每行以\"￥节点：\"开头，行末不加分号\n"
            f"- 节点数量 5~10 个\n"
            f"- 类型可选：document(讲解文档)、mindmap(思维导图)、exercise(练习题)、ppt(演示文稿)\n"
            f"- 时长单位：分钟（如\"30分钟\"）\n"
            f"- 知识点：填写具体的知识点名称\n"
            f"- 依赖：填写前置节点的序号，多个用逗号分隔如\"1,2\"，首个节点填\"无\"\n"
            f"- 不要输出JSON，不要输出代码块，直接输出纯文本\n"
            f"- 不要加任何说明文字，直接输出节点列表"
        ),
        expected_output="学习路径节点（￥标签格式）",
        agent=teacher,
    )

    return Crew(
        agents=[teacher],
        tasks=[task],
        process=Process.sequential,
        stream=True,
        verbose=False,
    )
