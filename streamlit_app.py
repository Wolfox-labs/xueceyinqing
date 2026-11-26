"""
mlqk 前端 — Streamlit 应用。
uv run streamlit run streamlit_app.py
"""
import json
import queue
import threading

import streamlit as st

from agents import create_agents
from core import CrewPipeline, MemoryManager
from core.parsing import _extract_json
from crews.ask import build_ask_crew
from crews.generate import build_gen_crew, json_to_mindmap_html
from schemas import MindmapOutput, DocumentOutput, ExerciseOutput, StudentProfile
from tools.registry import get_tools
from db.vector_store import get_store, init_knowledge_base
from utils.tokens import format_metrics


@st.cache_resource
def init():
    init_knowledge_base()
    profile_agent, teacher, reviewer = create_agents("default")
    store = get_store()
    memory = MemoryManager("default")
    pipeline = CrewPipeline(reviewer, memory)
    return profile_agent, teacher, reviewer, store, memory, pipeline


profile_agent, teacher, reviewer, store, memory, pipeline = init()


st.set_page_config(page_title="mlqk", layout="wide")

with st.sidebar:
    st.markdown("### 用户画像")
    text = store.get_profile("default")
    p = StudentProfile.from_text(text)
    st.caption(f"阶段：{p.learning_stage}")
    st.caption(f"偏好：{p.learning_style}  |  风格：{p.language_style}")
    if p.subjects:
        st.caption(f"学科：{'、'.join(p.subjects)}")
    if p.weak_points:
        st.caption(f"薄弱：{'、'.join(p.weak_points)}")

    st.divider()
    st.markdown("### 资源生成")
    rtype = st.selectbox("类型", ["document", "mindmap", "exercise", "ppt"])
    topic = st.text_input("主题", placeholder="例如：Python 列表推导式")
    gen_btn = st.button("生成资源", use_container_width=True)

st.title("mlqk — 个性化学习助手")

if "messages" not in st.session_state:
    st.session_state["messages"] = []


for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if q := st.chat_input("输入问题..."):
    st.session_state["messages"].append({"role": "user", "content": q})
    with st.chat_message("user"):
        st.markdown(q)
    with st.chat_message("assistant"):
        tools = get_tools("default")
        ctx = memory.get_context("streamlit_session", 1)
        crew = build_ask_crew(profile_agent, teacher, q, ctx, tools=tools)

        q_ = queue.Queue()
        def _run():
            r = pipeline.execute(crew,
                session_id="streamlit_session", turn=1, question=q,
                on_chunk=lambda c: q_.put(("chunk", c)))
            q_.put(("result", r))
        t = threading.Thread(target=_run)
        t.start()

        collected = []
        result = None
        placeholder = st.empty()
        while True:
            item = q_.get()
            if isinstance(item, tuple) and item[0] == "result":
                result = item[1]
                break
            collected.append(item[1])
        full = "".join(collected)
        placeholder.empty()

        if result and result.withdrawn:
            full = f"⚠️ 内容已被审核撤回：{result.reason}"

        st.markdown(full)
        st.session_state["messages"].append({"role": "assistant", "content": full})


if gen_btn and topic:
    with st.spinner(f"生成 {rtype}: {topic}..."):
        tools = get_tools("default", resource_type=rtype)
        crew = build_gen_crew(teacher, reviewer, rtype, topic, tools=tools)

        q_ = queue.Queue()
        def _run():
            r = pipeline.execute(crew,
                session_id="streamlit_session", turn=2,
                question=f"/gen {rtype} {topic}",
                on_chunk=lambda c: q_.put(("chunk", c)))
            q_.put(("result", r))
        t = threading.Thread(target=_run)
        t.start()

        collected = []
        result = None
        while True:
            item = q_.get()
            if isinstance(item, tuple) and item[0] == "result":
                result = item[1]
                break
            collected.append(item[1])
        raw = "".join(collected)

    if result and result.withdrawn:
        st.warning(f"内容已被审核撤回：{result.reason}")
    else:
        st.caption(f"Tokens: {format_metrics(getattr(result, 'metrics', None) or '--')}")
        if rtype == "mindmap":
            try:
                data = _extract_json(raw)
                mindmap = MindmapOutput.model_validate(data)
                st.markdown(json_to_mindmap_html(mindmap.model_dump()), unsafe_allow_html=True)
            except Exception:
                st.markdown(raw)
        elif rtype == "document":
            try:
                data = _extract_json(raw)
                doc = DocumentOutput.model_validate(data)
                st.markdown(f"# {doc.title}")
                for s in doc.sections:
                    st.markdown(f"## {s.heading}")
                    st.markdown(s.body)
                from tools.docx_tools import DocxGenerateTool
                dt = DocxGenerateTool()
                md = "\n".join([f"# {doc.title}"] + [f"## {s.heading}\n\n{s.body}" for s in doc.sections])
                fp = dt._run(content=md, filename=doc.title)
                st.success(fp)
            except Exception:
                st.markdown(raw)
        elif rtype == "exercise":
            try:
                data = _extract_json(raw)
                ex = ExerciseOutput.model_validate(data)
                st.markdown(f"## {ex.title}")
                score = 0
                total = 0
                for i, item in enumerate(ex.items):
                    st.markdown(f"**第{i+1}题** {item.question}")
                    if item.options:
                        ans = st.radio(f"选项_{i}", item.options, key=f"quiz_{i}", index=None)
                        if ans == item.answer:
                            score += 1
                            st.success("正确")
                        elif ans:
                            st.error(f"正确答案：{item.answer}")
                    else:
                        user_ans = st.text_input(f"答案_{i}", key=f"quiz_{i}")
                        if user_ans:
                            total += item.score
                            if user_ans.strip() == item.answer.strip():
                                score += item.score
                                st.success("正确")
                            else:
                                st.error(f"正确答案：{item.answer}")
                    with st.expander("解析"):
                        st.write(item.explanation)
                    st.divider()
                if total > 0:
                    st.metric("得分", f"{score}/{total}")
            except Exception:
                st.markdown(raw)
        elif rtype == "ppt":
            try:
                from schemas import PPTOutput
                data = _extract_json(raw)
                ppt = PPTOutput.model_validate(data)
                st.markdown(f"# {ppt.title}")
                for i, slide in enumerate(ppt.slides):
                    st.markdown(f"## 第{i+1}页：{slide.title}")
                    for point in slide.bullet_points:
                        st.markdown(f"- {point}")
                    if slide.notes:
                        with st.expander("讲稿备注"):
                            st.write(slide.notes)
                    st.divider()
                from tools.pptx_tools import PptxGenerateTool
                pt = PptxGenerateTool()
                fp = pt._run(slides_json=json.dumps(data, ensure_ascii=False), filename=ppt.title)
                st.success(fp)
            except Exception:
                st.markdown(raw)
        else:
            st.markdown(raw)
