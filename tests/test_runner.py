import unittest
from types import SimpleNamespace

from core.runner import CrewRunner


class FakeCrew:
    def __init__(self, result):
        self._result = result
        self.usage_metrics = {"total_tokens": 1}

    def kickoff(self):
        return self._result


class RunnerTest(unittest.TestCase):
    def test_plain_crew_output_uses_raw(self):
        result = CrewRunner.run(FakeCrew(SimpleNamespace(raw="完整回答")))
        self.assertEqual(result.raw, "完整回答")

    def test_streaming_chunks_use_content(self):
        chunks = [SimpleNamespace(content="第一"), SimpleNamespace(content="第二")]
        received = []
        result = CrewRunner.run(FakeCrew(chunks), on_chunk=received.append)
        self.assertEqual(result.raw, "第一第二")
        self.assertEqual(received, ["第一", "第二"])

    def test_string_result_is_supported(self):
        result = CrewRunner.run(FakeCrew("直接文本"))
        self.assertEqual(result.raw, "直接文本")


if __name__ == "__main__":
    unittest.main()