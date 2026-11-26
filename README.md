# 学策引擎 — 算法驱动的多智能体自适应学习系统

基于 CrewAI + DeepSeek + ChromaDB 构建的学习助手。三个 AI Agent 协同工作：画像助手记录用户特征，教学助手做 RAG 问答和资源生成，审核助手把关内容质量。提供 CLI / React SPA / REST API 三种入口，支持对话记忆和多用户画像隔离。

---

## 目录

- [快速开始](#快速开始)
- [命令](#命令)
- [项目结构](#项目结构)
- [数据流](#数据流)
- [三个 Agent](#三个-agent)
- [数据库层](#数据库层)
- [对话记忆](#对话记忆)
- [用户画像](#用户画像)
- [配置说明](#配置说明)
- [如何修改](#如何修改)
- [常见问题](#常见问题)
- [工作日志](#工作日志)

---

## 快速开始

```bash
cp .env.example .env          # 填入自己的 LLM Base URL 与 API Key
uv sync                        # 安装 Python 依赖
uv run python main.py                      # CLI 交互
uv run uvicorn api_server.main:app --host 127.0.0.1 --port 8001  # 本地 REST API（React 开发服务器依赖此服务）

# React 前端
cd frontend
npm install
npm run dev                    # 开发服务器 → http://localhost:5173
```

仓库不含任何可用账号或密钥。需要演示账号时，用脚本按自己的口令创建（口令不写进代码）：

```bash
.venv\Scripts\python.exe scripts\accounts\ensure_demo_account.py --password "自定口令"
# 或：DEMO_ACCOUNT_PASSWORD="自定口令" uv run python scripts/accounts/ensure_demo_account.py
```

登录接口只认数据库里真实存在的账号；`core/auth_service.py` 的演示账号种子默认关闭，
开启时必须由 `DEMO_STUDENT_PASSWORD` / `DEMO_TEACHER_PASSWORD` 提供口令。

首次运行会初始化知识库；中文检索优先使用轻量词法匹配，必要时再使用 ChromaDB 向量检索。

---

## 命令

```
mlqk> /ask Python列表推导式是什么？
mlqk> /gen document 面向对象编程
mlqk> /gen mindmap 数据结构
mlqk> /gen exercise 列表和字典
mlqk> /gen ppt Python入门
mlqk> /assess 面向对象编程
mlqk> /classroom Python基础
mlqk> /path
mlqk> /profile
mlqk> /exit
```

| 命令 | 说明 |
|------|------|
| `/ask <问题>` | 提问。先更新画像，再结合画像+知识库+对话历史回答 |
| `/gen document <主题>` | 生成讲解文档（.docx） |
| `/gen mindmap <主题>` | 生成交互式思维导图（markmap 渲染，可缩放折叠） |
| `/gen exercise <主题>` | 生成练习题库（含答案和解析） |
| `/gen ppt <主题>` | 生成 PPT 演示文稿（.pptx） |
| `/assess <主题>` | 生成检测题库 → 交互答题 → 错题分析 → 评估报告 |
| `/classroom <主题>` | 生成虚拟课堂（PPT + 讲稿 + 三点测验） |
| `/path [主题]` | 查看/生成个性化学习路径（缓存机制） |
| `/profile` | 查看当前用户六维画像 |
| `/exit` | 退出 |

---

## 项目结构

```
mlqk/
│
├── main.py                 # CLI 入口。命令路由 + 终端 I/O（约 355 行）。
│
├── core/                   # 业务逻辑层（SDK 层）。CLI / API / Streamlit 共享。
│   ├── __init__.py         #   统一导出 11 个公开类
│   ├── runner.py           #   CrewRunner — 流式执行 Crew + 收集结果
│   ├── pipeline.py         #   CrewPipeline — 统一执行管线（ReviewContext 注入→执行→撤回→保存）
│   ├── memory.py           #   MemoryManager — 向下兼容委托，组合 3 个子模块
│   ├── conversation_memory.py  #   ConversationMemory — 对话压缩 + 上下文 + 存取
│   ├── path_store.py       #   PathStore — 学习路径存取
│   ├── assessment_store.py #   AssessmentStore — 评估结果存取
│   ├── assessment_service.py   #   AssessmentService — 评估业务编排（出题 + 评分流程串联）
│   ├── assessment_flow.py  #   parse_answers + generate_assessment_report
│   ├── question_parser.py  #   parse_questions — ￥标签格式正则解析
│   ├── parsing.py          #   _extract_json + parse_resource + _parse_mindmap + _parse_path_nodes + _parse_document（LLM 输出解析 + ￥标签/￥节点正则提取）
│   ├── report_builder.py   #   ReportBuilder — 学习报告数据构建
│   └── session.py          #   SessionManager — 会话 ID 生成 + 轮次追踪
│
├── config.py               # LLM 配置。定义 MODEL_LLM 字典，换模型只改这一个文件。
│
├── agents/                 # Agent 定义。每个文件返回一个 crewai.Agent 实例。
│   ├── __init__.py         #   create_agents(user_id) 工厂函数
│   ├── profile.py          #   画像助手 — 从对话中抽取学习特征 + 语言风格偏好
│   ├── teacher.py          #   教学助手 — RAG 检索 + 个性化回答 + 资源生成
│   ├── quiz_crafter.py     #   出题助手 — teacher 的 affiliate，专责题目生成（￥标签格式）
│   └── reviewer.py         #   审核助手 — 检查生成内容的准确性和难度匹配
│
├── crews/                  # Crew 组装。Task 序列编排 + 上下文注入。
│   ├── ask.py              #   /ask — 画像更新 → 个性化问答
│   ├── generate.py         #   /gen — 资源生成 → 审核（document/mindmap/exercise/ppt）
│   ├── assessment.py       #   /assess — 题库生成 + 答题分析
│   ├── classroom.py        #   /classroom — 虚拟课堂脚本生成
│   └── path.py             #   /path — 个性化学习路径生成（￥节点 格式）
│
├── tools/                  # CrewAI BaseTool 实现。由 tools/registry.py 统一路由。
│   ├── registry.py         #   get_tools(user_id, resource_type) — 唯一工具路由
│   ├── knowledge.py        #   KnowledgeSearchTool — 语义检索知识库
│   ├── profile_store.py    #   ProfileGetTool / ProfileUpdateTool — 画像存取
│   ├── docx_tools.py       #   DocxGenerateTool / DocxParseTool
│   ├── pptx_tools.py       #   PptxGenerateTool
│   ├── classroom_tools.py  #   PptxFromClassroomTool / QuizExtractTool / ScriptToAudioTool
│   ├── exam_tools.py       #   ScoreTool / WeakPointAnalyzer
│   └── review_tools.py     #   ReportIssueTool / WithdrawOutputTool / ReviewContext
│
├── db/                     # 数据库层。接口与实现分离，可替换后端。
│   ├── interface.py        #   StorageBackend 抽象类 — 定义所有数据库操作协议
│   └── vector_store.py     #   ChromaDB 实现。四个 collection:
│                           #     knowledge_base  — 知识文档向量索引
│                           #     user_profiles   — 用户画像 + 通用键值存储
│                           #     conversations   — 对话记忆（压缩摘要）
│                           #     question_bank   — 题库（￥标签格式）
│
├── api_server/main.py      # FastAPI — SSE 流式 + REST，12 个端点
├── frontend/                # React 前端（TypeScript + Vite + Tailwind CSS）
│   ├── src/pages/           #   6 个页面：Chat / Generate / Assess / LearningPath / Report / Profile
│   ├── src/components/      #   雷达图/折线图/饼图（Recharts）、思维导图（markmap）、Markdown 渲染
│   ├── src/stores/          #   Zustand 状态管理
│   └── src/api/             #   API 客户端 + SSE 流式 + question-bank CRUD
│
├── schemas/                # Pydantic 数据定义，CLI/API/前端共享
│   ├── resources.py        #   MindmapOutput / DocumentOutput / ExerciseOutput / PPTOutput / QUESTION_TAGS
│   ├── profile.py          #   StudentProfile 六维画像
│   ├── classroom.py        #   ClassroomScript 虚拟课堂
│   ├── learning_path.py    #   LearningPath + PathNode（含 resource_type / resource_ref）
│   └── assessment.py       #   AssessmentResult / QuestionItem / AssessGenerateRequest 等
│
├── scripts/                # 启动与运维脚本
│   ├── start_xuece.ps1     #   一键启动入口，保留原路径
│   ├── accounts/           #   演示账号初始化、学习会话种子数据
│   ├── data/               #   题库导入、历史数据迁移
│   └── diagnostics/        #   知识库评估、模型连接及流式输出诊断
│
├── docs/diagrams/          # 项目配图（保留可编辑架构图 PPT）
│
├── utils/
│   └── tokens.py           #   format_metrics() — Token 用量格式化输出
│
├── knowledge/              # 知识文档。启动时自动索引到 knowledge_base。
│   ├── python_basics.txt
│   ├── python_oop.txt
│   ├── data_structures.txt
│   ├── python_strings.txt
│   └── ...
│
├── runtime/chroma_data/            # ChromaDB 持久化数据（gitignore，自动生成）
├── output/                 # 生成的文件输出目录（.docx / .pptx / .md）
├── report/                 # 工作日志与审计报告
├── guidelines/             # 开发规范文档（￥标签 标准等）
├── .env                    # DeepSeek API Key + 模型名
├── pyproject.toml          # 项目元数据 + 依赖
└── uv.lock                 # 依赖锁定
```

---

## 数据流

```
用户输入 /ask "列表推导式是什么？"
    │
    ▼
main.py（命令路由）
    │
    ├─ 1. memory.get_context(session_id, turn)
    │      ConversationMemory 从 ChromaDB 取最近 5 轮记录，格式化为上下文文本
    │
    ├─ 2. build_ask_crew(profile_agent, teacher, question, context, tools=...)
    │      tools 由 tools/registry.py 的 get_tools(user_id) 动态挂载
    │
    ├─ 3. pipeline.execute(crew, session_id=..., turn=..., question=...)
    │      CrewPipeline 统一封装：ReviewContext 注入 → 流式执行 → 撤回检查 → 记忆保存
    │       │
    │       ├─ Task1: profile_agent 执行
    │       │     ├─ ProfileGetTool._run()     → store.get_profile(user_id)
    │       │     ├─ LLM 分析问题 + 历史上下文，抽取特征
    │       │     └─ ProfileUpdateTool._run()   → store.update_profile(user_id, text)
    │       │
    │       └─ Task2: teacher 执行
    │             ├─ ProfileGetTool._run()      → store.get_profile(user_id)
    │             ├─ KnowledgeSearchTool._run()  → store.search_knowledge(query)
    │             └─ LLM 结合画像 + 知识 + 历史上下文，生成回答
```

`/gen` 流程同理，额外多一个 Task：reviewer 调用 ReportIssueTool / WithdrawOutputTool 审核。

### 分层职责

| 层 | 职责 | 例子 |
|----|------|------|
| `main.py`（适配层） | 命令解析 + 终端 I/O | 读输入、打印 chunk、显示 banner |
| `core/`（业务层） | 纯逻辑，无 I/O | 执行 Crew、压缩记忆、管理 session |
| `agents/` + `crews/`（Agent 层） | Agent 定义 + Task 编排 | 创建 Agent 实例、定义 Task 顺序 |
| `tools/`（工具层） | Agent 可调用的工具 | 知识检索、画像读写 |
| `db/`（存储层） | 数据持久化 | ChromaDB 读写、向量检索 |

---

## 三个 Agent

### 画像助手 (profile)

- **角色**：教育数据分析师
- **做的事**：每轮 `/ask` 调用前读旧画像，分析当前问题和对话历史，抽取学习特征和语言风格偏好，融合后写回
- **工具**：`ProfileGetTool`（读）、`ProfileUpdateTool`（写）
- **输出格式**：
  ```
  学习阶段：xxx
  关注学科：xxx
  薄弱环节：xxx
  学习偏好：xxx
  语言风格：xxx
  ```
- **改 prompt 位置**：`agents/profile.py` 的 `backstory`（角色设定）和 `crews/ask.py` 的 `profile_task.description`（任务指令）

### 教学助手 (teacher)

- **角色**：AI 教师
- **做的事**：读画像 → 查知识库 → 结合对话上下文 → 生成个性化回答或学习资源
- **工具**：`KnowledgeSearchTool`（检索知识库）、`ProfileGetTool`（读画像）
- **改 prompt 位置**：`agents/teacher.py` 的 `backstory` 和 `crews/ask.py` 的 `answer_task.description`

### 出题助手 (quiz_crafter)

- **角色**：出题助手（教学助手的 affiliate）
- **做的事**：根据指定主题和用户画像，生成格式规范的检测题目，输出 `￥标签` 格式纯文本
- **工具**：`ProfileGetTool`（读画像）、`KnowledgeSearchTool`（查知识库）
- **只在 `/gen exercise` 时启用**。和 teacher 不同：QuizCrafter 专责出题，teacher 做分析指导

### 审核助手 (reviewer)

- **角色**：教研审核员
- **做的事**：检查生成内容的准确性、难度匹配、结构完整、表述清晰
- **工具**：`ReportIssueTool`（上报问题到 runtime/logs/review_log.jsonl）、`WithdrawOutputTool`（撤回/拦截输出）
- **只在 `/gen` 时启用**。发现严重事实错误或不当内容时调用 WithdrawOutputTool 阻止展示给用户

---

## 数据库层

### 接口设计 (`db/interface.py`)

```python
class StorageBackend(ABC):
    search_knowledge(query, n_results) -> list[str]    # 知识库检索
    get_profile(user_id) -> str                        # 读画像
    update_profile(user_id, profile_text) -> None      # 写画像
    save_conversation(record: ConversationRecord)       # 存对话
    get_recent_conversations(user_id, session_id, turn, n) -> list[ConversationRecord]
    search_conversations(user_id, query, n_results) -> list[str]

@dataclass
class ConversationRecord:
    user_id: str
    session_id: str
    turn: int
    question: str
    answer_summary: str       # 压缩摘要（约 300 字）
    answer_full: str          # 完整回答
    topics: list[str]
    timestamp: str
```

### 当前实现 (`db/vector_store.py`)

`ChromaDBStorage` 实现了 `StorageBackend`，使用三个 ChromaDB collection：

| Collection | 用途 | Key/ID 格式 | 内容 |
|-----------|------|-----------|------|
| `knowledge_base` | 知识文档 | `"{filename}_{chunk_index}"` | 按 `\n\n` 切分的段落文本 |
| `user_profiles` | 用户画像 | `"user_{user_id}"` | 纯文本画像 |
| `conversations` | 对话记忆 | `"{user_id}_{session_id}_{turn:04d}"` | 压缩摘要（向量化）+ 元数据 |
| `question_bank` | 题库 | `"qb_{uuid8}"` | `￥标签` 格式题目文本 + metadata（topic/type/source） |

### 题库管理

### 题库管理

`question_bank` 存储格式规范的检测题目。每条记录包含 `￥标签` 格式的完整题目文本和 metadata（topic、type、knowledge_point、difficulty、source）。

题目来源：
- **导入**：`python_exam_bank.md` → 210 道 Python 题目已入库（通过 `scripts/data/import_exam_bank.py`）
- **生成**：`/gen exercise` → QuizCrafter agent 出题 → 前端编辑 → 点"保存到题库"

API 端点：
- `GET /api/question-bank/topics` — 列出所有题库主题
- `GET /api/question-bank/{topic}` — 获取某个主题的全部题目
- `POST /api/question-bank/save` — 保存题目到题库

### 换数据库

1. 新建 `db/sql_store.py`，实现 `StorageBackend`
2. 改 `db/vector_store.py` 中 `get_store()` 返回新实现
3. 上层代码（tools、agents、crews、main.py）完全不动

---

## 业务逻辑层 (`core/`)

`core/` 是项目的 SDK 层，封装了所有可复用的业务逻辑，CLI、Streamlit 和 API 都调用它。

### CrewRunner (`core/runner.py`)

```python
runner = CrewRunner()
result = runner.run(crew, on_chunk=lambda c: print(c, end="", flush=True))
# result.raw     → 拼接后的完整文本
# result.metrics → crew.usage_metrics（Token 用量）
```

### CrewPipeline (`core/pipeline.py`)

统一执行管线，封装 ReviewContext 注入、Crew 执行、撤回检查、记忆保存四步：

```python
pipeline = CrewPipeline(reviewer, memory)
result = pipeline.execute(crew,
    session_id=sid, turn=n, question=q,
    runner=runner, on_chunk=cb)
# result.withdrawn → bool  是否被审核撤回
# result.reason    → str   撤回原因
# result.raw       → str   输出文本
# result.metrics   →  Token 用量
```

### SessionManager (`core/session.py`)

```python
session = SessionManager()
session.create()         # → "20260712-143052"
session.next_turn()      # → 1, 2, 3, ...
session.session_id       # 当前 session ID
session.turn             # 当前轮次
```

### MemoryManager (`core/memory.py`)

向下兼容委托，内部组合三个子模块：

| 子模块 | 类 | 职责 |
|--------|------|------|
| `conversation_memory.py` | ConversationMemory | 对话压缩、上下文格式化、存取 |
| `path_store.py` | PathStore | 学习路径 CRUD |
| `assessment_store.py` | AssessmentStore | 评估结果存取 |

新增便捷方法：`get_next_turn(session_id)`、`get_profile_text()`

### 解析与评估 (`core/parsing.py` / `core/assessment_flow.py`)

```python
from core.parsing import _extract_json, parse_resource
from core.assessment_flow import parse_answers, generate_assessment_report
```

- `_extract_json(raw)` — 从 LLM 输出中提取第一个有效 JSON，跳过工具调用记录，内置 `json-repair` 修复未转义引号等常见 LLM 输出问题
- `parse_resource(rtype, raw)` — 按 document/mindmap/exercise/ppt 类型解析并生成文件
- `parse_answers(items, user_inputs)` — 将用户答题输入映射为标准答案格式
- `generate_assessment_report(teacher, exercise_json, answers_json, profile_text, tools)` — 调用分析 Crew 并返回 AssessmentResult

---

## 对话记忆

对话记忆的存取由 `core/memory.py` 的 `MemoryManager` 统一管理，`main.py` 只需调用两个方法：

```python
ctx = memory.get_context(session_id, turn)    # 执行前：拿上下文
memory.save_turn(session_id, turn, q, ans)    # 执行后：存记忆
```

内部流程：

### 写入 (`save_turn`)

1. `MemoryManager.compress()` 取回答前 300 字，在句号处截断，得到摘要
2. 构造 `ConversationRecord`，调用 `store.save_conversation(record)`
3. ChromaDB 将 `search_text`（`问：{question}\n答：{summary}`）向量化存储，metadata 中保存完整字段

### 读取 (`get_context`)

1. 调用 `store.get_recent_conversations(user_id, session_id, current_turn, n=5)`
2. 按 ID 格式 `{user_id}_{session_id}_{0001}` ~ `{turn-1:04d}` 依次 get
3. 取最近 5 条存在的记录，按时间正序排列
4. `MemoryManager.format_context()` 格式化为 `用户：{question}\n助手：{summary}` 文本

### 跨 session 检索

`store.search_conversations(user_id, query)` 做向量语义搜索，可召回历史 session 中的相关讨论。当前未在主流程中启用，预留接口。

---

## 用户画像

### 存储

- ChromaDB `user_profiles` collection
- Key 格式：`"user_{user_id}"`，如 `"user_default"` 或 `"user_yao"`
- 内容：一段纯文本，每行一个字段

### 更新机制

画像助手（profile agent）在每轮 `/ask` 时自动执行：

1. `ProfileGetTool` 从 ChromaDB 读当前画像
2. LLM 分析当前问题 + 对话历史上下文
3. 融合新旧信息，输出新画像文本
4. `ProfileUpdateTool` 写回 ChromaDB

### 字段

| 字段 | 含义 | 由谁更新 |
|------|------|---------|
| 学习阶段 | 入门/进阶/高级 | 画像 Agent（暂留，后续移交效果评估模块） |
| 关注学科 | 正在学的科目 | 画像 Agent（同上） |
| 薄弱环节 | 当前掌握不足的知识点 | 画像 Agent（同上） |
| 学习偏好 | 喜欢的教学方式 | 画像 Agent |
| 语言风格 | 简洁/详细、严肃/幽默等 | 画像 Agent |

### 多用户

CLI 启动时传 `--user <name>`，画像 key 自动隔离。不同用户互不干扰。

---

## 配置说明

### `.env`

```
MODEL=deepseek-v4-flash
DEEPSEEK_API_KEY=sk-xxxxxxxx
```

换模型：改 `MODEL` 和 `DEEPSEEK_API_KEY`，以及 `config.py` 中的 `provider`。

### `config.py`

```python
MODEL_LLM = {"provider": "deepseek", "model": os.getenv("MODEL", "deepseek-v4-flash")}
```

换供应商（如 OpenAI）：改为 `{"provider": "openai", "model": "gpt-4o"}`，同时设 `OPENAI_API_KEY` 环境变量。

### Embedding 模型

ChromaDB 内置 `all-MiniLM-L6-v2`，80MB，384 维。在 `db/vector_store.py` 的 `_get_client()` 中可通过 `embedding_function` 参数替换。

---

## 如何修改

### 调整 Agent 行为

改 `agents/<name>.py` 中的 `role`、`goal`、`backstory`。这三个字段会被 CrewAI 注入到 LLM 的 system prompt 中。

### 调整 Task 执行逻辑

改 `crews/<command>.py` 中的 `Task(description=...)`。description 是给 LLM 的指令，写得越具体效果越好。

### 加新工具

1. 在 `tools/` 下新建文件，继承 `BaseTool`
2. 实现 `_run()` 方法
3. 在 `tools/registry.py` 的 `get_tools()` 中按资源类型注册（不要直接改 Agent 的 tools 参数）

### 加知识文档

1. 放 `.txt` 文件到 `knowledge/` 目录
2. 删除 `runtime/chroma_data/` 或手动清空 `knowledge_base` collection
3. 重新启动，自动索引

### 加新 Agent

1. 在 `agents/` 下新建文件，写 `create_xxx_agent()` 函数
2. 在 `agents/__init__.py` 中 import 并加入 `create_agents()`
3. 在 `crews/` 中用到新 Agent 的 Task

### 加新命令

1. 在 `crews/` 下新建或复用 Crew 构建函数
2. 在 `main.py` 的 while 循环中加 `elif raw.startswith("/xxx")` 分支

---

## 工作日志

项目开发和变更记录存放在 `report/` 目录下：

| 文件 | 内容 |
|------|------|
| `report/01_GIT_HISTORY.md` | 完整 Git 提交历史（2026-07-10 ~ 至今） |
| `report/02_SESSION_LOG_2026-07-14.md` | 2026-07-14 工作日志：Bug 修复、API 对齐、新功能 |
| `report/03_API_ENDPOINT_AUDIT.md` | API 端点审计：response_model 修复前后对比 |
| `report/04_HANDOFF.md` | 前端交接文档：架构概述、当前状态、已知问题 |
| `report/05_FRONTEND_BACKEND_AUDIT.md` | 前后端对齐审计 |
| `report/06_FRONTEND_FULL_AUDIT.md` | 前端全量审计 |
| `report/07_FINAL_REPORT.md` | 前端重构终态报告 |
| `report/08_CODE_AUDIT_2026-07-14.md` | 全栈代码审计：问题清单 + 重构路线图 |
| `report/09_ASSESSMENT_REFACTOR_2026-07-15.md` | 评估功能重构：agent 出题 + ￥标签格式 + 题库存储 |
| `report/10_TEMPLATE_AND_PATH_2026-07-15.md` | 模板格式标准化（document/PPT）+ 学习路径与资源生成联通 + MiMo 切换 |
| `report/11_PATH_NODE_NAV_2026-07-16.md` | 节点跳转修复：路径 ￥节点 重构、mindmap .md 输出、前端资源加载、下载修复、￥标签 标准化指南 |
| `../guidelines/YEN_TAG_STANDARD.md` | ￥标签 输出格式标准化规范（正则 + 解析器 + 降级策略 + 反模式） |

---

## 常见问题

### Windows 控制台乱码

`main.py` 开头已处理 UTF-8 编码。如果仍有问题，检查终端是否支持 UTF-8（推荐 Windows Terminal）。

### DeepSeek API 报错

- `ConnectionResetError 10054`：网络波动，重试即可
- `structured output not supported`：确认 agents 中 `reasoning=True` 已注释掉

### 知识库检索结果不相关

`all-MiniLM-L6-v2` 以英文训练为主，中文语义匹配偏弱。可替换为 `BAAI/bge-large-zh-v1.5` 等中文模型。

### 画像格式混乱

问题在 `crews/ask.py` 的 `profile_task.description`，改输出格式约束即可。当前格式要求每行一个字段，不要用 `【】` 标记。
