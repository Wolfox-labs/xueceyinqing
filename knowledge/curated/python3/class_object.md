---
title: "类与对象"
module: "面向对象"
knowledge_point: "面向对象"
difficulty: "进阶"
prerequisites: ["函数", "变量与类型"]
tags: ["python", "oop"]
source: "Python 官方文档"
source_url: "https://docs.python.org/zh-cn/3/tutorial/classes.html"
---

# 类与对象

## 定义类
```python
class Student:
    def __init__(self, name, score):
        self.name = name
        self.score = score

    def passed(self):
        return self.score >= 60
```

## 封装、继承和多态
- 封装：把数据和操作数据的方法放在一起。
- 继承：复用父类行为，表达 is-a 关系。
- 多态：不同对象对同一接口给出不同实现。

## 常见错误
- 过度继承，使用继承表达 has-a 关系。
- 忘记 `self`。
- 把可变对象直接作为类属性共享。
