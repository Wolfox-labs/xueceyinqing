"""守住"审核不通过"的分级语义。

真实故障
--------
审核提示词把"建议 / 需注意 / 必须修复"都归到"不通过"，而旧代码只要看到
"不通过"就整篇撤回。于是一句"这个表述有点绝对"就能让一次 60 多秒的生成
成果全部作废——用户界面上只看到"内容已被审核撤回"，什么都拿不到。

现在：只有硬问题（严重错误 / 幻觉 / 跑题 / 违规）才拦截；措辞与深度建议
降级为"通过但有意见"，内容照常交付。
"""
import unittest

from tools.review_tools import (
    VERDICT_FAIL,
    VERDICT_PASS,
    VERDICT_PASS_WITH_NOTES,
    ReviewContext,
    is_blocking_reason,
    parse_verdict,
)


class BlockingReasonTest(unittest.TestCase):
    def test_hard_problems_block(self):
        for reason in (
            "审核结果：不通过。存在事实性错误：空集合不能用 {} 定义。",
            "审核结果：不通过。内容与主题完全跑题。",
            "审核结果：不通过。存在幻觉，引用了不存在的文献。",
            "审核结果：不通过。包含不当内容。",
        ):
            self.assertTrue(is_blocking_reason(reason), reason)

    def test_style_suggestions_do_not_block(self):
        for reason in (
            "审核结果：不通过。存在“不同类型不能直接运算”的绝对化表述，容易误导学习者。",
            "审核结果：不通过。难度略高于初学者，建议压缩。",
        ):
            self.assertFalse(is_blocking_reason(reason), reason)

    def test_empty_reason_is_not_blocking(self):
        self.assertFalse(is_blocking_reason(""))


class ReviewContextVerdictTest(unittest.TestCase):
    def test_style_fail_becomes_pass_with_notes(self):
        ctx = ReviewContext()
        ctx.set_verdict(VERDICT_FAIL, "审核结果：不通过。措辞过于绝对，建议改写。")
        self.assertFalse(ctx.is_withdrawn(), "措辞建议不应拦截交付")
        self.assertEqual(ctx.verdict(), VERDICT_PASS_WITH_NOTES)

    def test_hard_fail_still_withdraws(self):
        ctx = ReviewContext()
        ctx.set_verdict(VERDICT_FAIL, "审核结果：不通过。存在事实性错误。")
        self.assertTrue(ctx.is_withdrawn(), "事实性错误必须拦截")
        self.assertEqual(ctx.verdict(), VERDICT_FAIL)
        self.assertTrue(ctx.reason())

    def test_explicit_withdraw_tool_wins(self):
        """工具撤回是权威信号：即使判词是"通过"也不能放行。"""
        ctx = ReviewContext()
        ctx.withdraw("内容违规")
        ctx.set_verdict(VERDICT_PASS, "审核结果：通过。")
        self.assertTrue(ctx.is_withdrawn())
        self.assertEqual(ctx.reason(), "内容违规")

    def test_plain_pass(self):
        ctx = ReviewContext()
        ctx.set_verdict(VERDICT_PASS, "审核结果：通过。很好。")
        self.assertFalse(ctx.is_withdrawn())
        self.assertEqual(ctx.verdict(), VERDICT_PASS)

    def test_parse_verdict_fail_matched_before_pass(self):
        # "不通过"必须在"通过"之前匹配，否则会被子串命中。
        self.assertEqual(parse_verdict("审核结果：不通过。理由"), VERDICT_FAIL)


if __name__ == "__main__":
    unittest.main()