"""简答题语义评分。

目标：不再要求答案与参考答案逐字相同。
优先使用当前配置的 LLM 按语义和评分要点评分；模型不可用时回退到本地相似度评分。
"""
from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher

import httpx

from config import MODEL_LLM

logger = logging.getLogger(__name__)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _normalize(text: str) -> str:
    return re.sub(r"[\W_]+", "", (text or "").lower(), flags=re.UNICODE)


def _heuristic_score(reference: str, student: str) -> float:
    ref = _normalize(reference)
    stu = _normalize(student)
    if not ref or not stu:
        return 0.0
    if ref == stu:
        return 1.0
    sequence = SequenceMatcher(None, ref, stu).ratio()
    ref_tokens = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", reference.lower()))
    stu_tokens = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", student.lower()))
    coverage = len(ref_tokens & stu_tokens) / max(1, len(ref_tokens))

    # 包含关系必须按长度比打折：旧实现只要学生答案（≥4 字）被参考答案包含
    # 就直接给 0.95，等于答一个词就能拿满分。
    containment = 0.0
    if stu and ref and (stu in ref or ref in stu):
        shorter, longer = (stu, ref) if len(stu) <= len(ref) else (ref, stu)
        length_ratio = len(shorter) / max(1, len(longer))
        if len(shorter) >= 8 and length_ratio >= 0.5:
            containment = 0.95 * length_ratio

    return _clamp(max(sequence, coverage * 0.9, containment))


def _llm_score(question: str, reference: str, student: str) -> dict | None:
    model = MODEL_LLM.get("model")
    base_url = str(MODEL_LLM.get("base_url") or "").rstrip("/")
    api_key = MODEL_LLM.get("api_key")
    if not model or not base_url or not api_key:
        logger.warning("语义评分缺少 LLM 配置（model/base_url/api_key），回退本地相似度")
        return None
    from core.parsing import _extract_json

    prompt = f"""你是严格但公平的课程阅卷老师。请按语义评分，不要求与参考答案逐字一致。

题目：
{question}

参考答案：
{reference}

学生答案：
{student}

评分要求：
1. 核心概念正确即可给较高分，不能因为措辞不同判零分。
2. 检查是否遗漏关键要点、是否存在概念错误。
3. score 必须是 0 到 1 之间的小数。
4. 只返回 JSON，不要输出解释性前后缀。

JSON 格式：
{{"score": 0.0, "reason": "一句话评分理由", "missing_points": ["遗漏要点"]}}
"""
    try:
        response = httpx.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "你只负责依据参考答案进行语义评分。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0,
                "max_tokens": 220,
            },
            timeout=45,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"].get("content", "")
        data = _extract_json(content)
        if not isinstance(data, dict):
            logger.warning("语义评分未解析出 JSON，回退本地相似度：%r", content[:200])
            return None
        return {
            "score": _clamp(data.get("score", 0.0)),
            "reason": str(data.get("reason") or "语义评分完成"),
            "missing_points": [str(item) for item in (data.get("missing_points") or [])],
        }
    except Exception as exc:
        logger.warning("LLM 语义评分调用失败，回退本地相似度：%s", exc, exc_info=True)
        return None


def grade_short_answer(question: str, reference: str, student: str) -> dict:
    """返回 0~1 分数、理由、缺失要点与评分方式。

    grading_mode 让"语义评分悄悄降级为字面相似度"这件事可被观测：
    llm=语义评分 / heuristic=本地相似度回退 / exact=与参考答案一致 / blank=未作答。
    原先降级只换了一段 reason 文案，没有日志也没有指标——评分标准变了却无人知晓。
    """
    student = (student or "").strip()
    if not student:
        return {"score": 0.0, "reason": "学生未作答", "missing_points": ["未作答"],
                "grading_mode": "blank"}
    if _normalize(reference) == _normalize(student):
        return {"score": 1.0, "reason": "答案与参考答案一致", "missing_points": [],
                "grading_mode": "exact"}
    judged = _llm_score(question, reference, student)
    if judged is not None:
        judged.setdefault("grading_mode", "llm")
        return judged
    score = _heuristic_score(reference, student)
    return {
        "score": score,
        "reason": f"模型评分不可用，使用本地语义相似度评分：{score:.2f}",
        "missing_points": [],
        "grading_mode": "heuristic",
    }