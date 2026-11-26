#!/usr/bin/env python
"""
mlqk — 个性化资源生成与学习多智能体系统 CLI

用法:
  uv run python main.py [--user <用户名>]

命令:
  /ask <问题>       向AI教师提问
  /gen <类型> <主题> 生成学习资源 (document / mindmap / exercise / ppt)
  /path [主题]      查看/生成学习路径
  /profile          查看用户画像
  /exit             退出

架构:
  main.py         — 命令路由 + 终端 I/O（本文件，约 350 行）
  core/runner.py  — Crew 执行器（流式 + 结果收集）
  core/memory.py  — 对话记忆（压缩 + 上下文 + 存取）
  core/session.py — 会话生命周期（session_id + turn）
  agents/         — Agent 定义
  crews/          — Task + Crew 编排
  tools/          — Tool 实现
  db/             — 存储后端
"""
import argparse
import json
import os
import sys
import io

# ── Windows 控制台 UTF-8 编码兼容 ──────────────────────
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
os.environ["PYTHONIOENCODING"] = "utf-8"

from agents import create_agents
from core import CrewRunner, CrewPipeline, MemoryManager, SessionManager
from core.parsing import _extract_json, parse_resource
from core.assessment_flow import parse_answers, generate_assessment_report
from crews.ask import build_ask_crew
from crews.generate import build_gen_crew
from crews.path import build_path_crew
from crews.classroom import build_classroom_crew
from crews.assessment import build_assessment_crew
from schemas import ExerciseOutput, LearningPath, ClassroomScript
from tools.registry import get_tools
from db.vector_store import get_store, init_knowledge_base
from utils.tokens import format_metrics


# ── CLI 辅助函数 ───────────────────────────────────────

def _banner():
    print()
    print("=" * 56)
    print("  mlqk  个性化资源生成与学习多智能体系统")
    print("=" * 56)
    print("  /ask <问题>       向AI教师提问")
    print("  /gen <类型> <主题> 生成学习资源")
    print("     类型: document  mindmap  exercise  ppt")
    print("  /assess <主题>    生成评估题库并评分")
    print("  /path [主题]      查看/生成学习路径")
    print("  /classroom <主题>  生成虚拟课堂")
    print("  /profile          查看用户画像")
    print("  /exit             退出")
    print("=" * 56)


