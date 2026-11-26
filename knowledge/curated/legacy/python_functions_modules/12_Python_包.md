---
title: "Python 包"
module: "函数与模块"
knowledge_point: "Python 包"
difficulty: "进阶"
prerequisites: ["函数"]
tags: ["python", "legacy-curated"]
source: "Python 官方文档 / 旧版知识迁移"
source_url: "https://docs.python.org/zh-cn/3/"
---

## Python 包

包是包含 __init__.py 文件的目录，定义模块和子包的环境。
目录结构示例：
```
package_runoob/
|-- __init__.py
|-- runoob1.py
|-- runoob2.py
```
导入方式：
```python
from package_runoob.runoob1 import runoob1
```
