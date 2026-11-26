"""
出题助手 Agent — 根据主题和用户画像生成格式规范的检测题目。
"""
from crewai import Agent
from config import MODEL_LLM


def create_quiz_crafter_agent(user_id: str = "default") -> Agent:
    return Agent(
        role="出题助手",
        goal="根据指定主题和用户画像，生成格式规范的检测题目，确保题型多样、难度匹配、覆盖知识点。",
        backstory=(
            "你是教学助手的专属出题专家。"
            "你擅长根据学习主题设计检测题目，从知识库中提取关键知识点，"
            "结合用户画像中的薄弱点调整题目难度和侧重点。"
            "你输出的题目格式严格规范，便于系统解析和用户审阅。"
        ),
        llm=MODEL_LLM,
        verbose=False,
        allow_delegation=False,
    )
