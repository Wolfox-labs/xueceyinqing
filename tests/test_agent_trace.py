"""公开摘要的边界，以及审核回传时 SSE 摘要与真实输入的一致性。"""

import sys
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core.agent_trace import agent_trigger_rules, public_summary
from core.deliberation import AdaptiveDeliberationRouter
from core.deliberation_service import DeliberationService


class PublicSummaryTest(unittest.TestCase):
    def test_reasoning_and_tool_records_are_not_displayed(self):
        result = public_summary(
            '<think>内部推理\n不应展示</think>\n'
            'Thought: hidden\nAction: search\nObservation: tool output\n'
            '- 缺少空列表的边界条件。\n2. **补充反例**。'
        )
        self.assertEqual(result, ['缺少空列表的边界条件。', '补充反例。'])

    def test_unclosed_reasoning_tag_is_not_displayed(self):
        self.assertEqual(public_summary('公开结论\n<analysis>内部内容'), ['公开结论'])

    def test_long_results_are_bounded(self):
        result = public_summary('\n'.join(['很长的内容' * 100] * 10))
        self.assertEqual(len(result), 3)
        self.assertTrue(all(len(point) <= 110 for point in result))


class DeliberationTraceTest(unittest.TestCase):
    def run_service(self, review, decision=None):
        builders = SimpleNamespace(**{
            name: Mock(return_value=name)
            for name in ('build_initial_answer_crew', 'build_critique_crew', 'build_review_crew', 'build_revision_crew')
        })
        service = DeliberationService.__new__(DeliberationService)
        service.teacher, service.critic, service.reviewer = object(), object(), object()
        service.tools = None
        service.router = AdaptiveDeliberationRouter()
        service.runner = Mock()
        outputs = ['未审核的初版内容']
        if decision and decision.requires_critic and decision.max_rounds:
            outputs.append('缺少反例')
        outputs.append('修订稿')
        service.runner.run.side_effect = [SimpleNamespace(raw=text) for text in outputs]
        service.review_pipeline = Mock()
        service.review_pipeline.execute.return_value = SimpleNamespace(raw=review, withdrawn=False)
        events = []
        with patch.dict(sys.modules, {'crews.deliberation': builders}):
            result = service.run('什么是变量？', decision=decision, on_status=events.append)
        return result, events, builders

    def test_revision_summary_uses_real_review_and_handoff(self):
        review = '{"status":"revise","reason":"遗漏边界条件","must_fix":["补充空列表情况"]}'
        result, events, builders = self.run_service(review)
        completed = {event['stage']: event for event in events if event['state'] == 'completed'}
        self.assertIn('补充空列表情况', completed['review_1']['summary'])
        self.assertIn('同一个教学 Agent', completed['review_1']['handoff'])
        self.assertIn('未再次核验', completed['revision_1']['handoff'])
        self.assertEqual(builders.build_revision_crew.call_args.kwargs['review'], review)
        self.assertEqual(result.raw, '修订稿')
        self.assertNotIn('未审核的初版内容', str(events))

    def test_pass_does_not_invent_a_revision(self):
        result, events, builders = self.run_service('{"status":"pass","reason":"核验通过","must_fix":[]}')
        builders.build_revision_crew.assert_not_called()
        self.assertFalse(any(event['stage'].startswith('revision') for event in events))
        self.assertEqual(result.raw, '未审核的初版内容')

    def test_withdraw_marks_trace_as_error(self):
        result, events, builders = self.run_service('{"status":"withdraw","reason":"严重错误","must_fix":[]}')
        self.assertTrue(result.withdrawn)
        self.assertEqual(events[-1]['state'], 'error')
        self.assertIn('停止交付', events[-1]['handoff'])
        builders.build_revision_crew.assert_not_called()

    def test_route_reports_score_and_actual_critic_schedule(self):
        decision = AdaptiveDeliberationRouter().route(
            '请设计一个学习系统并证明架构能够优化路径，同时分析边界条件和反例。'
        )
        _, events, builders = self.run_service('{"status":"pass","reason":"通过"}', decision)
        routing = events[0]['routing']
        self.assertEqual(routing['score'], decision.score)
        self.assertEqual(routing['reasons'], list(decision.reasons))
        self.assertTrue(routing['critic_scheduled'])
        builders.build_critique_crew.assert_called_once()

    def test_high_score_with_zero_rounds_does_not_claim_critic_is_scheduled(self):
        decision = AdaptiveDeliberationRouter().route('请设计一个完整系统，证明架构并分析边界条件。')
        self.assertTrue(decision.requires_critic)
        decision = replace(decision, max_rounds=0)
        _, events, builders = self.run_service('{"status":"pass"}', decision)
        self.assertFalse(events[0]['routing']['critic_scheduled'])
        self.assertEqual(events[0]['routing']['max_rounds'], 0)
        builders.build_critique_crew.assert_not_called()


class AgentTriggerRulesTest(unittest.TestCase):
    def test_rules_preserve_current_threshold_and_gates_without_extra_settings(self):
        config = {
            'critic_enabled': False, 'quiz_agent_enabled': True, 'reviewer_enabled': True,
            'orchestration_mode': 'multi_agent', 'deliberate_threshold': 0.81,
            'max_rounds': 2, 'profile_enabled': True, 'updated_at': 'internal',
        }
        rules = agent_trigger_rules(config)
        self.assertEqual(rules['deliberate_threshold'], 0.81)
        self.assertFalse(rules['critic_enabled'])
        self.assertNotIn('updated_at', rules)
        self.assertNotIn('profile_enabled', rules)


if __name__ == '__main__':
    unittest.main()
