"""基于 SQLite 的账号认证与限流服务。

- 用户注册后持久化到 runtime/app.db
- 密码使用 PBKDF2-SHA256 加盐保存，不保存明文
- 登录令牌落库并在过期后自动失效
- Token 仍然通过 Authorization: Bearer 传递
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import secrets
import sqlite3
import threading
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DB_PATH = _PROJECT_ROOT / "runtime" / "app.db"
_USERNAME_RE = re.compile(r"^[\w\u4e00-\u9fff.\-]{3,32}$", re.UNICODE)
_VALID_ROLES = {"student", "teacher"}

# 自助注册只允许创建学生账号。教师是特权角色（可读取全校学生名单、改动实验
# 配置），绝不能让访客自选——否则注册接口就是一条提权链。
SELF_REGISTER_ROLE = "student"


@dataclass(frozen=True, slots=True)
class AuthUser:
    user_id: str
    username: str
    role: str


class AuthService:
    """账号注册、登录和令牌校验服务。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._db_path = Path(os.getenv("AUTH_DB_PATH", str(_DEFAULT_DB_PATH))).resolve()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ttl = timedelta(seconds=max(300, int(os.getenv("AUTH_TOKEN_TTL_SECONDS", "86400"))))
        self._init_db()
        self._seed_optional_demo_accounts()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS auth_tokens (
                    token TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_auth_tokens_user
                    ON auth_tokens(user_id);
                CREATE INDEX IF NOT EXISTS idx_auth_tokens_expiry
                    ON auth_tokens(expires_at);
                """
            )

    @staticmethod
    def _hash_password(password: str) -> str:
        salt = os.urandom(16)
        iterations = 210_000
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"

    @staticmethod
    def _verify_password(password: str, encoded: str) -> bool:
        try:
            algorithm, iterations, salt_hex, digest_hex = encoded.split("$", 3)
            if algorithm != "pbkdf2_sha256":
                return False
            expected = bytes.fromhex(digest_hex)
            actual = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                bytes.fromhex(salt_hex),
                int(iterations),
            )
            return hmac.compare_digest(actual, expected)
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _normalize_username(username: str) -> str:
        return (username or "").strip().lower()

    def _validate_registration(self, username: str, password: str, role: str) -> tuple[str, str]:
        normalized = self._normalize_username(username)
        role_name = (role or "").strip().lower()
        if not _USERNAME_RE.fullmatch(normalized):
            raise ValueError("用户名需为 3-32 个字符，可使用中文、字母、数字、下划线、点和短横线")
        if len(password or "") < 6:
            raise ValueError("密码至少需要 6 位")
        if len(password) > 128:
            raise ValueError("密码不能超过 128 位")
        if role_name not in _VALID_ROLES:
            raise ValueError("账号角色无效")
        return normalized, role_name

    def _issue_token(self, user: AuthUser) -> tuple[str, AuthUser, datetime]:
        token = secrets.token_urlsafe(32)
        expires_at = self._now() + self._ttl
        now = self._now().isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO auth_tokens(token, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
                (token, user.user_id, expires_at.isoformat(), now),
            )
            conn.execute("DELETE FROM auth_tokens WHERE expires_at <= ?", (self._now().isoformat(),))
        return token, user, expires_at

    def register(
        self, username: str, password: str, role: str | None = None
    ) -> tuple[str, AuthUser, datetime]:
        """自助注册：角色一律为学生，传入的 role 被忽略。

        旧实现把客户端传来的 role 直接落库，于是任何访客都能注册成 teacher，
        进而访问 /api/teacher/overview（列出全部学生）并修改全局实验配置。
        """
        if (role or "").strip().lower() == "teacher":
            logger.warning(
                "注册请求试图自选教师角色，已强制降级为学生 username=%s",
                (username or "").strip(),
            )
        return self.create_user(username, password, SELF_REGISTER_ROLE)

    def create_user(
        self, username: str, password: str, role: str
    ) -> tuple[str, AuthUser, datetime]:
        """创建指定角色的账号。仅供内部/运维路径使用（如环境变量种子账号）。"""
        normalized, role_name = self._validate_registration(username, password, role)
        user = AuthUser(user_id=uuid.uuid4().hex, username=normalized, role=role_name)
        with self._lock, self._connect() as conn:
            try:
                conn.execute(
                    "INSERT INTO users(user_id, username, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?)",
                    (
                        user.user_id,
                        user.username,
                        self._hash_password(password),
                        user.role,
                        self._now().isoformat(),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("该用户名已被注册") from exc
        return self._issue_token(user)

    def login(self, username: str, password: str, role: str | None = None) -> tuple[str, AuthUser, datetime] | None:
        name = self._normalize_username(username)
        role_name = (role or "").strip().lower()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT user_id, username, password_hash, role FROM users WHERE username = ?",
                (name,),
            ).fetchone()
        if row is None:
            return None
        if role_name and role_name != row["role"]:
            return None
        if not self._verify_password(password or "", row["password_hash"]):
            return None
        return self._issue_token(
            AuthUser(user_id=row["user_id"], username=row["username"], role=row["role"])
        )

    def change_password(self, user_id: str, current_password: str, new_password: str) -> None:
        if len(new_password or "") < 6:
            raise ValueError("新密码至少需要 6 位")
        if len(new_password) > 128:
            raise ValueError("新密码不能超过 128 位")
        if new_password == current_password:
            raise ValueError("新密码不能与当前密码相同")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT password_hash FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
        if row is None or not self._verify_password(current_password, row["password_hash"]):
            raise ValueError("当前密码不正确")
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE user_id = ?",
                (self._hash_password(new_password), user_id),
            )
            conn.execute("DELETE FROM auth_tokens WHERE user_id = ?", (user_id,))
    def authenticate(self, token: str | None) -> AuthUser | None:
        if not token:
            return None
        now = self._now().isoformat()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT u.user_id, u.username, u.role, t.expires_at
                FROM auth_tokens t
                JOIN users u ON u.user_id = t.user_id
                WHERE t.token = ?
                """,
                (token,),
            ).fetchone()
            if row is None:
                return None
            if row["expires_at"] <= now:
                conn.execute("DELETE FROM auth_tokens WHERE token = ?", (token,))
                return None
        return AuthUser(user_id=row["user_id"], username=row["username"], role=row["role"])

    def logout(self, token: str | None) -> None:
        if not token:
            return
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM auth_tokens WHERE token = ?", (token,))

    def list_users(self, role: str = "student") -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT user_id, username, role, created_at FROM users WHERE role = ? ORDER BY created_at DESC",
                (role,),
            ).fetchall()
        return [dict(row) for row in rows]
    def _seed_optional_demo_accounts(self) -> None:
        """仅在显式开启时创建兼容账号，默认完全关闭。

        密码必须由环境变量提供：旧实现在这里内置了一个写死的默认口令，
        一个开关就能创建出密码公开的教师账号。
        """
        if os.getenv("AUTH_SEED_DEMO_ACCOUNTS", "false").strip().lower() not in {"1", "true", "yes"}:
            return
        seeds = [
            (username, password, role)
            for username, password, role in (
                ("student", os.getenv("DEMO_STUDENT_PASSWORD", "").strip(), "student"),
                ("teacher", os.getenv("DEMO_TEACHER_PASSWORD", "").strip(), "teacher"),
            )
            if password
        ]
        if not seeds:
            logger.warning(
                "已开启 AUTH_SEED_DEMO_ACCOUNTS 但未提供 DEMO_STUDENT_PASSWORD / "
                "DEMO_TEACHER_PASSWORD，跳过种子账号创建"
            )
            return
        for username, password, role in seeds:
            with self._connect() as conn:
                exists = conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
            if exists is None:
                try:
                    self.create_user(username, password, role)
                except ValueError:
                    logger.warning("种子账号创建失败 username=%s", username, exc_info=True)


