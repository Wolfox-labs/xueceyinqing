import unittest

from core.parsing import _parse_path_nodes


class PathParserTest(unittest.TestCase):
    def test_sorts_nodes_by_dependencies(self):
        raw = """￥节点：2.函数（类型：document，时长：30分钟，知识点：函数，依赖：1）
￥节点：1.变量（类型：document，时长：20分钟，知识点：变量，依赖：无）
￥节点：3.列表（类型：exercise，时长：20分钟，知识点：列表，依赖：2）"""
        nodes = _parse_path_nodes(raw)
        self.assertEqual([node["id"] for node in nodes], ["node1", "node2", "node3"])

    def test_cycle_falls_back_to_original_order(self):
        raw = """￥节点：1.A（依赖：2）
￥节点：2.B（依赖：1）"""
        nodes = _parse_path_nodes(raw)
        self.assertEqual([node["id"] for node in nodes], ["node1", "node2"])


if __name__ == "__main__":
    unittest.main()
