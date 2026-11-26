"""让 crewai 在"配置目录实际不可写"的环境里立刻回退，而不是空转几十分钟。

问题（Windows 特有）
-------------------
``crewai_core.settings.get_writable_config_path()`` 依次探测三个候选位置：

1. ``~/.config/crewai/settings.json``
2. 系统临时目录 ``…/crewai_settings.json``
3. 当前目录 ``./crewai_settings.json``

每个候选都用 ``tempfile.mkstemp(dir=那个目录)`` 做"能不能写"的探测。而 CPython
的 ``tempfile._mkstemp_inner`` 在 Windows 上撞到 ``PermissionError`` 时会用
``os.access(dir, os.W_OK)`` 复核——注释里写的理由是"这个名字可能是个已存在的
目录"。如果这次复核**错误地**报告"可写"，它就会 ``continue``，最多重试
``TMP_MAX = 238328`` 次。

实测（本机）：``os.access`` 说可写、``os.open`` 却被拒时，每次失败约 7ms，
一次 ``mkstemp`` 就要 **约 28 分钟**。后端启动时的表现因此是：
uvicorn 卡在 lifespan 不动、端口一直不 bind、一键脚本等 90 秒也等不到 8001。

修法
----
把 ``os.access(path, W_OK)`` 对**目录**的判断换成真刀真枪的写入探测
（建一个探测文件再删掉），让它和 ``os.open`` 给出一致的结论：

* 真能写 → 返回 True（探测文件已清理）；
* 真不能写 → 返回 False，``tempfile`` 随即按设计抛错，crewai 立刻走下一个
  候选路径，不再空转。

对目录以外的路径、以及非 W_OK 的查询一律原样交给 ``os.access``，所以
``shutil.which`` 之类的用法不受影响。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

#: 探测文件名：固定名字，避免每次都在 denied 目录里做随机名生成。
_PROBE_NAME = ".xuece_write_probe.tmp"

_installed = False


def _probe_writable(directory: str | bytes) -> bool:
    """真的试着建一个文件再删掉；异常一律视为不可写。"""
    probe = os.path.join(directory, _PROBE_NAME)
    try:
        fd = os.open(probe, os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o600)
    except FileExistsError:
        # 同名探测文件已存在：说明这个目录确实是可写的（上次可能被中断没删掉）。
        return True
    except OSError:
        return False
    try:
        os.close(fd)
    except OSError:
        pass
    try:
        os.unlink(probe)
    except OSError:
        pass
    return True


def install() -> bool:
    """安装写入探测（幂等、仅 Windows 生效）。返回本次是否真的装了。"""
    global _installed
    if _installed or os.name != "nt":
        return False

    # CrewAI 的默认 AppData 目录在部分 Windows 账号下能读、不能创建
    # SQLite 的 WAL 文件。使用项目专属的绝对路径，避免生成任务时才报 500。
    # 保留显式指定的存储目录，且不迁移或覆盖任何已有业务数据库。
    storage_dir = Path(__file__).resolve().parents[1] / "runtime" / "crewai"
    if not os.environ.get("CREWAI_STORAGE_DIR"):
        storage_dir.mkdir(parents=True, exist_ok=True)
        os.environ["CREWAI_STORAGE_DIR"] = str(storage_dir)

    real_access = os.access

    def access(path, mode, *args, **kwargs):
        if mode & os.W_OK and isinstance(path, (str, bytes, os.PathLike)):
            try:
                is_dir = os.path.isdir(path)
            except (OSError, ValueError):
                is_dir = False
            if is_dir:
                return _probe_writable(os.fspath(path))
        return real_access(path, mode, *args, **kwargs)

    os.access = access  # type: ignore[assignment]
    _installed = True
    return True


def installed() -> bool:
    """供自检/测试使用。"""
    return _installed
