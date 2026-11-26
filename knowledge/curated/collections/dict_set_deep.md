---
title: "字典与集合"
module: "Python 集合类型"
knowledge_point: "字典与集合"
difficulty: "基础"
prerequisites: ["变量与类型"]
tags: ["python", "dict", "set"]
source: "Python 官方文档"
source_url: "https://docs.python.org/zh-cn/3/tutorial/datastructures.html"
---

# 字典与集合

## 字典
字典保存键值对，键必须可哈希。常用操作：
```python
user = {"name": "Tom", "age": 18}
age = user.get("age", 0)
user["city"] = "Beijing"
```
`get()` 可以避免键不存在时抛出 `KeyError`。

## 集合
集合用于去重和集合运算：
```python
a = {1, 2, 3}
b = {3, 4}
print(a & b)  # 交集
print(a | b)  # 并集
print(a - b)  # 差集
```

## 常见错误
- 把列表当作字典键。
- 遍历字典时修改字典大小。
- 误以为集合有稳定顺序。
