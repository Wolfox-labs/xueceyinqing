"""
全局配置 — 集中管理 LLM、路径等设置。

推荐在项目根目录创建 .env：
    LLM_PROVIDER=openai
    LLM_MODEL=your-model-id
    LLM_BASE_URL=https://your-api.example.com/v1
    LLM_API_KEY=your-key

可选：图片/扫描件识别单独指定模型（默认复用 LLM_MODEL）：
    VISION_MODEL=qwen3-vl-plus

为兼容旧版本，仍支持 MODEL、MIMO_API_KEY、DEEPSEEK_API_KEY、OPENAI_API_KEY。
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# 确保从项目根目录加载 .env
load_dotenv(Path(__file__).parent / ".env")


def _first_env(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    return None


_llm_provider = os.getenv("LLM_PROVIDER", os.getenv("PROVIDER", "openai")).strip()
_llm_model = _first_env("LLM_MODEL", "MODEL") or "deepseek-chat"
_llm_base_url = (_first_env("LLM_BASE_URL", "BASE_URL")
                 or "https://api.deepseek.com/v1").rstrip("/")
_llm_api_key = _first_env(
    "LLM_API_KEY",
    "MIMO_API_KEY",
    "DEEPSEEK_API_KEY",
    "OPENAI_API_KEY",
)

MODEL_LLM = {
    "provider": _llm_provider,
    "model": _llm_model,
    "base_url": _llm_base_url,
    "api_key": _llm_api_key,
}

# ⚠ 不要往 MODEL_LLM 里加任何"不被 crewai / OpenAI 接口认识"的键。
# agents/*.py 是整份 `llm=MODEL_LLM` 交给 crewai 的，crewai 会把字典里每个键
# 都透传给 chat.completions.create()，多一个键就是一次
# `TypeError: Completions.create() got an unexpected keyword argument 'xxx'`，
# 结果是**所有**大模型调用全挂（生成、对话、出题、批改一个都跑不了）。
#   · "provider" / "model" / "base_url" / "api_key" / "temperature" /
#     "reasoning_effort" 是 crewai 认识的，可以放；
#   · 其余一律放到本模块的独立常量里（例如下面的 VISION_MODEL）。
# 这条约束由 tests/test_llm_config.py 守着。

# 图片/扫描件识别用的模型：默认复用主模型（多模态模型如 qwen3.8-flash 可直接读图），
# 也可用 VISION_MODEL 单独指定（例如 qwen3-vl-plus / qwen-vl-ocr），按成本与精度取舍。
# 单独成常量、**不进 MODEL_LLM**，原因见上面的警告。
VISION_MODEL = _first_env("VISION_MODEL") or _llm_model

_llm_temperature = _first_env("LLM_TEMPERATURE")
if _llm_temperature is not None:
    MODEL_LLM["temperature"] = float(_llm_temperature)

_llm_reasoning_effort = _first_env("LLM_REASONING_EFFORT")
if _llm_reasoning_effort is not None:
    MODEL_LLM["reasoning_effort"] = _llm_reasoning_effort

# CrewAI 的部分 OpenAI 兼容适配器会读取这个标准环境变量。
# 仅在用户没有自行配置时回填，不会覆盖已有设置。
if _llm_api_key and _llm_provider.lower() in {"openai", "openai-compatible", "compatible"}:
    os.environ.setdefault("OPENAI_API_KEY", _llm_api_key)





