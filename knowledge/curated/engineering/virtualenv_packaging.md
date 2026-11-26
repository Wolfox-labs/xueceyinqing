---
title: "虚拟环境与依赖管理"
module: "工程实践"
knowledge_point: "工程实践"
difficulty: "进阶"
prerequisites: ["模块与包"]
tags: ["engineering", "venv", "packaging"]
source: "Python 官方文档"
source_url: "https://docs.python.org/zh-cn/3/tutorial/venv.html"
---

# 虚拟环境与依赖管理

## 虚拟环境
虚拟环境为每个项目隔离 Python 解释器和第三方包：
```bash
python -m venv .venv
.venv\Scripts\activate
```

## 依赖声明
项目应明确声明直接依赖，避免依赖“碰巧存在于某台机器”。可以使用 `requirements.txt`、`pyproject.toml` 或 `uv.lock`。

## 常见问题
- 把 `.venv` 提交到 Git。
- 在全局环境安装项目依赖。
- 只记录间接依赖，不记录直接依赖。
