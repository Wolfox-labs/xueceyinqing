---
title: "输入输出"
module: "Python 基础语法"
knowledge_point: "输入输出"
difficulty: "基础"
prerequisites: ["变量与类型"]
tags: ["python", "io"]
source: "Python 官方文档"
source_url: "https://docs.python.org/zh-cn/3/tutorial/inputoutput.html"
---

# 输入输出

## 输入
```python
name = input("请输入姓名：")
print(f"你好，{name}")
```
`input()` 返回字符串，数值计算前需要调用 `int()` 或 `float()` 转换。

## 输出格式化
推荐使用 f-string：
```python
score = 92.5
print(f"得分：{score:.1f}")
```

## 常见错误
- 直接把 `input()` 结果参与算术运算。
- 用户输入不符合格式时没有异常处理。
- 输出敏感信息或调试数据。
