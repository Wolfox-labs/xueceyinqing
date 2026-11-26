import unittest
from datetime import datetime, timedelta, timezone

from core.adaptive_engine import AdaptiveLearningEngine, ContextualUCBPolicy, KnowledgeNode, MasteryState


class AdaptiveEngineTest(unittest.TestCase):
    def test_mastery_increases_after_correct_evidence(self):
        engine = AdaptiveLearningEngine()
        state = MasteryState('函数', mastery=0.4)
        engine.update_mastery(state, 1.0)
        self.assertGreater(state.mastery, 0.4)
        self.assertEqual(state.evidence_count, 1)

    def test_mastery_stays_in_range(self):
        engine = AdaptiveLearningEngine()
        state = MasteryState('函数', mastery=0.95)
        for _ in range(20):
            engine.update_mastery(state, 1.0)
        self.assertLessEqual(state.mastery, 1.0)

    def test_forgetting_reduces_effective_mastery(self):
        engine = AdaptiveLearningEngine(default_half_life_days=7)
        now = datetime(2026, 9, 28, tzinfo=timezone.utc)
        state = MasteryState('算法', mastery=0.8, last_practiced=now - timedelta(days=7))
        effective = engine.effective_mastery(state, now=now)
        self.assertAlmostEqual(effective, 0.4, places=6)

    def test_weak_and_dependent_topic_ranks_higher(self):
        engine = AdaptiveLearningEngine()
        now = datetime(2026, 9, 28, tzinfo=timezone.utc)
        weak = MasteryState('算法', mastery=0.3, last_practiced=now - timedelta(days=10))
        strong = MasteryState('函数', mastery=0.9, last_practiced=now)
        graph = {
            '算法': KnowledgeNode('算法', importance=0.9, prerequisites=('动态规划', '图搜索')),
            '函数': KnowledgeNode('函数', importance=0.5),
        }
        result = engine.recommend([strong, weak], graph, recent_errors={'算法': 2}, now=now)
        self.assertEqual(result[0].knowledge_point, '算法')

    def test_contextual_policy_explores_then_exploits(self):
        policy = ContextualUCBPolicy(exploration=0.5)
        context = policy.context_key(mastery=0.3, urgency=0.8, learning_style='visual')
        self.assertEqual(policy.select(context, ['explain', 'practice']), 'explain')
        policy.update(context, 'explain', 1.0)
        self.assertEqual(policy.select(context, ['explain', 'practice']), 'practice')
        policy.update(context, 'practice', 0.1)
        self.assertEqual(policy.select(context, ['explain', 'practice']), 'explain')


if __name__ == '__main__':
    unittest.main()
