# Industrial Maintenance Agent Platform

> **English version:** [README.en.md](README.en.md)

面向 **AI 应用开发 / 大模型应用开发 / RAG & Agent 实习岗位** 的工程化 Demo。项目模拟工业设备维护场景：上传设备手册 PDF 后，系统将文档切块、向量化并写入 **PostgreSQL + pgvector**；用户提问时由 **LangGraph Agent** 调用 RAG 检索工具、文档结构工具和设备健康预测 Tool，最终输出有证据来源、可调试 trace 的维护问答或风险分析结果。

一句话概括：这是一个可本地部署的 **Industrial Maintenance Agent Platform**，把“设备手册问答”和“传感器健康预测”编排到同一个 Agent 工作流里。

## 30 秒看懂项目价值

| 招聘视角 | 项目体现 |
| --- | --- |
| RAG 应用能力 | PDF 解析、chunking、embedding、pgvector 持久化检索、sources / confidence 输出 |
| Agent 能力 | LangGraph 状态图，支持 planner、tool calling、evaluator、多轮追问和 debug trace |
| 后端工程能力 | FastAPI REST API、JWT 鉴权、PostgreSQL ORM、Redis 限流、Docker Compose 本地部署 |
| 工业场景理解 | 维护手册检索 + 设备传感器风险预测 + 高风险动作确认 |
| 测试与评估意识 | pytest 离线单测、smoke test、RAGAS 与 retrieval evaluation 脚本 |

项目定位不是线上决策系统，而是一个 **工程化 Demo / 可本地部署的 AI 应用系统**。README 中不写未经验证的效果数字；v1/v2 检索差异通过同一评估集复现实验。

## 技术栈

| 模块 | 技术 |
| --- | --- |
| API 后端 | **FastAPI**、Uvicorn、Pydantic |
| Agent 编排 | **LangGraph**、LangChain tool calling |
| RAG 检索 | **PostgreSQL + pgvector**、FAISS baseline / fallback、BM25、rerank |
| 数据存储 | PostgreSQL、SQLAlchemy、Alembic |
| 缓存与限流 | **Redis**，用于 chat 接口用户级限流 |
| LLM / Embedding | DashScope OpenAI-compatible API，支持本地 OpenAI-compatible / Ollama 占位接入 |
| 工业预测 Tool | sibling repo: `predictive-maintenance-mini`，FastAPI `:8010` |
| 测试与评估 | **pytest**、smoke test、RAGAS、retrieval golden set |
| 部署 | **Docker Compose**，包含 API、PostgreSQL + pgvector、Redis |
| UI | Streamlit，用于上传 PDF、问答、Debug Trace 和设备健康预测演示 |

## 系统架构

```text
PDF 手册上传
    |
    v
pypdf 解析 -> chunking -> embedding
    |
    v
PostgreSQL + pgvector
documents / chunks / chunk_embeddings / qa_logs
    |
    +----------------------------+
    |                            |
    v                            v
POST /ask/                 POST /agent/invoke
通用 Agentic RAG            工业运维 Agent
    |                            |
    v                            v
LangGraph                 classify_intent
planner                   -> retrieve_manual
-> agent/tool calling      -> check_machine_health
-> evaluator loop          -> generate_maintenance_plan
-> answer                  -> human confirmation
    |                            |
    +-------------+--------------+
                  |
                  v
Tool: check_machine_health
HTTP POST {HEALTH_API_URL}/predict
                  |
                  v
predictive-maintenance-mini (:8010)
```

Docker Compose 会启动：

- `rag-agentic-system`，FastAPI 后端，默认 `http://127.0.0.1:8000`
- `postgres`，`pgvector/pgvector:pg16`，保存文档、chunks、embeddings 和 QA 日志
- `redis`，用于 `/ask/` 与 `/ask_rag/` 的用户级限流

## 核心能力