def _resolve_args():
    """解析 --user 参数（兼容 CrewAI 自身参数）。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", default="default", help="用户名，用于区分不同用户")
    args, _ = parser.parse_known_args()
    return args


# ── 主入口 ─────────────────────────────────────────────

def main():
    args = _resolve_args()
    user_id = args.user

    print("初始化知识库...")
    init_knowledge_base()

    print(f"加载 Agent...（用户: {user_id}）")
    profile_agent, teacher, reviewer = create_agents(user_id)

    # 业务层实例
    runner = CrewRunner()
    session = SessionManager()
    memory = MemoryManager(user_id)
    pipeline = CrewPipeline(reviewer, memory)
    store = get_store()
    session.create()

    _banner()

    while True:
        try:
            raw = input("\nmlqk> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not raw:
            continue

        if raw == "/exit":
            print("再见！")
            break

        if raw == "/profile":
            from schemas import StudentProfile
            text = store.get_profile(user_id)
            p = StudentProfile.from_text(text)
            print(f"\n  学习阶段：{p.learning_stage}")
            print(f"  关注学科：{'、'.join(p.subjects) if p.subjects else '暂无'}")
            print(f"  薄弱环节：{'、'.join(p.weak_points) if p.weak_points else '暂无'}")
            print(f"  学习偏好：{p.learning_style}")
            print(f"  语言风格：{p.language_style}")
            if p.knowledge_mastery:
                print(f"  知识掌握度：{json.dumps(p.knowledge_mastery, ensure_ascii=False)}")
            continue

        # ── /ask ──
        if raw.startswith("/ask"):
            question = raw[5:].strip()
            if not question:
                print("用法: /ask <问题>")
                continue

            session.next_turn()
            ctx = memory.get_context(session.session_id, session.turn)

            print("\n  思考中...", end="", flush=True)
            tools = get_tools(user_id)
            crew = build_ask_crew(profile_agent, teacher, question, ctx, tools=tools)
            result = pipeline.execute(crew,
                session_id=session.session_id, turn=session.turn,
                question=question, runner=runner,
                on_chunk=lambda c: print(c, end="", flush=True))
            print(f"\n\n{format_metrics(result.metrics)}")

            if result.withdrawn:
                print(f"\n  ⚠️ 内容已被审核撤回：{result.reason}")
            continue

        # ── /gen ──
        if raw.startswith("/gen"):
            parts = raw[4:].strip().split(maxsplit=1)
            if len(parts) < 2:
                print("用法: /gen <类型> <主题>")
                print("类型: document / mindmap / exercise / ppt")
                continue
            rtype = parts[0].lower()
            topic = parts[1]
            if rtype not in ("document", "mindmap", "exercise", "ppt"):
                print(f"未知类型: {rtype}，支持: document mindmap exercise ppt")
                continue

            session.next_turn()
            ctx = memory.get_context(session.session_id, session.turn)

            print(f"\n  生成 {rtype}: {topic} ...")

            tools = get_tools(user_id, resource_type=rtype)
            crew = build_gen_crew(teacher, reviewer, rtype, topic, ctx, tools=tools)

            # mindmap：不流式显示 JSON，静默收集后转换
            if rtype == "mindmap":
                result = pipeline.execute(crew,
                    session_id=session.session_id, turn=session.turn,
                    question=f"/gen {rtype} {topic}", runner=runner)
            else:
                result = pipeline.execute(crew,
                    session_id=session.session_id, turn=session.turn,
                    question=f"/gen {rtype} {topic}", runner=runner,
                    on_chunk=lambda c: print(c, end="", flush=True))

            if result.withdrawn:
                print(f"\n  ⚠️ 内容已被审核撤回：{result.reason}")
            else:
                output = parse_resource(rtype, result.raw)
                print(f"\n{output}")

            print(f"\n{format_metrics(result.metrics)}")
            continue

        # ── /assess ──
        if raw.startswith("/assess"):
            topic = raw[8:].strip()
            if not topic:
                print("用法: /assess <主题>")
                continue

            profile_text = store.get_profile(user_id)
            tools = get_tools(user_id, resource_type="assessment")

            print(f"\n  生成检测题库: {topic} ...")
            crew = build_assessment_crew(teacher, user_id, topic, profile_text, tools=tools)
            result = runner.run(crew)

            data = _extract_json(result.raw)
            if not data:
                print(f"\n  未能生成有效题库\n  原始输出:\n{result.raw[:500]}")
                continue

            try:
                ex = ExerciseOutput.model_validate(data)
            except Exception as e:
                print(f"\n  解析题库失败: {e}\n  原始输出:\n{result.raw[:500]}")
                continue

            print(f"\n  {ex.title}")
            print(f"  共 {len(ex.items)} 道题")

            user_inputs = []
            for i, item in enumerate(ex.items, 1):
                print(f"\n  --- 第{i}题 ---")
                print(f"  {item.question}")
                if item.options:
                    for j, opt in enumerate(item.options):
                        label = chr(65 + j)
                        print(f"    {label}. {opt}")

                while True:
                    try:
                        user_input = input(f"\n  你的答案: ").strip()
                        if not user_input:
                            print("  请输入答案")
                            continue
                        break
                    except (EOFError, KeyboardInterrupt):
                        user_input = ""
                        break

                user_inputs.append(user_input)

            answers = parse_answers(ex.items, user_inputs)

            print(f"\n  分析答题结果...")
            answers_json = json.dumps(answers, ensure_ascii=False)
            exercise_json = json.dumps(ex.model_dump(), ensure_ascii=False)
            try:
                assessment = generate_assessment_report(teacher, exercise_json, answers_json, profile_text, tools=tools)
            except ValueError as e:
                print(f"\n  {e}")
                continue

            print(f"\n  {'=' * 40}")
            print(f"  评估结果")
            print(f"  {'=' * 40}")
            print(f"  得分: {assessment.total_score}/{assessment.max_score} ({assessment.percentage}%)")
            if assessment.strengths:
                print(f"\n  已掌握知识点:")
                for s in assessment.strengths:
                    print(f"    ✅ {s}")
            if assessment.weak_points:
                print(f"\n  薄弱点:")
                for wp in assessment.weak_points:
                    kp = wp.get("knowledge_point", "未知")
                    ec = wp.get("error_count", 0)
                    qs = wp.get("questions", [])
                    print(f"    ⚠️ {kp} (错{ec}题): {', '.join(qs)}")
            if assessment.suggestions:
                print(f"\n  学习建议:")
                for i, s in enumerate(assessment.suggestions, 1):
                    print(f"    {i}. {s}")
            continue

        # ── /path ──
        if raw.startswith("/path"):
            user_input = raw[6:].strip()
            topic = user_input or "Python 编程"

            cached = memory.get_path(topic)
            if cached:
                print(f"\n  📋 学习路径（已缓存）: {cached.title}")
                print(f"  主题: {cached.topic}")
                print(f"  节点数: {len(cached.nodes)}")
                print(f"  更新时间: {cached.updated_at}")
                print()
                for node in cached.nodes:
                    status_icon = {"pending": "⬜", "in_progress": "🔄", "completed": "✅"}.get(node.status, "⬜")
                    deps_str = f" ← {', '.join(node.deps)}" if node.deps else ""
                    print(f"  {status_icon} [{node.type}] {node.title} ({node.duration}){deps_str}")
                continue

            print(f"\n  生成学习路径: {topic} ...")
            profile_text = store.get_profile(user_id)
            tools = get_tools(user_id)
            crew = build_path_crew(teacher, user_id, topic, profile_text, tools=tools)
            result = runner.run(crew)

            try:
                data = _extract_json(result.raw)
                if not data:
                    raise ValueError("未找到有效 JSON")
                path = LearningPath.model_validate(data)
                path.user_id = user_id
                memory.save_path(path)
                print(f"\n  📋 学习路径: {path.title}")
                print(f"  主题: {path.topic}")
                print(f"  节点数: {len(path.nodes)}")
                for node in path.nodes:
                    deps_str = f" ← {', '.join(node.deps)}" if node.deps else ""
                    print(f"  ⬜ [{node.type}] {node.title} ({node.duration}){deps_str}")
            except Exception as e:
                print(f"\n  ⚠️ 解析学习路径失败: {e}")
                print(f"  原始输出:\n{result.raw[:500]}")
            continue

        # ── /classroom ──
        if raw.startswith("/classroom"):
            topic = raw[11:].strip()
            if not topic:
                print("用法: /classroom <主题>")
                continue

            session.next_turn()
            profile_text = store.get_profile(user_id)
            tools = get_tools(user_id, resource_type="classroom")

            print(f"\n  生成虚拟课堂: {topic} ...")

            crew = build_classroom_crew(teacher, topic, profile_text, tools=tools)
            result = runner.run(crew, on_chunk=lambda c: print(c, end="", flush=True))

            data = _extract_json(result.raw)
            if not data:
                print(f"\n  解析失败，原始输出:\n{result.raw[:500]}")
            else:
                try:
                    classroom = ClassroomScript.model_validate(data)
                    from tools.classroom_tools import PptxFromClassroomTool
                    pt = PptxFromClassroomTool()
                    fp = pt._run(classroom_json=json.dumps(data, ensure_ascii=False), filename=classroom.title)
                    print(f"\n{fp}")
                    for i, slide in enumerate(classroom.slides, 1):
                        script_preview = slide.script[:60].replace("\n", " ")
                        print(f"  {i}. {slide.title} | {script_preview}...")
                except Exception as e:
                    print(f"\n  校验失败: {e}")

            print(f"\n{format_metrics(result.metrics)}")
            memory.save_turn(session.session_id, session.turn,
                           f"/classroom {topic}", result.raw)
            continue

        print(f"未知命令: {raw}，请使用 /ask /gen /profile /exit")


if __name__ == "__main__":
    main()
