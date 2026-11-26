"""
考试工具 — 答题评分与薄弱点分析。

- ScoreTool：对学生答案与标准答案进行比对评分
- WeakPointAnalyzer：根据错题统计薄弱知识点
"""
import json
from crewai.tools import BaseTool

from core.short_answer_grader import grade_short_answer


class ScoreTool(BaseTool):
    name: str = "ScoreTool"
    description: str = (
        "对学生的答题结果进行评分。"
        "参数 answers_json: 学生答案 JSON 字符串（[{\"question\": \"...\", \"answer\": \"...\"}, ...]）。"
        "参数 exercise_json: 标准答案 JSON 字符串（符合 ExerciseOutput schema）。"
        "返回评分结果 JSON：{score, total, percentage, wrong_items: [...]}。"
    )

    def _run(self, answers_json: str, exercise_json: str) -> str:
        answers = json.loads(answers_json)
        exercise = json.loads(exercise_json)

        items = exercise.get("items", [])
        total = sum(item.get("score", 10) for item in items)

        wrong_items = []
        item_results = []
        score = 0.0

        for item in items:
            question = item.get("question", "")
            correct = item.get("answer", "")
            item_score = item.get("score", 10)
            knowledge_point = item.get("knowledge_point", "")
            item_type = item.get("type", "single_choice")

            user_answer = ""
            for ans in answers:
                if ans.get("question", "").strip() == question.strip():
                    user_answer = ans.get("answer", "")
                    break

            feedback = ""
            missing_points = []
            grading_mode = "exact_match"
            if item_type == "short_answer":
                judgement = grade_short_answer(question, correct, user_answer)
                ratio = float(judgement.get("score", 0.0))
                feedback = str(judgement.get("reason", ""))
                missing_points = judgement.get("missing_points") or []
                # 记录评分方式，便于统计有多少题从语义评分降级成了字面相似度。
                grading_mode = str(judgement.get("grading_mode", "unknown"))
            else:
                ratio = 1.0 if user_answer.strip().lower() == correct.strip().lower() else 0.0

            awarded_score = round(float(item_score) * ratio, 2)
            score += awarded_score
            item_results.append({
                "question": question,
                "knowledge_point": knowledge_point,
                "item_type": item_type,
                "awarded_score": awarded_score,
                "max_score": item_score,
                "ratio": round(ratio, 4),
                "feedback": feedback,
                "missing_points": missing_points,
                "grading_mode": grading_mode,
            })

            if ratio < 0.999:
                wrong_items.append({
                    "question": question,
                    "correct_answer": correct,
                    "user_answer": user_answer,
                    "knowledge_point": knowledge_point,
                    "score": awarded_score,
                    "max_score": item_score,
                    "ratio": round(ratio, 4),
                    "feedback": feedback,
                    "missing_points": missing_points,
                })

        score = round(score, 2)
        percentage = round(score / total * 100, 1) if total > 0 else 0

        result = {
            "score": score,
            "total": total,
            "percentage": percentage,
            "wrong_items": wrong_items,
            "item_results": item_results,
        }
        return json.dumps(result, ensure_ascii=False, indent=2)


class WeakPointAnalyzer(BaseTool):
    name: str = "WeakPointAnalyzer"
    description: str = (
        "分析错题关联的知识点，输出薄弱点列表。"
        "参数 wrong_items_json: 错题 JSON 字符串（评分结果中的 wrong_items 数组）。"
        "返回薄弱点列表 JSON：[{knowledge_point, count, questions: [...]}, ...]。"
    )

    def _run(self, wrong_items_json: str) -> str:
        wrong_items = json.loads(wrong_items_json)

        point_map = {}
        for item in wrong_items:
            kp = item.get("knowledge_point", "").strip()
            if not kp:
                kp = "未标记知识点"
            if kp not in point_map:
                point_map[kp] = {"knowledge_point": kp, "count": 0, "questions": []}
            point_map[kp]["count"] += 1
            point_map[kp]["questions"].append(item.get("question", ""))

        result = sorted(point_map.values(), key=lambda x: x["count"], reverse=True)
        return json.dumps(result, ensure_ascii=False, indent=2)
