---
title: "递归"
module: "函数与算法"
knowledge_point: "递归"
difficulty: "进阶"
prerequisites: ["函数"]
tags: ["python", "recursion"]
source: "Python 官方文档 / 算法讲义"
source_url: "https://docs.python.org/zh-cn/3/tutorial/controlflow.html"
---

# 递归

## 核心定义
递归是函数直接或间接调用自身。一个正确的递归必须包含：
- 基本情况：不再继续递归的终止条件。
- 递归关系：把原问题缩小为同类子问题。

## 示例
```python
def factorial(n: int) -> int:
    if n <= 1:
        return 1
    return n * factorial(n - 1)
```

## 调用栈
每次递归调用都会占用栈帧。递归深度过大时可能触发 `RecursionError`，此时可以考虑改用迭代或尾递归改写。

## 常见错误
- 缺少终止条件导致无限递归。
- 子问题规模没有缩小。
- 重复计算严重时，应加入记忆化或改造成动态规划。
