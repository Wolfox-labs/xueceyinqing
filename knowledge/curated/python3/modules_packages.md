---
title: "模块与包"
module: "函数与模块"
knowledge_point: "模块与包"
difficulty: "进阶"
prerequisites: ["函数"]
tags: ["python", "module", "package"]
source: "Python 官方文档"
source_url: "https://docs.python.org/zh-cn/3/tutorial/modules.html"
---

# 模块与包

## 模块
一个 `.py` 文件可以作为一个模块被导入：
```python
# math_utils.py
def add(a, b):
    return a + b
```

```python
from math_utils import add
```

## 包
包是包含 `__init__.py` 的目录，用于组织多个模块。项目内部导入应保持清晰，避免循环导入。

## `__name__`
```python
if __name__ == "__main__":
    main()
```
它保证模块被导入时不会自动执行命令行逻辑。

## 常见错误
- 模块名与标准库模块重名。
- 使用相对路径导入时依赖当前工作目录。
- 在 `__init__.py` 中执行过重的初始化。
