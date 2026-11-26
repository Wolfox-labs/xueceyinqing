"""守住 LLM 配置契约：MODEL_LLM 里只能有 crewai 认识的键。

背景（真实事故）
----------------
agents/*.py 是整份 `llm=MODEL_LLM` 交给 crewai 的。crewai 会把字典里
**每一个键**都透传给 `chat.completions.create()`，于是往 MODEL_LLM 里加一个
它不认识的键（曾经加过 `vision_model`），就会让**所有**大模型调用报：

    TypeError: Completions.create() got an unexpected keyword argument 'vision_model'

表现是"生成思维导图/文档、对话、出题、批改全部不能用"——一个键废掉整个系统，
而且报错发生在运行时的一次真实调用里，静态检查看不出来。
"""
import unittest

import config


#: crewai / OpenAI 兼容接口认识的键（新增键前请先确认它真的会被接口接受）
ALLOWED_KEYS = frozenset({
    "provider",
    "model",
    "base_url",
    "api_key",
    "temperature",
    "reasoning_effort",
})


class LLMConfigContractTest(unittest.TestCase):
    def test_model_llm_has_no_unknown_keys(self):
        unknown = set(config.MODEL_LLM) - ALLOWED_KEYS
        self.assertEqual(
            unknown,
            set(),
            "MODEL_LLM 里出现了 crewai 不认识的键 %s：它们会被透传给 "
            "chat.completions.create()，导致所有大模型调用抛 TypeError。"
            "请改放到 config 模块的独立常量里。" % sorted(unknown),
        )

    def test_vision_model_not_in_model_llm(self):
        """多模态模型名是独立常量，绝不能混进 MODEL_LLM。"""
        self.assertNotIn("vision_model", config.MODEL_LLM)
        self.assertTrue(config.VISION_MODEL, "VISION_MODEL 应至少回落到主模型")

    def test_agents_use_model_llm_dict_directly(self):
        """守住前提：如果哪天 agents 不再整份传 MODEL_LLM，这条约束才可以放宽。"""
        from pathlib import Path
        agents_dir = Path(__file__).resolve().parent.parent / "agents"
        sources = {p.name: p.read_text(encoding="utf-8") for p in agents_dir.glob("*.py")}
        self.assertTrue(
            any("llm=MODEL_LLM" in text for text in sources.values()),
            "没有 agent 再用 llm=MODEL_LLM；若已改为显式字段，请同步更新本测试",
        )


if __name__ == "__main__":
    unittest.main()