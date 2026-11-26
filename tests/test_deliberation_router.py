import unittest

from core.deliberation import AdaptiveDeliberationRouter, DeliberationMode
from core.deliberation_service import _parse_review_verdict


class DeliberationRouterTest(unittest.TestCase):
    def test_simple_question_uses_fast_path(self):
        router = AdaptiveDeliberationRouter()
        decision = router.route("什么是变量？")
        self.assertEqual(decision.mode, DeliberationMode.FAST)
        # 简单问题仍走"快速审核路径"：不做质疑，但保留 1 轮审核。
        # 旧实现这里是 0 轮，等于完全绕过审核（"什么是列表？"关键词得 0 分），
        # 已按"任何模式都必须过审核"的原则改为 1 轮。
        self.assertEqual(decision.max_rounds, 1)
        self.assertTrue(decision.requires_review)
        self.assertFalse(decision.requires_critic)

    def test_design_question_uses_deliberation_path(self):
        router = AdaptiveDeliberationRouter()
        decision = router.route(
            "请设计一个多智能体学习系统，并证明这种架构能够优化学习路径，"
            "同时分析它的边界条件和可能出现的反例。"
        )
        self.assertEqual(decision.mode, DeliberationMode.DELIBERATE)
        self.assertEqual(decision.max_rounds, 2)

    def test_low_mastery_hint_raises_mode(self):
        router = AdaptiveDeliberationRouter()
        decision = router.route(
            "请解释递归和迭代的区别",
            adaptive_hint={
                "knowledge_point": "算法基础",
                "priority": 0.80,
                "effective_mastery": 0.32,
                "forgetting_risk": 0.48,
            },
        )
        self.assertEqual(decision.mode, DeliberationMode.DELIBERATE)


class ReviewVerdictTest(unittest.TestCase):
    def test_json_verdict(self):
        verdict = _parse_review_verdict(
            '{"status":"revise","reason":"缺少边界条件","must_fix":["补充空列表情况"]}'
        )
        self.assertEqual(verdict.status, "revise")
        self.assertEqual(verdict.must_fix, ["补充空列表情况"])

    def test_natural_language_withdraw(self):
        verdict = _parse_review_verdict("存在严重错误，必须撤回。")
        self.assertEqual(verdict.status, "withdraw")


if __name__ == "__main__":
    unittest.main()
