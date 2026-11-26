"""
/classroom 命令的 Crew — 虚拟课堂脚本生成。
"""
import json

from crewai import Task, Crew, Process
from schemas import ClassroomScript


def schema_to_prompt(schema_class) -> str:
    """从 Pydantic schema 生成占位符示例 JSON，供 LLM 理解输出格式。"""
    schema = schema_class.model_json_schema()

    def _example(props, defs):
        result = {}
        for key, prop in props.items():
            ref = prop.get("$ref", "")
            if ref:
                ref_name = ref.split("/")[-1]
                ref_props = defs[ref_name]["properties"]
                result[key] = [_example(ref_props, defs)] if prop.get("type") == "array" else _example(ref_props, defs)
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


def build_classroom_crew(teacher, topic: str, profile_text: str = "", tools=None) -> Crew:
    if tools is not None:
        teacher.tools = tools

    profile_section = ""
    if profile_text.strip():
        profile_section = f"\n用户画像：{profile_text}\n"

    task = Task(
        description=(
            f"生成虚拟课堂内容。主题：{topic}\n"
            f"{profile_section}\n"
            "请先调用 ProfileGetTool 获取画像，然后调用 KnowledgeSearchTool 检索知识库中与主题相关的知识点。\n\n"
            "你需要生成：\n"
            "1. 8~12 页幻灯片（每页含 title、bullet_points、口语讲稿 script）\n"
            "2. 3 道课堂测验题（课前 pre、课中 mid、课后 post 各一道，含选项和答案）\n\n"
            f"{schema_to_prompt(ClassroomScript)}"
        ),
        expected_output="虚拟课堂脚本 JSON",
        agent=teacher,
    )

    return Crew(
        agents=[teacher],
        tasks=[task],
        process=Process.sequential,
        stream=True,
        verbose=False,
    )
