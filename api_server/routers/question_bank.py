"""题库路由（全体共享，记录真实贡献者）。"""
from __future__ import annotations

from fastapi import APIRouter

from api_server.deps import _uid
from core.question_parser import parse_questions
from db.vector_store import get_store
from schemas.requests import SaveQuestionsRequest

router = APIRouter(tags=["question-bank"])


@router.get("/api/question-bank/topics")
async def list_question_topics():
    store = get_store()
    return {"topics": store.question_bank_list_topics()}


@router.get("/api/question-bank/{topic}")
async def get_questions_by_topic(topic: str):
    store = get_store()
    items = store.question_bank_get_by_topic(topic)
    results = []
    for item in items:
        questions = parse_questions(item["text"])
        for q in questions:
            q["_id"] = item["id"]
            q["_topic"] = item.get("metadata", {}).get("topic", "")
        results.extend(questions)
    return {"topic": topic, "questions": results}


@router.post("/api/question-bank/save")
async def save_questions(req: SaveQuestionsRequest):
    user_id = _uid()
    store = get_store()
    questions = parse_questions(req.raw_text)
    count = 0
    for q in questions:
        lines = []
        tag = {
            "￥题型": q.get("type", ""),
            "￥知识点": q.get("knowledge_point", ""),
            "￥题目": q.get("question", ""),
            "￥答案": q.get("answer", ""),
            "￥解析": q.get("explanation", ""),
            "￥难度": q.get("difficulty", ""),
        }
        for label, value in tag.items():
            lines.append(f"{label}：{value}")
        for opt in q.get("options", []):
            lines.append(f"￥选项{opt['label']}：{opt['text']}")
        question_text = "\n".join(lines)
        meta = {
            "type": q.get("type", ""),
            "knowledge_point": q.get("knowledge_point", ""),
            "difficulty": q.get("difficulty", ""),
            "source": "generated",
            # 题库是全体共享的，记录真实贡献者便于审计与追溯（原 user_id 字段
            # 由客户端填写且从未被读取）。
            "created_by": user_id,
        }
        store.question_bank_add(req.topic, question_text, meta=meta)
        count += 1
    return {"saved": count, "topic": req.topic}
