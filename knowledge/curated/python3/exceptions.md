---
title: "异常处理"
module: "文件与异常"
knowledge_point: "异常处理"
difficulty: "进阶"
prerequisites: ["函数"]
tags: ["python", "exception"]
source: "Python 官方文档"
source_url: "https://docs.python.org/zh-cn/3/tutorial/errors.html"
---

# 异常处理

## 基本语法
```python
try:
    value = int("123")
except ValueError as exc:
    print(f"输入不是整数：{exc}")
else:
    print("转换成功")
finally:
    print("流程结束")
```

## 使用原则
- 只捕获能够处理的异常。
- 不要使用裸 `except:`。
- 记录异常上下文，避免静默失败。
- 自定义异常应表达业务语义，而不是简单复制 `Exception`。

## 常见错误
- 用异常控制正常流程。
- 捕获后不处理也不记录。
- `except` 顺序错误，宽泛异常挡住了具体异常。
