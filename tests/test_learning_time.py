import unittest

from core.learning_time_service import LearningTimeService


class FakeStore:
    def __init__(self):
        self.data = {}

    def get_data(self, key):
        return self.data.get(key)

    def save_data(self, key, data):
        self.data[key] = dict(data)


class LearningTimeTest(unittest.TestCase):
    def test_accumulates_today_and_total(self):
        store = FakeStore()
        service = LearningTimeService('student', store=store)
        service.record(30)
        summary = service.record(45)
        self.assertEqual(summary['today_seconds'], 75)
        self.assertEqual(summary['total_seconds'], 75)
        self.assertEqual(summary['today_minutes'], 1.2)

    def test_users_are_isolated(self):
        store = FakeStore()
        LearningTimeService('student', store=store).record(60)
        teacher = LearningTimeService('teacher', store=store).summary()
        self.assertEqual(teacher['today_seconds'], 0)
        self.assertEqual(teacher['total_seconds'], 0)


if __name__ == '__main__':
    unittest.main()