---
title: "Python 内置类属性"
module: "面向对象"
knowledge_point: "Python 内置类属性"
difficulty: "进阶"
prerequisites: ["函数"]
tags: ["python", "legacy-curated"]
source: "Python 官方文档 / 旧版知识迁移"
source_url: "https://docs.python.org/zh-cn/3/"
---

## Python 内置类属性

- `__dict__`：类的属性字典，包含类的数据属性
- `__doc__`：类的文档字符串，通过 ClassName.__doc__ 访问
- `__name__`：类名
- `__module__`：类定义所在的模块名（类的全名是 '__main__.className'）
- `__bases__`：所有父类组成的元组
