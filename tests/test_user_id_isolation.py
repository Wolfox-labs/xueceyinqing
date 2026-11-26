"""守住"跨用户串数据"这条线。

真实故障
--------
前端曾把 'default' 硬编码进 8 个 API 模块当 user_id 发出去，而后端
_uid() 的兜底恰好也是 "default"，而 kv_store 里**真的存在**
profile_dashboard_state_default / assessment_default_* 这些键。

后果：换个账号登录，档案页显示的仍是同一份（别人的）薄弱知识点，
而且因为那份数据来自一次失败测评（total_score=0），页面上全是 0%。

对比赛演示来说这是致命的——评委只要切换账号就会发现数据不跟着人走。
"""
import unittest
from unittest import mock

from api_server import deps


class UserIdResolutionTest(unittest.TestCase):
    def test_authenticated_user_wins(self):
        token = deps._current_user.set("real-user-uuid")
        try:
            # 即使客户端伪造了别人的 user_id，也必须以认证用户为准。
            self.assertEqual(deps._uid("someone-else"), "real-user-uuid")
            self.assertEqual(deps._uid("default"), "real-user-uuid")
            self.assertEqual(deps._uid(None), "real-user-uuid")
        finally:
            deps._current_user.reset(token)

    def test_default_is_not_treated_as_a_real_user(self):
        """没带认证上下文时，显式传来的 'default' 不该被当成用户 ID。

        它对应 kv_store 里的共享数据；继续使用它就会把别人的画像读出来。
        """
        token = deps._current_user.set(None)
        try:
            self.assertEqual(deps._uid("default"), "default")  # 仅本地/CLI 兜底
            self.assertEqual(deps._uid("  "), "default")
            # 真正显式指定的用户仍然被尊重（内部调用路径）
            self.assertEqual(deps._uid("internal-user"), "internal-user")
        finally:
            deps._current_user.reset(token)

    def test_frontend_does_not_hardcode_default(self):
        """前端 API 模块里不能再把 'default' 当**默认参数值**。

        注意只抓"= 'default'"作为参数默认值这种形态，例如
        `userId = 'default'`；而 `userId !== 'default'`（防御性判断）是允许的，
        它正是在拦这个值。
        """
        import re
        from pathlib import Path

        api_dir = Path(__file__).resolve().parent.parent / "frontend" / "src" / "api"
        # 形如 `userId = 'default'` 或 `userId: string = "default"` 的参数默认值
        pattern = re.compile(r"=\s*['\"]default['\"]\s*[,)]")
        offenders = []
        for path in api_dir.glob("*.ts"):
            if path.name == "client.ts":  # client.ts 内部需要识别并过滤这个值
                continue
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("//") or stripped.startswith("*"):
                    continue
                for match in pattern.finditer(line):
                    # 排除比较运算：`!== 'default'` / `=== 'default'`
                    prefix = line[: match.start()].rstrip()
                    if prefix.endswith("!") or prefix.endswith("="):
                        continue
                    offenders.append("%s:%d %s" % (path.name, lineno, stripped))
                    break
        self.assertEqual(
            offenders,
            [],
            "以下位置把 'default' 当参数默认值，会读到 kv_store 里的共享数据：\n"
            + "\n".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()