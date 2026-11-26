---
title: "条件语句与循环"
module: "Python 基础语法"
knowledge_point: "条件与循环"
difficulty: "基础"
prerequisites: ["变量与类型"]
tags: ["python", "control-flow"]
source: "Python 官方教程"
source_url: "https://docs.python.org/zh-cn/3/tutorial/controlflow.html"
---

# 条件语句与循环

## 条件语句
```python
score = 85
if score >= 90:
    level = "优秀"
elif score >= 60:
    level = "合格"
else:
    level = "需要复习"
```

## 循环
`for` 适合遍历可迭代对象，`while` 适合条件满足时持续执行。`break` 结束整个循环，`continue` 跳过本轮。

```python
for number in range(5):
    if number == 3:
        continue
    print(number)
```

## 常见错误
- 忘记缩进或缩进层级不一致。
- `while` 条件永远为真导致死循环。
- 在遍历列表时删除元素导致漏项。
