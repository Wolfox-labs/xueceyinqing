"""质疑助手 Agent — 对教学初答进行反例、漏洞和前置知识检查。"""

from crewai import Agent

from config import MODEL_LLM
from tools.knowledge import KnowledgeSearchTool
from tools.profile_store import ProfileGetTool


def create_critic_agent(user_id: str = "default") -> Agent:
    return Agent(
        role="质疑助手",
        goal=(
            "从反例、边界条件、逻辑跳跃、前置知识缺失和事实证据不一致等角度"
            "审视教学助手的初版回答，只提出问题，不直接替学习者生成最终答案。"
        ),
        backstory=(
            "你是一位严格的课程评审员和反例设计专家。你的职责不是赞同教学助手，"
            "而是找出回答中可能误导学习者的地方：概念是否准确、推理是否完整、"
            "示例是否覆盖边界条件、难度是否匹配用户画像。"
            "你只能提出可验证、具体、可修订的问题；如果没有实质性问题，应明确说明。"
        ),
        llm=MODEL_LLM,
        tools=[KnowledgeSearchTool(), ProfileGetTool(user_id)],
        verbose=False,
        allow_delegation=False,
    )
