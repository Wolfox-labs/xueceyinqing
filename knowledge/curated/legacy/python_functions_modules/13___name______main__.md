---
title: "__name__ == '__main__'"
module: "函数与模块"
knowledge_point: "__name__ == '__main__'"
difficulty: "进阶"
prerequisites: ["函数"]
tags: ["python", "legacy-curated"]
source: "Python 官方文档 / 旧版知识迁移"
source_url: "https://docs.python.org/zh-cn/3/"
---

## __name__ == '__main__'

当.py文件被直接运行时，`if __name__ == '__main__':` 下的代码块被执行；当文件被导入时则不会执行。
