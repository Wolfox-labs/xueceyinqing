"""
/assess 命令的 Crew — 评估题库生成 + 答题分析。
"""
import json
from crewai import Task, Crew, Process
from schemas import ExerciseOutput, AssessmentResult


def _schema_to_prompt(schema_class) -> str:
    schema = schema_class.model_json_schema()

    def _example(props, defs):
        result = {}
        for key, prop in props.items():
            ref = prop.get("$ref", "")
            if ref:
                ref_name = ref.split("/")[-1]
                ref_props = defs[ref_name]["properties"]
                result[key] = [_example(ref_props, defs)] if prop.get("type") == "array" else _example(ref_props, defs)
            elif "anyOf" in prop:
                variants = [item for item in prop["anyOf"] if item.get("type") != "null"]
                variant = variants[0] if variants else {}
                if variant.get("type") == "array":
                    items = variant.get("items", {})
                    if items.get("type") == "string":
                        result[key] = [f"<{key}_内容>"]
                    elif "$ref" in items:
                        ref_name = items["$ref"].split("/")[-1]
                        result[key] = [_example(defs[ref_name]["properties"], defs)]
                    else:
                        result[key] = ["<内容>"]
                elif variant.get("type") == "string":
                    result[key] = f"<{key}>"
            elif prop.get("type") == "array":
                items = prop.get("items", {})
                if items.get("type") == "string":
                    result[key] = [f"<{key}_内容>"]
                elif "$ref" in items:
                    ref_name = items["$ref"].split("/")[-1]
                    result[key] = [_example(defs[ref_name]["properties"], defs)]
                else:
                    result[key] = ["<内容>"]
            elif prop.get("type") == "string":
                result[key] = prop.get("enum", [None])[0] or f"<{key}>"
            elif prop.get("type") == "integer":
                result[key] = 0
            elif prop.get("type") == "number":
                result[key] = 0.0
        return result

    example = _example(schema["properties"], schema.get("$defs", {}))
    return (
        "请输出一个纯 JSON 对象（不要用 ```json 包裹，不要加任何说明文字），格式如下：\n"
        f"{json.dumps(example, ensure_ascii=False, indent=2)}"
    )


def build_assessment_crew(teacher, user_id: str, topic: str,
                          profile_text: str = "", tools=None,
                          question_count: int = 5,
                          avoid_questions: list[str] | None = None) -> Crew:
    if tools is not None:
        teacher.tools = tools

    profile_section = ""
    if profile_text.strip():
        profile_section = f"用户画像：{profile_text}\n"

    avoid_section = ""
    if avoid_questions:
        blocked = "\n".join(f"- {question}" for question in avoid_questions[-30:])
        avoid_section = (
            "以下题目是历史已出现题目，本次禁止重复，包括同一道题的换序、换选项顺序和轻微改写：\n"
            f"{blocked}\n\n"
        )

    task = Task(
        description=(
            f"根据以下信息生成评估检测题库：\n"
            f"{profile_section}"
            f"主题：{topic}\n"
            f"题目数量：{question_count} 道\n"
            f"重点关注画像中的薄弱点（weak_points）和知识掌握度（knowledge_mastery）\n\n"
            f"请先调用 ProfileGetTool 获取画像，然后调用 KnowledgeSearchTool 查看知识库。\n\n"
            f"生成恰好 {question_count} 道检测题，覆盖画像中的薄弱知识点。\n"
            f"每道题必须标注 knowledge_point 字段。\n"
            f"只允许生成三种客观题：single_choice（单选）、multi_choice（多选）、true_false（判断）。\n"
            f"禁止生成 short_answer，禁止主观题。\n"
            f"同一批题目之间不得重复，且不得与历史题目重复。\n"
            f"{avoid_section}"
            f"格式硬性要求：\n"
            f"- single_choice 必须提供 options 数组，包含 4 个选项。\n"
            f"- multi_choice 必须提供 options 数组，包含 4 个选项。\n"
            f"- true_false 的 options 必须严格为 [\"对\", \"错\"]。\n"
            f"- short_answer 的 options 必须为 null。\n"
            f"- answer 必须与 options 中某一项的文本完全一致；不要只写 A/B/C/D。\n"
            f"- 不要把选项写进 question 字段，选项只能放在 options 数组。\n\n"
            f"{_schema_to_prompt(ExerciseOutput)}"
        ),
        expected_output="检测题库 JSON",
        agent=teacher,
    )

    return Crew(
        agents=[teacher],
        tasks=[task],
        process=Process.sequential,
        stream=True,
        verbose=False,
    )


def analyze_results(teacher, exercise_json: str, user_answers_json: str,
                    profile_text: str = "", tools=None) -> Crew:
    if tools is not None:
        teacher.tools = tools

    profile_section = ""
    if profile_text.strip():
        profile_section = f"当前画像：{profile_text}\n"

    task = Task(
        description=(
            f"分析学生的答题结果：\n\n"
            f"标准题库：{exercise_json}\n"
            f"学生答案：{user_answers_json}\n"
            f"{profile_section}\n"
            f"请按顺序执行以下操作：\n"
            f"1. 调用 ScoreTool(answers_json, exercise_json) 计算得分\n"
            f"2. 调用 WeakPointAnalyzer(wrong_items_json) 分析错题关联的知识点\n"
            f"3. 基于分析结果，输出以下 JSON（符合 AssessmentResult schema）：\n"
            f"   - 总得分和百分比\n"
            f"   - 薄弱点分析\n"
            f"   - 已掌握的知识点（strengths）\n"
            f"   - 学习建议（suggestions，1~3条）\n\n"
            f"{_schema_to_prompt(AssessmentResult)}\n\n"
            f"4. 最后调用 ProfileUpdateTool 将新发现的薄弱点更新到画像中。"
        ),
        expected_output="评估结果 JSON",
        agent=teacher,
    )

    return Crew(
        agents=[teacher],
        tasks=[task],
        process=Process.sequential,
        stream=True,
        verbose=False,
    )
