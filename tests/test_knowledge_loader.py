import unittest

from db.vector_store import _chunk_markdown, _parse_front_matter


class KnowledgeLoaderTest(unittest.TestCase):
    def test_front_matter_parsing(self):
        text = "---\ntitle: \"列表创建\"\nknowledge_point: \"列表创建\"\nprerequisites: [\"变量与类型\"]\n---\n\n# 列表创建\n正文"
        meta, body = _parse_front_matter(text)
        self.assertEqual(meta["title"], "列表创建")
        self.assertEqual(meta["prerequisites"], ["变量与类型"])
        self.assertIn("正文", body)

    def test_markdown_chunking_preserves_all_content(self):
        text = "\n\n".join(["## 标题", "A" * 300, "B" * 300, "C" * 300])
        chunks = _chunk_markdown(text, limit=400)
        self.assertGreaterEqual(len(chunks), 2)
        merged = "\n\n".join(chunks)
        self.assertIn("A" * 300, merged)
        self.assertIn("C" * 300, merged)


if __name__ == "__main__":
    unittest.main()