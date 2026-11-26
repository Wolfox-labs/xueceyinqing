"""
core/assessment_flow.py — /assess 命令的业务逻辑。

提供：
  parse_answers(items, raw_answers)          → 将用户原始输入映射为标准答案格式
  generate_assessment_report(...)            → 调用分析 Crew 并解析返回 AssessmentResult
"""


def parse_answers(items, raw_answers):
    """
    将用户原始输入映射为标准答案格式。

    参数:
      items: list[dict|ExerciseItem] - 题目列表，每元素含 question/options/type
      raw_answers: list[str] - 用户原始输入，与 items 一一对应

    返回: list[dict] - [{question: ..., answer: ...}, ...]

    内部处理 single_choice/multi_choice/true_false/short_answer 四种题型映射。
    """
    results = []
    # 选项字母上限到 H：原先只认 A-D，学生选 E/F 时会被静默丢弃、判为未作答。
    option_letters = "ABCDEFGH"
    for item, user_input in zip(items, raw_answers):
        if isinstance(item, dict):
            question = item.get("question", "")
            options = item.get("options")
            item_type = item.get("type", "single_choice")
        else:
            question = item.question
            options = item.options
            item_type = item.type

        if item_type == "short_answer" or not options:
            answer_text = user_input
        elif item_type == "multi_choice":
            parts = []
            for ch in user_input.upper():
                if ch in option_letters:
                    idx = ord(ch) - ord("A")
                    if idx < len(options):
                        parts.append(options[idx])
            answer_text = "; ".join(parts) if parts else user_input
        else:
            ch = user_input[0].upper() if user_input else ""
            if ch in option_letters:
                idx = ord(ch) - ord("A")
                if idx < len(options):
                    answer_text = options[idx]
                else:
                    answer_text = user_input
            else:
                answer_text = user_input

        results.append({
            "question": question,
            "answer": answer_text,
        })
    return results


def generate_assessment_report(teacher, exercise_json, answers_json,
                                profile_text="", tools=None):
    """
    调用 analyze_results Crew 并解析返回 AssessmentResult。

    参数:
      teacher: AI Teacher Agent
      exercise_json: 标准题库 JSON 字符串
      answers_json: 学生答案 JSON 字符串
      profile_text: 用户画像文本
      tools: 工具列表

    返回: AssessmentResult 实例

    raise ValueError 当 JSON 解析失败时。
    """
    from core.parsing import _extract_json
    from core.runner import CrewRunner
    from crews.assessment import analyze_results
    from schemas import AssessmentResult

    crew = analyze_results(teacher, exercise_json, answers_json, profile_text, tools=tools)
    runner = CrewRunner()
    result = runner.run(crew)

    data = _extract_json(result.raw)
    if not data:
        raise ValueError(f"无法解析评估结果\n原始输出:\n{result.raw[:500]}")

    try:
        assessment = AssessmentResult.model_validate(data)
    except Exception as e:
        raise ValueError(f"解析评估结果失败: {e}\n原始输出:\n{result.raw[:500]}") from e

    return assessment