| 能力 | 说明 |
| --- | --- |
| PDF 知识库构建 | 支持单文件和批量 PDF 上传，校验 PDF 文件头，解析后切块并入库 |
| 持久化向量库 | chunks 和 embeddings 写入 PostgreSQL + pgvector，服务重启后可继续检索 |
| Agentic RAG | `/ask/` 默认走 LangGraph Agent，可调用 `retrieve_chunks`、`list_headings`、`count_tables`、`check_machine_health` |
| 经典 RAG baseline | `/ask_rag/` 提供“检索 -> Prompt -> 生成”的对照链路 |
| Hybrid Retrieval | v2 支持 pgvector dense retrieval + BM25 keyword retrieval + fusion + optional rerank |
| 设备健康 Tool | Agent 通过 HTTP 调用 `predictive-maintenance-mini` 的 `/predict`，将传感器数据转成风险判断 |
| 多轮上下文 | 请求体 `history` 保留最近 3 轮，`session_id` 可持久化聊天记录 |
| 可观测调试 | `debug=true` 返回 `tool_trace`、`retrieved_evidence_preview`、`reasoning_snapshot` |
| 运维动作确认 | `/agent/invoke` 对高风险结果返回 `confirmation_required`，确认后 `/agent/confirm` 才创建 mock ticket |

## Agent 工作流

### 1. 通用 Agentic RAG: `POST /ask/`

`/ask/` 适合“围绕上传手册提问，必要时结合传感器数据判断设备状态”的场景。LangGraph 状态图在 [app/agent/graph.py](app/agent/graph.py) 中定义：

```text
START
  -> planner
  -> agent
  -> tools?            # 如模型决定调用工具
  -> evaluator
  -> agent?            # 需要补充检索或处理子问题时循环
  -> answer
  -> END
```

可用工具在 [app/agent/nodes.py](app/agent/nodes.py) 中定义：

- `retrieve_chunks(query)`：从当前知识库检索相关片段
- `list_headings()`：提取文档章节 / 小节标题
- `count_tables()`：粗略统计表格迹象
- `check_machine_health(sensor_data)`：调用设备健康预测服务

工作流特点：

- planner 会识别多跳问题并生成子问题
- evaluator 会根据证据决定是否继续检索
- 文档类追问优先再次检索，避免只依赖上一轮回答
- `debug=true` 时可看到工具调用轨迹、证据预览和推理快照

### 2. 工业运维 Agent: `POST /agent/invoke`

`/agent/*` 是专门面向 Industrial Maintenance 的状态图，在 [app/agents/maintenance_agent/graph.py](app/agents/maintenance_agent/graph.py) 中定义：

```text
START
  -> classify_intent
  -> retrieve_manual_node?       # 需要查手册时
  -> check_health_node?          # 有设备 / 传感器 / 风险意图时
  -> generate_plan_node
  -> require_confirmation_node?  # high / critical 风险时
  -> create_ticket_node?         # 用户确认后
  -> final_response_node
  -> END
```

它更像一个维护流程编排器：

- 根据问题判断是否需要手册检索、健康预测或直接生成维护建议
- 默认使用 `retriever_version="v2"` 和 `use_rerank=true`
- 对 high / critical 风险不会直接创建工单，而是返回 `trace_id` 等待 `/agent/confirm`
- 每个节点通过 `AgentTraceRecorder` 记录结构化 trace，便于排查 Agent 分支和工具耗时

## 核心接口

大部分业务接口需要 Bearer token。先注册并登录：

```bash
curl -X POST "http://127.0.0.1:8000/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@example.com","password":"password123"}'

curl -X POST "http://127.0.0.1:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@example.com","password":"password123"}'
```

把登录响应中的 `access_token` 放到请求头：

```bash
export TOKEN="<access_token>"
```

