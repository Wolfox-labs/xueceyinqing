import unittest

from core.assessment_service import _select_unique_objective_items


class AssessmentObjectiveTest(unittest.TestCase):
    def test_only_objective_unique_questions_are_selected(self):
        items = [
            {"type": "single_choice", "question": "Python 列表如何创建？", "answer": "方括号"},
            {"type": "short_answer", "question": "解释列表", "answer": "可变序列"},
            {"type": "single_choice", "question": "Python 列表如何创建？", "answer": "方括号"},
            {"type": "true_false", "question": "列表是可变的。", "answer": "对"},
            {"type": "multi_choice", "question": "历史题目", "answer": "A;B"},
        ]
        selected = _select_unique_objective_items(items, [["历史题目"]], 5)
        self.assertEqual([item["type"] for item in selected], ["single_choice", "true_false"])
        self.assertEqual([item["question"] for item in selected], ["Python 列表如何创建？", "列表是可变的。"])


if __name__ == "__main__":
    unittest.main()