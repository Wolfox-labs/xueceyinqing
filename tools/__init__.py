"""工具模块入口。

很多工具直接 `from crewai_tools import BaseTool`，而 core/parsing.py 会直接
懒加载 tools.docx_tools / tools.pptx_tools，所以这里也必须先装写入探测补丁，
否则这条路径同样会撞上 crewai 的空转导入（详见 core/crewai_compat.py）。
"""
from core.crewai_compat import install as _install_crewai_compat

_install_crewai_compat()