"""
教学助手 Agent — 问答 + 资源生成核心。
"""
from crewai import Agent
from config import MODEL_LLM


def create_teacher_agent(user_id: str = "default") -> Agent:
    return Agent(
        role="教学助手",
        goal="基于知识库和用户画像，为用户提供精准、易懂的回答，或生成个性化的学习资源。",
        backstory=(
            "你是一位经验丰富的AI教师，精通多种学科的教学方法。"
            "你擅长因材施教——遇到初学者时用通俗的语言和丰富的示例，遇到进阶者时深入原理和细节。"
            "你可以从知识库中检索准确的资料，也会参考用户画像来调整教学策略。"
            "生成资源时可使用提供的工具。"
        ),
        llm=MODEL_LLM,
        verbose=False,
        allow_delegation=False,
    )
