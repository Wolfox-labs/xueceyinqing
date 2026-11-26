"""评估业务编排 — 出题与确定性评分。"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone

from core.memory import MemoryManager
from core.runner import CrewRunner
from core.parsing import _extract_json
from core.assessment_flow import parse_answers
from schemas import AssessmentResult
from schemas.resources import ExerciseOutput
from db.vector_store import get_store

# 注意：crews.assessment / tools.exam_tools / tools.registry 都会在导入时拉起
# crewai。它们改为在使用处局部导入，否则 `import core.assessment_service`
# 会把整个 LLM 框架拖进来，本模块里的纯逻辑函数就无法被单元测试直接导入。

_pending_exercises: dict[tuple[str, str], tuple[ExerciseOutput, datetime]] = {}
_PENDING_TTL = timedelta(hours=2)

_TYPE_ALIASES = {
    "multiple_choice": "multi_choice",
    "single": "single_choice",
    "multi": "multi_choice",
    "multiple": "multi_choice",
    "tf": "true_false",
    "bool": "true_false",
    "short": "short_answer",
    "essay": "short_answer",
}

_DIFFICULTY_ALIASES = {
    "easy": "基础",
    "basic": "基础",
    "beginner": "基础",
    "简单": "基础",
    "容易": "基础",
    "易": "基础",
    "初级": "基础",
    "medium": "进阶",
    "intermediate": "进阶",
    "normal": "进阶",
    "中等": "进阶",
    "中": "进阶",
    "hard": "综合",
    "advanced": "综合",
    "difficult": "综合",
    "困难": "综合",
    "难": "综合",
    "高级": "综合",
}
_OBJECTIVE_TYPES = {"single_choice", "multi_choice", "true_false"}


def _question_fingerprint(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "")).lower()


def _history_key(user_id: str, topic: str, question_count: int) -> str:
    return f"assessment_question_history_{user_id}_{topic}_{question_count}"


# 选项字母上限到 H：原先写死 A-D（正则与答案映射都只认四个字母），
# 出现 E/F 选项时正则抽不出来、答案映射也被静默丢弃，直接判错。
_OPTION_LETTERS = "ABCDEFGH"
_OPTION_PATTERN = re.compile(
    rf"([{_OPTION_LETTERS}])[.、．)]\s*(.*?)(?=\s+[{_OPTION_LETTERS}][.、．)]|$)",
    re.DOTALL,
)


def _normalize_option_texts(options: list) -> list[str]:
    result = []
    for option in options:
        if option is None:
            continue
        text = str(option).strip()
        if text.lower() in {"none", "null"}:
            continue
        text = re.sub(rf"^[{_OPTION_LETTERS}][.、．)]\s*", "", text)
        if text:
            result.append(text)
    return result


def _extract_options_from_question(question: str) -> tuple[str, list[str]]:
    matches = list(_OPTION_PATTERN.finditer(question or ""))
    if len(matches) < 2:
        return question, []
    options = [match.group(2).strip() for match in matches]
    cleaned_question = (question[:matches[0].start()] + question[matches[-1].end():]).strip()
    return cleaned_question or question, options


def _normalize_exercise_items(items: list[dict]) -> list[dict]:
    normalized: list[dict] = []
    for raw_item in items:
        item = dict(raw_item)
        item_type = _TYPE_ALIASES.get(item.get("type", ""), item.get("type", "single_choice"))
        question = str(item.get("question", "")).strip()
        options = item.get("options") if isinstance(item.get("options"), list) else []
        options = _normalize_option_texts(options)

        if not options:
            question, extracted = _extract_options_from_question(question)
            options = _normalize_option_texts(extracted)

        if item_type == "true_false" and len(options) < 2:
            options = ["对", "错"]

        answer = str(item.get("answer", "") or "").strip()
        if item_type in {"single_choice", "multi_choice", "true_false"}:
            compact = re.sub(r"[\s,，;；、]+", "", answer.upper())
            labels = [ch for ch in compact if ch in _OPTION_LETTERS]
            if item_type == "single_choice" and labels:
                index = ord(labels[0]) - ord("A")
                if index < len(options):
                    answer = options[index]
            elif item_type == "multi_choice" and labels:
                answer = "; ".join(
                    options[ord(label) - ord("A")]
                    for label in labels
                    if ord(label) - ord("A") < len(options)
                )
            elif item_type == "true_false":
                lowered = answer.lower()
                if lowered in {"a", "true", "正确", "对", "是"}:
                    answer = options[0]
                elif lowered in {"b", "false", "错误", "错", "否"}:
                    answer = options[1]

        if item_type in {"single_choice", "multi_choice"} and len(options) < 2:
            item_type = "short_answer"
        if item_type == "short_answer":
            options = []

        item["type"] = item_type
        item["question"] = question
        item["options"] = options or None
        item["answer"] = answer
        item.setdefault("explanation", "")
        item.setdefault("score", 10)
        item.setdefault("knowledge_point", "")
        difficulty = str(item.get("difficulty", "") or "").strip().lower()
        item["difficulty"] = _DIFFICULTY_ALIASES.get(difficulty, "基础")
        normalized.append(item)
    return normalized

def _select_unique_objective_items(
    items: list[dict],
    history_sets: list[list[str]],
    limit: int,
) -> list[dict]:
    """只保留三种客观题，并过滤批内重复和历史重复。"""
    historical = {
        _question_fingerprint(question)
        for question_set in history_sets
        for question in question_set
    }
    batch_seen: set[str] = set()
    selected: list[dict] = []
    for item in items:
        if item.get("type") not in _OBJECTIVE_TYPES:
            continue
        if not item.get("question") or not item.get("answer"):
            continue
        fingerprint = _question_fingerprint(item.get("question", ""))
        if not fingerprint or fingerprint in historical or fingerprint in batch_seen:
            continue
        selected.append(item)
        batch_seen.add(fingerprint)
        if len(selected) >= limit:
            break
    return selected


class AssessmentService:
    """评估业务编排器。"""

    def __init__(self, user_id: str, teacher_agent):
        self.user_id = user_id
        self._teacher = teacher_agent
        self._memory = MemoryManager(user_id)

    @staticmethod
    def _format_exercise_response(assessment_id: str, exercise: ExerciseOutput) -> dict:
        return {
            "assessment_id": assessment_id,
            "title": exercise.title,
            "questions": [
                {
                    "id": i,
                    "type": item.type,
                    "question": item.question,
                    "options": item.options,
                    "score": item.score,
                    "knowledge_point": item.knowledge_point,
                    "difficulty": item.difficulty,
                }
                for i, item in enumerate(exercise.items)
            ],
        }

    def generate_questions(self, topic: str, question_count: int = 5) -> dict:
        question_count = max(1, min(int(question_count), 20))
        topic_key = topic.strip()
        store = get_store()
        history_key = _history_key(self.user_id, topic_key, question_count)
        history_data = store.get_data(history_key) or {"sets": []}
        history_sets = [list(item) for item in history_data.get("sets", []) if item]
        avoid_questions = [question for question_set in history_sets[-5:] for question in question_set]

        profile_text = ""
        try:
            profile_text = self._memory.get_profile_text()
        except Exception:
            pass

        from crews.assessment import build_assessment_crew  # 局部导入：见文件头说明
        from tools.registry import get_tools

        tools = get_tools(self.user_id, resource_type="assessment")
        selected_items: list[dict] = []
        last_raw = ""
        data: dict = {}

        for _attempt in range(4):
            crew = build_assessment_crew(
                self._teacher,
                self.user_id,
                topic_key,
                profile_text,
                tools=tools,
                question_count=question_count,
                avoid_questions=avoid_questions,
            )
            result = CrewRunner().run(crew)
            last_raw = result.raw.strip() if hasattr(result, "raw") else str(result).strip()
            data = _extract_json(last_raw) or {}
            normalized = _normalize_exercise_items(data.get("items", []))
            objective_items = [
                item for item in normalized
                if item.get("type") in _OBJECTIVE_TYPES and item.get("question") and item.get("answer")
            ]

            unique_items = _select_unique_objective_items(
                objective_items,
                history_sets,
                question_count,
            )
            if len(unique_items) >= question_count:
                selected_items = unique_items
                break
            avoid_questions.extend(item.get("question", "") for item in objective_items)

        if len(selected_items) < question_count:
            raise ValueError(f"无法生成足够的不重复客观题。最后输出：{last_raw[:500]}")

        exercise = ExerciseOutput.model_validate({
            "title": data.get("title") or f"{topic_key} 检测题库",
            "items": selected_items,
        })
        assessment_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc)
        _pending_exercises[(self.user_id, assessment_id)] = (exercise, created_at)
        history_sets.append([item.question for item in exercise.items])
        store.save_data(history_key, {"sets": history_sets[-20:]})
        return self._format_exercise_response(assessment_id, exercise)

    @staticmethod
    def build_local_result(
        user_id: str,
        topic: str,
        exercise: ExerciseOutput,
        mapped_answers: list[dict],
    ) -> AssessmentResult:
        """使用本地 ScoreTool 评分，不依赖大模型输出格式。"""
        from tools.exam_tools import ScoreTool  # 局部导入：见文件头说明

        exercise_json = json.dumps(exercise.model_dump(), ensure_ascii=False)
        answers_json = json.dumps(mapped_answers, ensure_ascii=False)
        score_data = json.loads(ScoreTool()._run(answers_json, exercise_json))

        item_results = score_data.get("item_results") or []
        point_stats: dict[str, dict] = {}
        if item_results:
            for item in item_results:
                point = str(item.get("knowledge_point") or "未标记知识点").strip()
                stats = point_stats.setdefault(point, {"earned": 0.0, "total": 0.0})
                stats["total"] += float(item.get("max_score", 0))
                stats["earned"] += float(item.get("awarded_score", 0))
        else:
            answer_map = {
                str(item.get("question", "")).strip(): str(item.get("answer", "")).strip().lower()
                for item in mapped_answers
            }
            for item in exercise.items:
                point = item.knowledge_point.strip() or "未标记知识点"
                stats = point_stats.setdefault(point, {"earned": 0.0, "total": 0.0})
                stats["total"] += item.score
                user_answer = answer_map.get(item.question.strip(), "")
                if user_answer == item.answer.strip().lower():
                    stats["earned"] += item.score

        weak_points = []
        strengths = []
        for point, stats in point_stats.items():
            point_score = round(stats["earned"] / stats["total"] * 100, 1) if stats["total"] else 0.0
            if point_score < 80:
                weak_points.append({"knowledge_point": point, "score": point_score})
            else:
                strengths.append(point)
        weak_points.sort(key=lambda item: item["score"])

        if weak_points:
            names = "、".join(item["knowledge_point"] for item in weak_points[:3])
            suggestions = [
                f"优先复习 {names}，先查看讲解再进行一次变式练习。",
                "对错题重新说明解题依据，确认不是靠记忆选项作答。",
            ]
        else:
            suggestions = [
                "本次测评表现稳定，可以提升题目难度或进入下一学习节点。",
                "建议在 3 天后进行一次间隔复习，巩固当前掌握度。",
            ]

        return AssessmentResult(
            user_id=user_id,
            topic=topic,
            total_score=int(round(float(score_data.get("score", 0)))),
            max_score=int(score_data.get("total", 0)),
            percentage=float(score_data.get("percentage", 0.0)),
            weak_points=weak_points,
            strengths=strengths,
            suggestions=suggestions,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def grade(self, assessment_id: str, answers: list[dict]) -> AssessmentResult:
        record = _pending_exercises.get((self.user_id, assessment_id))
        if record is None:
            raise ValueError("测评不存在或已过期，请重新生成题目")
        exercise, created_at = record
        if datetime.now(timezone.utc) - created_at > _PENDING_TTL:
            _pending_exercises.pop((self.user_id, assessment_id), None)
            raise ValueError("测评已过期，请重新生成题目")

        answers_by_id = {
            int(item.get("question_id", -1)): str(item.get("answer", "") or "")
            for item in answers
        }
        raw_answers = [answers_by_id.get(index, "") for index in range(len(exercise.items))]
        mapped_answers = parse_answers(exercise.items, raw_answers)
        result = self.build_local_result(
            self.user_id,
            exercise.title,
            exercise,
            mapped_answers,
        )
        self._memory.save_assessment(result.model_dump())
        _pending_exercises.pop((self.user_id, assessment_id), None)
        return result