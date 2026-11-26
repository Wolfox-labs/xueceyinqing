"""
画像助手 Agent — 自动从对话中抽取用户特征。
"""
from crewai import Agent
from config import MODEL_LLM
from tools.profile_store import ProfileGetTool, ProfileUpdateTool


def create_profile_agent(user_id: str = "default") -> Agent:
    return Agent(
        role="画像助手",
        goal="从用户对话中自动抽取学习阶段、知识薄弱点、偏好、语言风格等特征，构建并持续更新用户画像。",
        backstory=(
            "你是一位教育数据分析师，善于从只言片语中洞察学生的背景。"
            "每次对话，你需要识别用户关心的话题、暴露的知识盲点、偏好的学习方式、"
            "以及用户的语言风格偏好（如简洁/详细、严肃/幽默、学术/口语等），"
            "将它们整理成一段流畅的用户画像描述。"
        ),
        llm=MODEL_LLM,
        tools=[ProfileGetTool(user_id), ProfileUpdateTool(user_id)],
        verbose=False,
        allow_delegation=False,
    )