class SlidingWindowRateLimiter:
    """按用户/来源做简单的滑动窗口限流。"""

    # 每处理这么多次调用就清理一次陈旧键：旧实现里每个登录过的用户都会永久
    # 占用一个字典项，_events 无界增长。
    _PRUNE_EVERY = 512

    def __init__(self, limit: int = 30, window_seconds: int = 60) -> None:
        self.limit = max(1, limit)
        self.window_seconds = max(1, window_seconds)
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._calls = 0

    def allow(self, key: str) -> bool:
        now = datetime.now(timezone.utc).timestamp()
        with self._lock:
            self._calls += 1
            if self._calls % self._PRUNE_EVERY == 0:
                self._prune_locked(now)
            events = self._events[key]
            while events and now - events[0] >= self.window_seconds:
                events.popleft()
            if len(events) >= self.limit:
                return False
            events.append(now)
            return True

    def prune(self) -> int:
        """清理窗口内已无事件的键，返回清理数量。"""
        now = datetime.now(timezone.utc).timestamp()
        with self._lock:
            return self._prune_locked(now)

    def tracked_keys(self) -> int:
        """当前占用的键数量（供测试与观测使用）。"""
        with self._lock:
            return len(self._events)

    def _prune_locked(self, now: float) -> int:
        removed = 0
        for key in list(self._events.keys()):
            events = self._events[key]
            while events and now - events[0] >= self.window_seconds:
                events.popleft()
            if not events:
                del self._events[key]
                removed += 1
        return removed