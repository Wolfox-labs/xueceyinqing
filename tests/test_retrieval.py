import unittest

from db.vector_store import _lexical_rank_documents


class RetrievalTest(unittest.TestCase):
    def test_chinese_keyword_ranks_relevant_document_first(self):
        docs = [
            "Python 列表可以通过方括号创建，也可以使用 list() 转换。",
            "字符串是不可变序列，可以使用索引访问。",
            "函数用于封装可复用逻辑。",
        ]
        result = _lexical_rank_documents(docs, "列表怎么创建", 2)
        self.assertTrue(result)
        self.assertIn("列表", result[0])

    def test_english_keyword_is_supported(self):
        docs = ["Python list creation", "File I/O exceptions"]
        result = _lexical_rank_documents(docs, "list creation", 1)
        self.assertEqual(result, ["Python list creation"])


if __name__ == "__main__":
    unittest.main()
