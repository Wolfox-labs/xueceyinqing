"""Crew 模块入口。

在任何 `from crewai import ...` 之前安装写入探测补丁：否则在"配置目录不可写"
的 Windows 环境里，crewai 首次导入会空转几十分钟（详见 core/crewai_compat.py）。
"""
from core.crewai_compat import install as _install_crewai_compat

_install_crewai_compat()