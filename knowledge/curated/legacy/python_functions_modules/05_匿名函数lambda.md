---
title: "匿名函数（lambda）"
module: "函数与模块"
knowledge_point: "匿名函数（lambda）"
difficulty: "进阶"
prerequisites: ["函数"]
tags: ["python", "legacy-curated"]
source: "Python 官方文档 / 旧版知识迁移"
source_url: "https://docs.python.org/zh-cn/3/"
---

## 匿名函数（lambda）

```python
lambda [arg1 [,arg2,...]]: expression
sum = lambda arg1, arg2: arg1 + arg2
sum(10, 20)  # 30
```
lambda 是表达式而非代码块，只能封装有限逻辑。
