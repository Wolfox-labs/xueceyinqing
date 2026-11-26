"""确保演示账号存在（幂等）：demo_student / demo_teacher。

为什么需要它
------------
真实库 runtime/app.db 里的账号是历次调试留下的，口令无人记得。
演示前如果没有可用登录，整套系统就打不开第一屏。

本脚本只做"缺了就建"，已存在则原样跳过，**不会改任何已有账号的口令**。
必须在**你自己双击一键脚本**启动的那个环境里运行（同一台机器、同一个用户），
因为它要写 runtime/app.db。

口令不写死在代码里：优先取 --password，其次取环境变量
DEMO_ACCOUNT_PASSWORD，两者都没有就报错退出。

⚠ 这里刻意区分两种失败，绝不混为一谈：
    · ValueError（该用户名已被注册）-> 账号已存在，属于正常情况，跳过；
    · 其他任何异常（典型是 sqlite3.OperationalError：数据库不可写）
      -> **明确报错并要求人工处理**。
    曾经把"写不进去"也当成"已存在"打印"跳过"，那是在撒谎：用户会以为账号
    已经建好，实际根本没有这个账号，登录必然失败。

用法
----
    .venv\\Scripts\\python.exe scripts\\accounts\\ensure_demo_account.py --password 你的口令
    .venv\\Scripts\\python.exe scripts\\accounts\\ensure_demo_account.py   # 读 DEMO_ACCOUNT_PASSWORD
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.auth_service import AuthService  # noqa: E402

ACCOUNTS = (("demo_student", "student"), ("demo_teacher", "teacher"))


def _resolve_password(cli_value: str | None) -> str:
    password = (cli_value or os.getenv("DEMO_ACCOUNT_PASSWORD", "")).strip()
    if not password:
        raise SystemExit(
            "缺少口令：请用 --password 传入，或设置环境变量 DEMO_ACCOUNT_PASSWORD。"
        )
    if len(password) < 6:
        raise SystemExit("口令太短：至少 6 位。")
    return password


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--password", default=None, help="演示账号口令（或用 DEMO_ACCOUNT_PASSWORD）")
    args = ap.parse_args()

    password = _resolve_password(args.password)

    service = AuthService()
    created, existed, failed = [], [], []

    for username, role in ACCOUNTS:
        try:
            service.create_user(username, password, role)
            created.append(f"{username}({role})")
        except ValueError:
            # 用户名已注册：这是 create_user 明确表达的"已存在"。
            existed.append(f"{username}({role})")
        except Exception as exc:  # noqa: BLE001 - 必须如实暴露，不能伪装成"已存在"
            failed.append(f"{username}({role}) -> {type(exc).__name__}: {exc}")

    if created:
        print(f"[+] 已创建演示账号：{', '.join(created)}")
    if existed:
        print(f"[i] 已存在，跳过：{', '.join(existed)}")

    if failed:
        print(f"[x] 创建失败：{'; '.join(failed)}")
        print("    常见原因：runtime/app.db 不可写（权限/被其它进程独占）。")
        print("    请修复后重跑本脚本；在账号真正建好之前，不要用 demo_student 登录。")
        return 1

    print(f"[=] 可用登录：{' / '.join(u for u, _ in ACCOUNTS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
