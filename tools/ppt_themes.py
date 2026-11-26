"""PPT 主题注册表。

主题只负责视觉 token，版式由 renderer 负责组合。这样后续增加学校模板、
企业模板或用户上传模板时，不需要改内容生成逻辑。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class PPTTheme:
    key: str
    name: str
    description: str
    is_dark: bool
    bg: str
    bg_deep: str
    surface: str
    surface_alt: str
    primary: str
    secondary: str
    accent: str
    text: str
    muted: str
    border: str
    success: str
    warning: str
    font_title: str = "Microsoft YaHei"
    font_body: str = "Microsoft YaHei"
    font_code: str = "Consolas"


THEMES: dict[str, PPTTheme] = {
    "dark_tech": PPTTheme(
        key="dark_tech",
        name="深色科技风",
        description="深蓝黑底、青蓝强调色，适合算法讲解和技术展示。",
        is_dark=True,
        bg="0F172A",
        bg_deep="080D18",
        surface="162033",
        surface_alt="1E293B",
        primary="38BDF8",
        secondary="22D3EE",
        accent="8B5CF6",
        text="F8FAFC",
        muted="94A3B8",
        border="334155",
        success="22C55E",
        warning="F59E0B",
    ),
    "academic_clean": PPTTheme(
        key="academic_clean",
        name="学术简洁风",
        description="米白底、深蓝标题与青绿色强调，适合课堂、论文和正式汇报。",
        is_dark=False,
        bg="F7F8FA",
        bg_deep="E8EEF5",
        surface="FFFFFF",
        surface_alt="EEF2F7",
        primary="1E3A8A",
        secondary="0F766E",
        accent="B45309",
        text="0F172A",
        muted="64748B",
        border="D7DEE8",
        success="15803D",
        warning="B45309",
    ),
    "education_fresh": PPTTheme(
        key="education_fresh",
        name="清新教育风",
        description="浅绿与暖黄配色，适合通识课程、青少年教学和科普内容。",
        is_dark=False,
        bg="F7FBF5",
        bg_deep="E0F2E3",
        surface="FFFFFF",
        surface_alt="E8F5E9",
        primary="2E7D32",
        secondary="0288D1",
        accent="F9A825",
        text="1B2E1B",
        muted="607D5C",
        border="D6E8D2",
        success="2E7D32",
        warning="EF6C00",
    ),
    "business_blue": PPTTheme(
        key="business_blue",
        name="商务蓝风",
        description="标准商务蓝与暖橙点缀，适合教师培训、企业汇报和项目路演。",
        is_dark=False,
        bg="EEF3F9",
        bg_deep="DCE7F3",
        surface="FFFFFF",
        surface_alt="E1EAF5",
        primary="0F4C81",
        secondary="2F80ED",
        accent="F2994A",
        text="102A43",
        muted="627D98",
        border="C9D7E8",
        success="16876D",
        warning="D97706",
    ),
}

THEME_ALIASES = {
    "dark": "dark_tech",
    "tech": "dark_tech",
    "深色科技风": "dark_tech",
    "academic": "academic_clean",
    "学术简洁风": "academic_clean",
    "education": "education_fresh",
    "清新教育风": "education_fresh",
    "business": "business_blue",
    "商务蓝风": "business_blue",
}


def get_theme(key: str | None) -> PPTTheme:
    normalized = (key or "dark_tech").strip()
    normalized = THEME_ALIASES.get(normalized, normalized)
    return THEMES.get(normalized, THEMES["dark_tech"])


def list_themes() -> list[dict]:
    return [asdict(theme) for theme in THEMES.values()]
