"""业务路由模块。

拆分原则：按域内聚，每个模块自带 APIRouter，由 api_server/main.py 统一 include。
模块只从 api_server/deps.py 取共享依赖，**不反向导入 main**（否则循环依赖）。
"""
from api_server.routers import (
    auth,
    files,
    materials,
    question_bank,
    reports,
    teacher,
)

# 挂载顺序无关紧要（路径无重叠），但保持稳定便于阅读与 diff。
ROUTERS = (
    auth.router,
    materials.router,
    teacher.router,
    files.router,
    question_bank.router,
    reports.router,
)

__all__ = ["ROUTERS"]