| method | path | description | auth required | main response fields |
| --- | --- | --- | --- | --- |
| `POST` | `/auth/register` | 注册新用户，创建本地账号。 | No | `id`, `email`, `is_active`, `created_at` |
| `POST` | `/auth/login` | 用户登录，返回后续业务接口使用的 Bearer token。 | No | `access_token`, `token_type` |
| `POST` | `/documents/upload` | 文档上传接口名；当前代码实现路径为 `POST /upload_pdf/`，用于上传单个 PDF 并构建知识库。 | Yes | `knowledge_base_id`, `collection_id`, `status`, `message`, `chunks_count`, `filename` |
| `DELETE` | `/documents/{document_id}` | 删除当前用户的文档，并级联删除 chunks 与 embeddings。 | Yes | `document_id`, `deleted`, `chunks_deleted`, `embeddings_deleted` |
| `POST` | `/ask` 或 `/chat` | Agentic RAG 问答入口；当前代码实现路径为 `POST /ask/`，支持 `retriever_version`, `top_k`, `use_rerank`, `history`, `debug`。 | Yes | `answer`, `confidence`, `sources`, `knowledge_base_id`, `session_id`, `history`, `debug`, `mode` |
| `POST` | `/ask/stream` | 通用问答流式接口规划项；当前代码尚未暴露该路由，已有流式能力在 `POST /agent/stream`。 | Yes | SSE events: `delta` / `tool_trace` / `final_answer` / `error` |
| `POST` | `/agent/invoke` | 工业运维 Agent 普通调用：手册检索、健康预测、维护计划生成和高风险确认判断。 | Yes | `final_answer`, `risk_level`, `tools_used`, `sources`, `trace_id`, `confidence`, `maintenance_plan`, `confirmation_required`, `recommended_action`, `decision`, `debug` |
| `POST` | `/agent/stream` | 工业运维 Agent SSE 流式调用，逐步返回 intent、tool、risk 和 final answer 事件。 | Yes | SSE events: `intent_classified`, `tool_started`, `tool_finished`, `risk_checked`, `final_answer`, `error` |
| `POST` | `/agent/confirm` | 对 high / critical 风险场景下的维护动作进行确认或拒绝，确认后才创建 mock ticket。 | Yes | `trace_id`, `decision`, `confirmation_required`, `recommended_action`, `risk_level`, `ticket`, `tools_used`, `sources`, `session_id`, `final_answer` |
| `POST` | `/feedback` | 用户反馈接口规划项；当前代码尚未暴露该路由，可用于后续记录 answer quality、thumbs up/down 和人工标注。 | Yes | `feedback_id`, `status`, `message` |
| `POST` | `predictive service /predict` | `predictive-maintenance-mini` 单条传感器样本推理接口，本系统 Tool 通过 `HEALTH_API_URL` 调用。 | No | `prediction`, `risk_level`, `risk_score`, `recommendation`, `probabilities`, `trigger_reasons`, `recommended_actions`, `model_version` |
| `POST` | `predictive service /predict-batch` | `predictive-maintenance-mini` 批量传感器样本推理接口。 | No | `results`, `total`, `model_version` |

### 上传 PDF

```bash
curl -X POST "http://127.0.0.1:8000/upload_pdf/" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@test.pdf"
```

响应字段：

```json
{
  "knowledge_base_id": "uuid",
  "collection_id": "uuid-or-null",
  "status": "success",
  "message": "知识库构建成功，包含 N 个文本块",
  "chunks_count": 83,
  "filename": "test.pdf"
}
```

### Agentic RAG 问答

```bash
curl -X POST "http://127.0.0.1:8000/ask/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "这份维护手册中关于报警处理的建议是什么？",
    "knowledge_base_id": "<knowledge_base_id>",
    "retriever_version": "v2",
    "top_k": 5,
    "use_rerank": true,
    "history": [],
    "debug": true
  }'
```

关键请求字段：

| 字段 | 说明 |
| --- | --- |
| `question` | 用户问题 |
| `knowledge_base_id` | 上传 PDF 后返回的知识库 / 文档 ID |
| `document_id` | 可选；未传时会自动等于 `knowledge_base_id` |
| `collection_id` | 可选；用于限定集合 |
| `retriever_version` | `v1` 或 `v2` |
| `top_k` | 返回候选片段数量 |
| `use_rerank` | v2 下是否启用 rerank |
| `history` | 多轮历史，服务端最多使用最近 3 轮 |
| `debug` | 是否返回工具 trace 和推理快照 |

### 经典 RAG baseline

```bash
curl -X POST "http://127.0.0.1:8000/ask_rag/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "这份文档主要讲什么？",
    "knowledge_base_id": "<knowledge_base_id>",
    "retriever_version": "v1",
    "history": []
  }'
```

`/ask_rag/` 不走 LangGraph 工具循环，适合和 `/ask/` 对照演示。

### 检索接口

