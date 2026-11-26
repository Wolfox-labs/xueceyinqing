---
title: "单元测试与调试"
module: "工程实践"
knowledge_point: "工程实践"
difficulty: "进阶"
prerequisites: ["函数", "异常处理"]
tags: ["engineering", "test"]
source: "Python 官方文档 / 工程实践讲义"
source_url: "https://docs.python.org/zh-cn/3/library/unittest.html"
---

# 单元测试与调试

## 为什么需要测试
测试把“我认为它能工作”变成“有证据证明它在特定输入下能工作”。核心函数、接口边界和异常分支都应该有测试。

## unittest 示例
```python
import unittest

def add(a, b):
    return a + b

class TestAdd(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(1, 2), 3)
```

## 调试方法
- 使用最小可复现输入定位问题。
- 检查边界值、空值和非法输入。
- 使用日志记录状态，而不是只依赖 `print`。
- 先写失败测试，再修代码，最后回归测试。
