---
title: "globals() 和 locals()"
module: "函数与模块"
knowledge_point: "globals() 和 locals()"
difficulty: "进阶"
prerequisites: ["函数"]
tags: ["python", "legacy-curated"]
source: "Python 官方文档 / 旧版知识迁移"
source_url: "https://docs.python.org/zh-cn/3/"
---

## globals() 和 locals()

- locals()：返回局部命名空间字典
- globals()：返回全局命名空间字典

重新执行已导入模块的顶层代码：
```python
reload(module_name)
```
