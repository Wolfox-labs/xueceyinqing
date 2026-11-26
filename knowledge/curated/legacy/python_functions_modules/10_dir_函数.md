---
title: "dir() 函数"
module: "函数与模块"
knowledge_point: "dir() 函数"
difficulty: "进阶"
prerequisites: ["函数"]
tags: ["python", "legacy-curated"]
source: "Python 官方文档 / 旧版知识迁移"
source_url: "https://docs.python.org/zh-cn/3/"
---

## dir() 函数

返回模块里定义的所有模块、变量和函数的排序列表：
```python
import math
content = dir(math)  # 返回 math 模块所有名称
```
