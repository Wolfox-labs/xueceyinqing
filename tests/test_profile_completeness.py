"""守住"画像完整度不能凭空起步"。

真实故障
--------
旧实现：completeness = min(100, 42 + 证据源种类数 * 12)。
凭空给了 42% 的底数，于是**刚注册、什么都没做的新账号也显示 54%**。
这是编出来的数字：用户看到 54% 会以为系统已经了解了自己一半，
实际上一条画像数据都没有。

现在改为"六个画像维度里究竟有几个真的填上了"，全空 = 0%。
"""
import unittest
from unittest import mock

from core.profile_service import ProfileService
from schemas.profile import StudentProfile


class CompletenessTest(unittest.TestCase):
    def _service(self, *, signals, history, mastery_profile, sessions, profile_text):
        """构造一个只替换存储读取、其余走真实逻辑的 ProfileService。"""
        service = ProfileService.__new__(ProfileService)
        service.user_id = "u1"
        service.store = mock.Mock()
        service.store.get_profile.return_value = profile_text
        service.store.list_sessions.return_value = sessions
        service.path_store = mock.Mock()
        service.assessment_store = mock.Mock()
        service.assessment_store.get_history.return_value = history
        service._load_state = lambda: {"signals": signals, "update_log": []}
        return service

    def test_empty_profile_is_zero_percent(self):
        svc = self._service(signals=[], history=[], mastery_profile={}, sessions=[], profile_text="")
        with mock.patch.object(StudentProfile, "from_text", return_value=StudentProfile()):
            dash = svc.build_dashboard()
        self.assertEqual(
            dash.summary["profile_completeness"],
            0,
            "全空的画像必须是 0%，不能像旧实现那样凭空显示 42%+ 的底数",
        )

    def test_one_dimension_is_one_sixth(self):
        svc = self._service(
            signals=[{"source": "resource", "kind": "preference", "value": "思维导图"}],
            history=[], mastery_profile={}, sessions=[], profile_text="",
        )
        with mock.patch.object(StudentProfile, "from_text", return_value=StudentProfile()):
            dash = svc.build_dashboard()
        # 只有"学习行为信号"这一维有数据 -> 1/6 ≈ 17%
        self.assertEqual(dash.summary["profile_completeness"], 17)

    def test_all_dimensions_is_full(self):
        profile = StudentProfile(subjects=["计算机网络"])
        svc = self._service(
            signals=[{"source": "resource", "kind": "preference", "value": "思维导图"}],
            history=[{"weak_points": [{"knowledge_point": "TCP", "score": 0.0}]}],
            mastery_profile={}, sessions=[{"id": "s1"}], profile_text="学习阶段：入门",
        )
        with mock.patch.object(StudentProfile, "from_text", return_value=profile):
            dash = svc.build_dashboard()
        self.assertEqual(dash.summary["profile_completeness"], 100)

    def test_display_name_is_not_the_hex_user_id(self):
        """展示名不能回退成 uuid4 十六进制（那不是给人看的名字）。"""
        svc = self._service(signals=[], history=[], mastery_profile={}, sessions=[], profile_text="")
        with mock.patch.object(StudentProfile, "from_text", return_value=StudentProfile()):
            dash = svc.build_dashboard()
        self.assertNotEqual(dash.identity["display_name"], "u1")
        self.assertEqual(dash.identity["display_name"], "")


class DashboardRouteIdentityTest(unittest.TestCase):
    """路由层写入 display_name 的方式必须与 schema 一致。

    真实故障：identity 在 schemas/profile_dashboard.py 里声明为 `dict`，
    而我在路由里写成了 `dashboard.identity.display_name = username`（属性赋值），
    于是每次请求都抛 AttributeError -> 档案页直接显示"无法加载学习者数字画像"。
    测试必须覆盖"路由真的被调用"这条路径，只测 service 是抓不到的。
    """

    def _fake_request(self, username: str):
        class _User:
            pass

        class _State:
            pass

        user = _User()
        user.username = username
        request = _State()
        request.state = _State()
        request.state.user = user
        return request

    def test_route_sets_display_name_on_dict_identity(self):
        import asyncio

        from api_server import main as api_main

        dashboard = api_main.ProfileDashboardResponse(
            user_id="u1",
            identity={"display_name": "", "learning_stage": "未知", "subjects": [], "last_active": ""},
            summary={},
            cards=[],
            knowledge={"labels": [], "values": []},
            activities=[],
            update_log=[],
        )

        with mock.patch.object(api_main, "ProfileService") as service_cls:
            service_cls.return_value.build_dashboard.return_value = dashboard
            result = asyncio.run(
                api_main.get_profile_dashboard(self._fake_request("demo_student"), user_id="u1")
            )

        self.assertEqual(result.identity["display_name"], "demo_student")

    def test_route_survives_missing_auth_user(self):
        """未认证/无 user 上下文时不能抛异常，仍要返回画像。"""
        import asyncio

        from api_server import main as api_main

        dashboard = api_main.ProfileDashboardResponse(
            user_id="u1",
            identity={"display_name": "", "learning_stage": "未知", "subjects": [], "last_active": ""},
            summary={},
            cards=[],
            knowledge={"labels": [], "values": []},
            activities=[],
            update_log=[],
        )

        class _EmptyState:
            pass

        class _Req:
            pass

        req = _Req()
        req.state = _EmptyState()  # 没有 user 属性

        with mock.patch.object(api_main, "ProfileService") as service_cls:
            service_cls.return_value.build_dashboard.return_value = dashboard
            result = asyncio.run(api_main.get_profile_dashboard(req, user_id="u1"))

        self.assertEqual(result.identity["display_name"], "")


if __name__ == "__main__":
    unittest.main()