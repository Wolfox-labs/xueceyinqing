"""为一个演示账号注入一次「真实学习会话」的数据。

设计原则
--------
本脚本**不写入任何展示用数字**。它只做一件事：把模拟的学习观测（某知识点
答对/答错）提交给后端，其余全部由系统真实算法产生 ——

  · 掌握度      -> core/adaptive_engine.py 的 update_mastery（含遗忘曲线/半衰期）
  · 薄弱点/推荐 -> 真实 UCB 策略 + 知识图谱前置依赖
  · 学习时长    -> LearningTimeService 的真实累加
  · 落盘        -> AdaptiveStateStore 写入数据库

因此页面上的每个数字都是"系统算出来的"，不是"写死的"。这与往代码里塞
DEFAULT_RADAR 之类的假数据是两回事：后者无论用户做什么都显示同一组数字。

用法
----
  python scripts/accounts/seed_demo_session.py --base-url http://127.0.0.1:8001 \
      --username demo_student --password demo12345

  # 先清空该账号已有证据，再重新注入
  python scripts/accounts/seed_demo_session.py ... --reset
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone


# 模拟一个"基础尚可、进阶吃力"的学习者：每个知识点给出若干次答题观测。
# 数值是**输入**（答题对错的得分），不是展示值——掌握度由后端算。
PROFILE: dict[str, list[float]] = {
    "变量与类型": [0.9, 0.8, 1.0],
    "函数": [0.8, 0.7, 0.9],
    "列表与迭代": [0.7, 0.8, 0.6],
    "异常处理": [0.6, 0.5, 0.7],
    "面向对象": [0.6, 0.4, 0.5],
    "算法基础": [0.5, 0.3, 0.4],
    "动态规划": [0.2, 0.3, 0.1],
    "图搜索": [0.3, 0.4, 0.2],
    "工程实践": [0.4, 0.5, 0.3],
}

# 近期错误次数（用于 UCB 的 recent_errors 特征）
RECENT_ERRORS = {"动态规划": 4, "图搜索": 3, "算法基础": 2, "面向对象": 1}

# 每日学习时长（秒）——真实累加到学习时长统计。
# 总量刻意控制在百分钟级：后端对 /api/* 有 120 次/分的限流（这是刻意加的防护），
# 心跳单次上限 120 秒，发太多会被 429 拒掉。
DAILY_STUDY_SECONDS = [600, 900, 750, 1200, 500, 1050, 800]


def call(base: str, path: str, method: str = "GET", body=None, token: str | None = None,
         retries: int = 4):
    """带 429 退避重试的请求。

    后端对 /api/* 限流 120 次/分、对生成类端点 20 次/分（见 api_server/deps.py）。
    批量灌数据时必须尊重它，否则会被拒。
    """
    delay = 1.0
    for attempt in range(retries + 1):
        url = f"{base.rstrip('/')}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                return resp.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            if exc.code == 429 and attempt < retries:
                time.sleep(delay)
                delay *= 2
                continue
            try:
                return exc.code, json.loads(raw)
            except json.JSONDecodeError:
                return exc.code, raw
    return 429, {"detail": "重试后仍被限流"}


def seed_assessment(base: str, token: str, topic: str, count: int) -> dict:
    """跑一次真实的出题 -> 作答 -> 评分流程。

    这是**画像与学习报告页数据的唯一来源**（薄弱点、平均正确率、最近主题、
    学习建议都由测评结果派生）。它需要 LLM（出题与简答评分），因此：
      · 在本机完整后端上运行 -> 正常产出真实测评历史
      · 在未配置模型的环境 -> 返回 {"skipped": True}，不影响其余数据
    """
    try:
        code, paper = call(base, "/api/assess/generate", "POST",
                           {"topic": topic, "question_count": count}, token, retries=0)
    except (TimeoutError, urllib.error.URLError, OSError) as exc:
        print(f"[!] 出题请求超时/不可达（{type(exc).__name__}）——已跳过测评流程")
        print("    提示：该端点需要 LLM。在你本机启动完整后端后重跑本脚本，")
        print("          画像与学习报告页会被真实测评数据填满。")
        return {"skipped": True, "reason": type(exc).__name__}
    if code != 200 or not isinstance(paper, dict) or not paper.get("questions"):
        print(f"[!] 出题不可用（{code}）——需要 LLM，已跳过测评流程")
        print("    提示：在你本机启动完整后端后重跑本脚本，画像与学习报告页会被真实数据填满。")
        return {"skipped": True, "code": code}

    questions = paper["questions"]
    answers = []
    for q in questions:
        options = q.get("options") or []
        if options:
            # 客观题：确定性选第一项（评分仍由后端真实执行）
            answers.append({"question_id": q["id"], "answer": options[0]})
        else:
            # 简答题：给一段简短作答，由后端真实评分
            answers.append({"question_id": q["id"], "answer": "根据定义逐步推导并给出结论。"})

    code, result = call(base, "/api/assess/submit", "POST",
                        {"assessment_id": paper["assessment_id"], "answers": answers}, token)
    if code != 200 or not isinstance(result, dict):
        print(f"[x] 提交测评失败（{code}）: {result}")
        return {"skipped": True, "code": code}

    pct = result.get("percentage")
    print(f"[+] 测评完成：{result.get('total_score')}/{result.get('max_score')} "
          f"= {pct}%  主题={result.get('topic')}")
    wp = [w.get("knowledge_point") for w in (result.get("weak_points") or []) if isinstance(w, dict)]
    if wp:
        print(f"    系统判定薄弱点: {wp}")
    if result.get("suggestions"):
        print(f"    系统给出建议 {len(result['suggestions'])} 条")
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8001")
    ap.add_argument("--username", default="demo_student")
    ap.add_argument("--password", default="demo12345")
    ap.add_argument("--role", default="student")
    ap.add_argument("--days", type=int, default=12, help="把观测时间打散到最近多少天")
    ap.add_argument("--reset", action="store_true",
                    help="探测后端是否支持清空证据（当前无此接口，只如实报告，不静默假装成功）")
    ap.add_argument("--no-assessment", dest="with_assessment", action="store_false",
                    help="跳过测评流程（无 LLM 环境用）")
    ap.add_argument("--topic", default="Python 基础", help="测评主题")
    ap.add_argument("--question-count", type=int, default=8)
    args = ap.parse_args()

    base = args.base_url
    code, login = call(base, "/api/auth/login", "POST",
                       {"username": args.username, "password": args.password, "role": args.role})
    if code != 200 or not isinstance(login, dict):
        print(f"[x] 登录失败 ({code}): {login}")
        return 1
    token = login["access_token"]
    print(f"[+] 已登录 {args.username} (role={login['user']['role']})")

    if args.reset:
        # 后端目前没有"清空证据"的公开接口；这里只做探测并如实说明。
        c, _ = call(base, "/api/adaptive/evidence/reset", "POST", {}, token)
        print(f"[i] 尝试重置已有证据 -> HTTP {c}"
              + ("（该接口不存在，如需清空请直接改数据库或换新账号）" if c == 404 else ""))

    now = datetime.now(timezone.utc)
    # 把每个知识点的多次观测分散到最近 N 天，让遗忘曲线与趋势有意义
    observations = []
    # 知识点越靠后（进阶内容）安排得越早，模拟"先学基础、进阶刚碰"
    names = list(PROFILE.keys())
    for idx, name in enumerate(names):
        scores = PROFILE[name]
        for j, score in enumerate(scores):
            days_ago = args.days - idx - j * 2
            if days_ago < 0:
                days_ago = 0
            observed = now - timedelta(days=days_ago, hours=(idx * 3 + j) % 12)
            observations.append({
                "knowledge_point": name,
                "score": score,
                "observed_at": observed.isoformat(),
            })

    code, resp = call(base, "/api/adaptive/evidence", "POST",
                      {"observations": observations, "recent_errors": RECENT_ERRORS}, token)
    print(f"[{'+' if code == 200 else 'x'}] 提交 {len(observations)} 条答题证据 -> {code}")
    if code != 200:
        print(f"    响应: {resp}")
        return 1
    if isinstance(resp, dict):
        rec = resp.get("recommendation") or {}
        if rec:
            print(f"    系统算出当前推荐知识点: {rec.get('knowledge_point')} "
                  f"(目标难度 {rec.get('target_difficulty')})")

    # 学习时长：心跳接口单次上限 120 秒（schemas/activity.py 的 le=120），
    # 超上限会被 422 拒掉。所以要按天拆分多次发送。
    MAX_HEARTBEAT = 120
    total = 0
    failed = 0
    for secs in DAILY_STUDY_SECONDS:
        remaining = secs
        while remaining > 0:
            chunk = min(remaining, MAX_HEARTBEAT)
            c, _ = call(base, "/api/activity/heartbeat", "POST",
                        {"seconds": chunk, "source": "demo_session"}, token)
            if c == 200:
                total += chunk
            else:
                failed += 1
            remaining -= chunk
    print(f"[{'+' if not failed else '!'}] 累加学习时长 {total // 60} 分钟（被拒 {failed} 次）")

    # 测评流程：会走真实出题/评分（需要 LLM）。沙箱或未配置模型时优雅跳过。
    paper = {"skipped": True}
    if args.with_assessment:
        paper = seed_assessment(base, token, args.topic, args.question_count)

    # 回读，确认落盘生效
    code, dash = call(base, "/api/adaptive/dashboard", token=token)
    if code == 200 and isinstance(dash, dict):
        s = dash.get("summary", {})
        print("\n[=] 系统真实算出的结果（非脚本写入）:")
        print(f"    掌握度均值 : {s.get('mastery')}")
        print(f"    学习时长   : {s.get('study_minutes')} 分钟")
        print(f"    风险知识点 : {s.get('risk_points')}")
        print(f"    策略命中率 : {s.get('policy_hit_rate')}")
        rec = dash.get("recommendation") or {}
        print(f"    当前推荐   : {rec.get('knowledge_point')} / {rec.get('action_label')}")
        print(f"    需要引导   : {dash.get('needs_onboarding')}")
    else:
        print(f"[!] 驾驶舱回读失败 ({code}): {dash}")

    code, prof = call(base, "/api/profile", token=token)
    if code == 200 and isinstance(prof, dict):
        p = prof.get("profile") or {}
        print(f"    画像薄弱点 : {p.get('weak_points')}")
        print(f"    知识掌握度 : {p.get('knowledge_mastery')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
