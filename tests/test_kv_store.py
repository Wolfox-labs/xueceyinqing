import tempfile
import unittest
from pathlib import Path

from db.kv_store import SQLiteKVStore


class KVStoreTest(unittest.TestCase):
    def test_dict_roundtrip_and_prefix(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteKVStore(str(Path(directory) / "test.db"))
            store.save_data("assessment_student_1", {"score": 80})
            store.save_data("assessment_student_2", {"score": 90})
            self.assertEqual(store.get_data("assessment_student_1"), {"score": 80})
            self.assertEqual(len(store.list_data_by_prefix("assessment_student_")), 2)

    def test_text_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteKVStore(str(Path(directory) / "test.db"))
            store.set_text("user_student", "学习阶段：入门")
            self.assertEqual(store.get_text("user_student"), "学习阶段：入门")


if __name__ == "__main__":
    unittest.main()