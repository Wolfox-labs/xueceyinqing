"""
Agent 模块统一入口 — 返回全部常驻 Agent 及按需 Agent。
"""
# 必须在任何 `from crewai import ...` 之前安装：否则在"配置目录不可写"的
# Windows 环境里，crewai 首次导入会空转几十分钟（详见 core/crewai_compat.py）。
from core.crewai_compat import install as _install_crewai_compat

_install_crewai_compat()

from agents.profile import create_profile_agent
from agents.teacher import create_teacher_agent
from agents.reviewer import create_reviewer_agent
from agents.critic import create_critic_agent


def create_agents(user_id: str = "default"):
    """创建常驻的画像、教学、审核三类 Agent。"""
    return (
        create_profile_agent(user_id),
        create_teacher_agent(user_id),
        create_reviewer_agent(),
    )


def create_deliberation_agents(user_id: str = "default"):
    """创建协商链路所需的 Agent；质疑助手按需加入。"""
    profile_agent, teacher, reviewer = create_agents(user_id)
    return profile_agent, teacher, reviewer, create_critic_agent(user_id)


__all__ = [
    "create_agents",
    "create_deliberation_agents",
    "create_profile_agent",
    "create_teacher_agent",
    "create_reviewer_agent",
    "create_critic_agent",
]