```bash
curl -X POST "http://127.0.0.1:8000/documents/retrieve" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "主轴异常振动如何检查？",
    "document_id": "<knowledge_base_id>",
    "retriever_version": "v2",
    "limit": 5,
    "use_rerank": true
  }'
```

响应中的 chunk 会包含 `score`，v2 下可能包含 `dense_score`、`bm25_score`、`final_score`、`rerank_score` 和 `source_metadata`。

### 工业运维 Agent

```bash
curl -X POST "http://127.0.0.1:8000/agent/invoke" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "user_input": "请查询维护手册并检查这台设备的风险",
    "machine_id": "MACHINE-001",
    "knowledge_base_id": "<knowledge_base_id>",
    "retriever_version": "v2",
    "top_k": 5,
    "use_rerank": true,
    "sensor_data": {
      "temperature": 75,
      "pressure": 1.2,
      "vibration": 0.6,
      "speed": 118,
      "humidity": 48
    },
    "confirm_create_ticket": false
  }'
```

若返回 `confirmation_required=true`，使用 `trace_id` 确认或拒绝：

```bash
curl -X POST "http://127.0.0.1:8000/agent/confirm" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "trace_id": "<trace_id>",
    "decision": "confirmed"
  }'
```

## 本地启动方式

### 方式 A：Docker Compose 启动后端、PostgreSQL、Redis

适合面试官或 HR 本地快速复现 API。

```bash
git clone https://github.com/ShihangPENg-afk/rag-agentic-system.git
cd rag-agentic-system

make env-init
# 编辑 .env，至少配置 DASHSCOPE_API_KEY、POSTGRES_USER、POSTGRES_PASSWORD、JWT_SECRET_KEY

make docker-up
```

访问：

- API: `http://127.0.0.1:8000`
- Swagger: `http://127.0.0.1:8000/docs`
- PostgreSQL: `localhost:5432`
- Redis: `localhost:6379`

查看日志或停止服务：

```bash
make docker-logs
make docker-down
```

### 方式 B：本地 Python 启动 FastAPI

适合开发调试。PostgreSQL 和 Redis 可先由 Docker Compose 单独启动：

```bash
make install
make env-init
# 编辑 .env

docker compose up postgres redis -d
make run
```

等价启动命令：

```bash
source .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Streamlit UI

UI 不直接访问数据库，通过 HTTP 调 FastAPI 和健康预测服务：

```bash
source .venv/bin/activate
pip install -r ui/requirements-ui.txt
export API_BASE_URL=http://127.0.0.1:8000
export HEALTH_API_URL=http://127.0.0.1:8010
make ui
```

默认访问 `http://127.0.0.1:8501`。

## predictive-maintenance-mini 如何作为 Tool 服务

`predictive-maintenance-mini` 是独立仓库，负责工业设备健康预测 API。本仓库不直接导入它的代码，而是通过 HTTP 调用它的服务，因此两个项目可以独立启动、测试和替换。

推荐目录结构：

```text
pythonProject1/
  rag-agentic-system/
  predictive-maintenance-mini/
```

启动预测服务：

```bash
cd ../predictive-maintenance-mini
make docker-up
make docker-verify
```

