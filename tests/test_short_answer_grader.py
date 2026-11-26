import json
import unittest
from unittest.mock import patch

from core import short_answer_grader


class ShortAnswerGraderTest(unittest.TestCase):
    def test_exact_answer_gets_full_score(self):
        result = short_answer_grader.grade_short_answer("列表是什么？", "列表是可变序列", "列表是可变序列")
        self.assertEqual(result["score"], 1.0)

    def test_semantically_similar_answer_is_not_zero(self):
        with patch.object(short_answer_grader, "_llm_score", return_value=None):
            result = short_answer_grader.grade_short_answer(
                "列表如何创建？",
                "列表是可变序列，可以用方括号或 list() 创建",
                "Python 列表可以使用中括号创建",
            )
        self.assertGreater(result["score"], 0.0)

    def test_empty_answer_is_zero(self):
        result = short_answer_grader.grade_short_answer("问题", "参考答案", "")
        self.assertEqual(result["score"], 0.0)

    def test_score_tool_supports_partial_short_answer(self):
        # ScoreTool 是 CrewAI 工具（导入即拉起 crewai），只在真正需要它的用例里
        # 导入；否则整个测试文件都会因为框架依赖而无法运行。
        from tools.exam_tools import ScoreTool

        exercise = {"title": "测试", "items": [
            {"question": "1+1=?", "answer": "2", "type": "short_answer", "score": 10, "knowledge_point": "算术"},
            {"question": "列表是什么？", "answer": "可变序列", "type": "short_answer", "score": 10, "knowledge_point": "列表"},
        ]}
        answers = [{"question": "1+1=?", "answer": "2"}, {"question": "列表是什么？", "answer": "可以修改的序列"}]
        with patch("tools.exam_tools.grade_short_answer", return_value={"score": 0.8, "reason": "部分正确", "missing_points": []}):
            data = json.loads(ScoreTool()._run(json.dumps(answers, ensure_ascii=False), json.dumps(exercise, ensure_ascii=False)))
        self.assertEqual(data["score"], 16.0)
        self.assertEqual(len(data["item_results"]), 2)


if __name__ == "__main__":
    unittest.main()