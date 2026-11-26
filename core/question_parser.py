"""
Parse ￥tag formatted question text into structured data.
"""
import re

_QUESTION_SPLIT = re.compile(r"(?:^|\n)### .*(?:\n|$)|\n---\n")

_OPTION_PATTERN = re.compile(r"￥选项([A-Z])：(.+)")

_TAG_PATTERNS = [
    ("type", re.compile(r"￥题型：(.+)")),
    ("knowledge_point", re.compile(r"￥知识点：(.+)")),
    ("question", re.compile(r"￥题目：(.+)")),
    ("answer", re.compile(r"￥答案：(.+)")),
    ("explanation", re.compile(r"￥解析：(.*?)(?=￥\w+：|$)", re.DOTALL)),
    ("difficulty", re.compile(r"￥难度：(.+)")),
]


def parse_questions(raw_text: str) -> list[dict]:
    blocks = _QUESTION_SPLIT.split(raw_text)
    blocks = [b.strip() for b in blocks if b.strip()]

    results = []
    for block in blocks:
        q = {
            "type": "",
            "knowledge_point": "",
            "question": "",
            "options": [],
            "answer": "",
            "explanation": "",
            "difficulty": "",
        }

        for key, pattern in _TAG_PATTERNS:
            m = pattern.search(block)
            if m:
                q[key] = m.group(1).strip()

        q["options"] = [
            {"label": m.group(1), "text": m.group(2).strip()}
            for m in _OPTION_PATTERN.finditer(block)
        ]

        results.append(q)

    return results