预测服务默认端口为 `8010`，核心接口：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/health` | 预测服务健康检查 |
| `GET` | `/model-info` | 查询模型和特征字段 |
| `POST` | `/predict` | 输入传感器特征，返回 `prediction`、`risk_level` 等 |

本仓库通过环境变量连接：

```env
HEALTH_API_URL=http://127.0.0.1:8010
HEALTH_API_TIMEOUT=5
MAINTENANCE_HEALTH_PROVIDER=http
```

Tool 调用边界：

- `/ask/` 中的 `check_machine_health(sensor_data)` 会请求 `POST {HEALTH_API_URL}/predict`
- `/agent/invoke` 中的 `check_health_node` 会优先调用同一预测服务，并将结果标准化为 `prediction`、`risk_level`、`risk_score`、`trigger_reasons`、`recommended_actions`
- Streamlit 的“设备健康预测”Tab 可以直接调用 `predictive-maintenance-mini`
- 如果预测服务未启动或超时，工业运维 Agent 会走 deterministic mock fallback，保证 Agent 流程可演示；这不代表真实模型效果

双服务联动：

```bash
cd rag-agentic-system
make stack-up
make stack-verify
```

`make stack-up` 默认要求 `../predictive-maintenance-mini` 存在。

## v1 FAISS/pgvector baseline vs v2 hybrid + rerank

项目中 `retriever_version` 用于切换检索策略。为了和代码一致，v1 这里拆成两层来理解：

- `pgvector` dense retrieval 是当前的持久化 baseline
- `FAISS` 是更早期的进程内兼容 fallback

也就是说，`/ask/` 的 v1 路径本质上是“单路 dense 检索 + 兼容回退”，而 v2 才是“多路召回 + rerank”。这里不写固定效果数字，真实效果应通过 `evals/golden_questions.jsonl` 在同一批文档上复现。

| 版本 | 实现 | 特点 | 适合演示 |
| --- | --- | --- | --- |
| v1 FAISS baseline | [app/retrievers/retriever_v1_faiss.py](app/retrievers/retriever_v1_faiss.py) | 早期进程内向量索引，服务重启后需要重新构建；当前作为兼容 fallback 保留 | 说明 RAG 最小闭环和向量检索 baseline |
| v1 pgvector baseline | [app/retrievers/retriever_v2_pgvector.py](app/retrievers/retriever_v2_pgvector.py) | 单路 dense retrieval，按 `user_id`、`document_id`、`collection_id` 过滤，向量持久化在 PostgreSQL | 说明从内存索引升级到持久化知识库 |
| v2 hybrid | [app/retrievers/retriever_v2_hybrid.py](app/retrievers/retriever_v2_hybrid.py) | pgvector dense retrieval + BM25 keyword retrieval，并用 RRF 或 weighted fusion 合并候选 | 适合报警码、零件名、维护动作等关键词和语义混合问题 |
| v2 hybrid + rerank | `use_rerank=true` + [app/retrievers/rerank.py](app/retrievers/rerank.py) | 对 hybrid 候选做二次排序，输出 `rerank_score`；默认 `RERANK_PROVIDER=mock`，便于离线测试 | 说明可插拔 reranker 位置和评估方式 |

实际调用示例：

```json
{
  "retriever_version": "v1",
  "use_rerank": false
}
```

```json
{
  "retriever_version": "v2",
  "use_rerank": true
}
```

检索评估脚本：

```bash
EVAL_USER_ID=<user_id> python3 evals/evaluate_retrieval.py --top-k 5

EVAL_USER_ID=<user_id> python3 evals/evaluate_retrieval.py \
  --document-id <document_id> \
  --top-k 5 \
  --use-rerank
```

输出文件：

- `evals/results_v1.json`
- `evals/results_v2.json`
- `evals/report_v1_vs_v2.md`

## RAG vs LoRA 边界

本仓库主线是 RAG + Agent，不把 LoRA 结果包装成已接入能力。

| 方向 | 本项目边界 |
| --- | --- |
| RAG | 负责动态知识接入：上传 PDF、切块、embedding、检索、引用 sources。设备手册更新时，优先更新知识库，不需要重训模型 |
| Agent | 负责任务编排：判断问题意图、选择工具、汇总证据、输出维护建议或确认动作 |
| LoRA | 适合优化模型回答风格、领域术语表达和固定输出格式，例如“现象 -> 风险 -> 原因 -> 检查步骤 -> 建议” |
| 当前状态 | `llm-finetune-for-manufacturing` 是独立 LoRA 实验仓库，尚未接入本仓库的默认问答链路 |

预留接入方式：

- `LLM_PROVIDER=dashscope`：当前默认
- `LLM_PROVIDER=local`：接 OpenAI-compatible 本地模型服务
- `OLLAMA_BASE_URL` / `OLLAMA_MODEL`：本地 Ollama 示例路径
- `LOCAL_LLM_MOCK=true`：无真实模型时验证流程

如果未来接入 LoRA adapter，需要在同一评估集上比较：

- `RAG + 云端模型`
- `RAG + 本地基座模型`
- `RAG + LoRA 模型`

只有通过同一套评估和人工样例验证后，才应声明效果变化。

## 测试与评估

离线单元测试，不需要 DashScope Key：

```bash
make test
# 等价于：PYTHONPATH=. .venv/bin/python -m pytest tests/ -v
```

端到端 smoke test，需要后端已启动且 `.env` 配置可用：

```bash
make smoke
make smoke BASE_URL=http://127.0.0.1:8000 PDF=test.pdf
```

RAGAS 回答质量评估：

```bash
make eval-ragas
make eval-ragas RAGAS_LIMIT=3 RAGAS_METRICS=all RAGAS_TIMEOUT=600
```

检索质量评估：

```bash
EVAL_USER_ID=<user_id> python3 evals/evaluate_retrieval.py --top-k 5
```

## 重要配置

`.env.example` 提供占位配置，真实 key 不应提交到仓库。

```env
DASHSCOPE_API_KEY=your_dashscope_api_key_here
LLM_PROVIDER=dashscope
MODEL_NAME=qwen-plus

