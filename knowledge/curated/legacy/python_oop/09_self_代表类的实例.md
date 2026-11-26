---
title: "self 代表类的实例"
module: "面向对象"
knowledge_point: "self 代表类的实例"
difficulty: "进阶"
prerequisites: ["函数"]
tags: ["python", "legacy-curated"]
source: "Python 官方文档 / 旧版知识迁移"
source_url: "https://docs.python.org/zh-cn/3/"
---

## self 代表类的实例

类的方法与普通函数的唯一区别是必须有额外的第一个参数（通常是 self），self 代表类的实例而非类本身，约定命名为 self 但不是 Python 关键字。
```python
class Test:
    def prt(self):
        print(self)          # 当前对象的地址
        print(self.__class__)  # 指向类
```
