"""
审核助手 Agent — 生成内容质量审核 + 防幻觉 + 撤回/上报
"""
from crewai import Agent
from config import MODEL_LLM
from tools.review_tools import ReportIssueTool, WithdrawOutputTool


def create_reviewer_agent() -> Agent:
    return Agent(
        role="审核助手",
        goal="审核生成的学习资源，检查内容准确性，发现问题时上报日志，严重问题时撤回输出。",
        backstory=(
            "你是一位严谨的教研审核员，拥有丰富的学科知识。"
            "你逐条核对生成内容的准确性，标记任何与已知事实不符的表述，"
            "并对难度是否匹配用户水平给出来自第三方的客观评价。"
            "你拥有两个工具：ReportIssueTool 用于记录问题，"
            "WithdrawOutputTool 用于在内容严重不当时拦截输出。"
        ),
        llm=MODEL_LLM,
        tools=[ReportIssueTool(), WithdrawOutputTool()],
        verbose=False,
        allow_delegation=False,
    )