EMBEDDING_PROVIDER=dashscope
EMBEDDING_MODEL_NAME=text-embedding-v1
RERANK_PROVIDER=mock

POSTGRES_USER=rag_agent_user
POSTGRES_PASSWORD=change-me
POSTGRES_DB=rag_agent_db
DATABASE_URL=postgresql+psycopg2://rag_agent_user:change-me@localhost:5432/rag_agent_db

REDIS_URL=redis://localhost:6379/0

HEALTH_API_URL=http://127.0.0.1:8010
HEALTH_API_TIMEOUT=5
MAINTENANCE_HEALTH_PROVIDER=http

JWT_SECRET_KEY=change-me-for-local-demo
```

离线测试 embedding 可设置：

```env
EMBEDDING_PROVIDER=fake
LOCAL_LLM_MOCK=true
```

## 关联仓库

| 仓库 | 说明 |
| --- | --- |
| [rag-agentic-system](https://github.com/ShihangPENg-afk/rag-agentic-system) | 本仓库：Industrial Maintenance Agent Platform |
| [predictive-maintenance-mini](https://github.com/ShihangPENg-afk/predictive-maintenance-mini) | 工业设备健康预测 Tool 服务，FastAPI `:8010` |
| [llm-finetune-for-manufacturing](https://github.com/ShihangPENg-afk/llm-finetune-for-manufacturing) | LoRA 微调实验，当前未接入本仓库默认链路 |

## 项目结构

```text
rag-agentic-system/
├── app/
│   ├── api/                         # FastAPI 路由
│   ├── agent/                       # /ask/ 通用 LangGraph Agentic RAG
│   ├── agents/maintenance_agent/    # /agent/* 工业运维 Agent
│   ├── db/                          # 数据库连接与初始化
│   ├── models/                      # SQLAlchemy models
│   ├── repositories/                # PostgreSQL repository
│   ├── retrievers/                  # FAISS / pgvector / hybrid / rerank
│   ├── services/                    # 上传、索引、LLM、Agent service
│   └── tools/                       # Agent tools
├── ui/
│   └── streamlit_app.py             # Streamlit 演示 UI
├── evals/
│   ├── evaluate_retrieval.py        # v1/v2 检索评估
│   ├── golden_questions.jsonl       # 检索评估集
│   └── run_ragas_eval.py            # RAGAS 评估脚本
├── tests/
│   └── test_offline.py              # 离线 pytest 单测
├── scripts/
│   ├── smoke_test.sh                # 端到端冒烟
│   ├── start_stack.sh               # 双服务启动
│   └── verify_health_stack.sh       # 8000 + 8010 联动检查
├── docker-compose.yml               # API + PostgreSQL + Redis
├── Dockerfile
├── Makefile
└── README.md
```

## 常用命令

```bash
make help
make install
make run
make docker-up
make docker-logs
make docker-down
make ui
make test
make smoke
make eval-ragas
make stack-up
make stack-verify
```

## 进一步阅读

- [docs/architecture.md](docs/architecture.md)
- [docs/industrial_demo_guide.md](docs/industrial_demo_guide.md)
- [docs/ui_demo_guide.md](docs/ui_demo_guide.md)
- [docs/rag_vs_lora.md](docs/rag_vs_lora.md)
- [evals/report_v1_vs_v2.md](evals/report_v1_vs_v2.md)

## License

本项目采用 [MIT License](LICENSE) 开源。
