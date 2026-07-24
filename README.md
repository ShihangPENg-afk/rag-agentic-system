# rag-agentic-system

> **English version:** [README.en.md](README.en.md)

基于 **Agentic RAG** 的 PDF 智能问答系统，并集成 **工业设备健康预测** 能力：上传 PDF 后自动切块、向量化并写入 PostgreSQL + pgvector 持久化向量库，通过 LangGraph Agent 进行工具调用、多步推理与对话记忆；同时通过 `check_machine_health` 工具 HTTP 调用独立工业预测服务，实现「文档问答 + 传感器风险预测」双链路编排。

项目覆盖 **Web API（FastAPI）**、**Streamlit 前端**、**PostgreSQL 结构化日志**、**Docker 部署**、**RAGAS 离线评估** 与 **双服务联动验收**，可作为 RAG + Agent + 工业场景 AI 的工程化 POC 展示。

详细架构见 [docs/architecture.md](docs/architecture.md)；工业联动演示见 [docs/industrial_demo_guide.md](docs/industrial_demo_guide.md)。

---

## 关联 GitHub 仓库

| 仓库 | GitHub | 说明 |
|------|--------|------|
| **rag-agentic-system** | https://github.com/ShihangPENg-afk/rag-agentic-system | 本仓库：Agentic RAG、Streamlit、PostgreSQL |
| **predictive-maintenance-mini** | https://github.com/ShihangPENg-afk/predictive-maintenance-mini | 工业 ML 训练与推理 API（`:8010`） |
| **llm-finetune-for-manufacturing** | https://github.com/ShihangPENg-afk/llm-finetune-for-manufacturing | LoRA 微调实验（**尚未接入**本仓库） |

三个仓库**代码与部署相互独立**。本地双服务联调时，请将上述仓库 clone 到**同级目录**（例如 `pythonProject1/rag-agentic-system` 与 `pythonProject1/predictive-maintenance-mini` 并列），详见 [4.1 双服务联动](#41-双服务联动rag-agentic-system--predictive-maintenance-mini)。

---

## 视频演示

完整功能演示视频（PDF 问答、Debug Trace、PostgreSQL 历史、设备健康预测 Tab、Agent 调用 `check_machine_health`）：

| 平台 | 内容 |
|------|------|
| **百度网盘** | 文件 `rag-demo.mp4` · [链接](https://pan.baidu.com/s/1G3FDGbw7h37hDuddjUFpRg) · 提取码 `iqcq` |
| **文字版 Demo（无需视频）** | 海外或无法访问网盘时，请按 [docs/ui_demo_guide.md](docs/ui_demo_guide.md) 与 [docs/industrial_demo_guide.md](docs/industrial_demo_guide.md) 逐步复现 |

> 视频为端到端演示录屏；文字指南与视频覆盖相同能力，适合国际访问者与 CI 环境外的本地验收。

---

## 项目亮点（能力概览）

| 方向 | 实现要点 |
|------|----------|
| **RAG / Agent** | LangGraph 多步推理；`retrieve_chunks` / `list_headings` / `count_tables`；`/ask/` 与经典 RAG `/ask_rag/` 对照 |
| **Web 开发** | FastAPI REST API + Streamlit 宽屏 UI；Debug Trace 四面板可视化 |
| **DevOps** | Docker Compose（API + PostgreSQL）；`make smoke` 四步冒烟；`make stack-up` 双服务栈联动 |
| **RAG 评估** | RAGAS 离线评估（faithfulness **0.875**、answer_relevancy **0.886**，3/10 样本基线） |
| **工业场景 AI** | 联动 [predictive-maintenance-mini](https://github.com/ShihangPENg-afk/predictive-maintenance-mini)（`:8010`）；传感器 → `prediction` / `risk_level` / 运维建议 |
| **Agent 工具集成** | `check_machine_health` 经 HTTP 调工业 `/predict`；`debug.tool_trace` 可观测；与 PDF 问答链路解耦并存 |

**关联独立仓库：**

- **[predictive-maintenance-mini](https://github.com/ShihangPENg-afk/predictive-maintenance-mini)** — EDA、RandomForest 训练、FastAPI 推理、Docker（工业预测）
- **[llm-finetune-for-manufacturing](https://github.com/ShihangPENg-afk/llm-finetune-for-manufacturing)** — PDF → LoRA 微调实验（**尚未接入**本仓库）

---

## 核心功能

| 功能 | 说明 |
|------|------|
| **PDF 上传与文本切块** | 单文件 / 批量上传，校验 `%PDF` 魔数，pypdf 解析后切块、去重 |
| **pgvector 向量检索** | 可配置 embedding provider，默认 DashScope TextEmbedding，PostgreSQL + pgvector 持久化相似度检索 |
| **Agent 工具调用** | LangGraph 驱动，支持 `retrieve_chunks`、`list_headings`、`count_tables`、**`check_machine_health`**（工业预测） |
| **工业预测联动** | Agent 工具 / Streamlit Tab 双入口，HTTP 调用 predictive-maintenance-mini 的 `/predict` |
| **多步推理** | `planner` 拆解子问题，`evaluator` 汇总证据并决定是否继续检索 |
| **对话 Memory** | 请求体传入 `history`，保留最近 3 轮；Agent 将历史摘要注入 system message，检索工具也可利用历史做指代消解 |
| **Debug trace** | `/ask/` 设置 `debug: true`，返回 `tool_trace`、`reasoning_snapshot`、`retrieved_evidence_preview` |
| **Streamlit UI** | 浏览器端上传 PDF、多轮问答、Debug Trace 可视化、历史问答查看、**设备健康预测**（联动 predictive-maintenance-mini） |
| **PostgreSQL + pgvector 持久化** | 文档元信息、chunks、embeddings 与 QA 日志落库；服务重启后无需重新上传即可检索 |
| **Docker 部署** | `Dockerfile` + `docker-compose.yml`（含 PostgreSQL），含 healthcheck |
| **RAGAS 评估** | 离线脚本对 Agent 回答打分，输出 JSON / Markdown 报告 |

**问答入口：**

- `POST /ask/` — LangGraph Agent（默认主路径）
- `POST /ask_rag/` — 经典 RAG 单链路（检索 → Prompt → 生成，用于对照基线）

---

## 技术栈

| 类别 | 技术 |
|------|------|
| Web 框架 | **FastAPI**、Uvicorn |
| 前端 UI | **Streamlit**（`ui/streamlit_app.py`，调用后端 HTTP API） |
| Agent 编排 | **LangGraph**、LangChain OpenAI 兼容接口 |
| 向量检索 | **PostgreSQL + pgvector**（主路径）、FAISS v1 后备、NumPy |
| 元数据 / 日志 | **PostgreSQL 16 + pgvector**、SQLAlchemy（`documents`、`chunks`、`chunk_embeddings`、`qa_logs` 表） |
| 大模型 / 向量 | **DashScope**（`qwen-plus`、TextEmbedding）或 `fake` embedding provider，通过 **OpenAI-compatible API** 调用 |
| 容器化 | **Docker**、**Docker Compose**（`rag-agentic-system` + `postgres`；工业服务见 sibling 仓库） |
| 工业预测（外部） | **[predictive-maintenance-mini](https://github.com/ShihangPENg-afk/predictive-maintenance-mini)**：scikit-learn、FastAPI `:8010`（本仓库通过 HTTP 调用） |
| 质量评估 | **RAGAS**（`Faithfulness`、`ResponseRelevancy`） |
| 文本处理 | pypdf、langchain-text-splitters |

---

## 架构概览

```
上传 PDF → 切块 / 向量化 → PostgreSQL + pgvector（持久化，可重启恢复）
              │                    ↓
              │          POST /ask/（Agent，默认）
              │                    ↓
              │   planner → agent ⇄ tools → evaluator → answer
              │                    ↓
              │    retrieve_chunks / list_headings / count_tables
              │    check_machine_health ──HTTP──► predictive-maintenance-mini :8010
              │                                      POST /predict → risk_level
              ↓
     PostgreSQL collections / documents / chunks / chunk_embeddings
                              ↓
                    qa_logs 表（问答历史 + 可选 debug JSON）

Streamlit UI（:8501）──┬── API_BASE_URL → rag-agentic-system :8000（PDF / 聊天 / Debug）
                       └── HEALTH_API_URL → predictive-maintenance-mini :8010（设备健康 Tab 直连）

                    POST /ask_rag/（经典 RAG，回退）
                              ↓
         历史增强 → pgvector 检索 → Prompt → DashScope 生成
```

**持久化说明：** chunk 文本与 embedding 向量写入 PostgreSQL + pgvector；检索时可按 `user_id`、`document_id`、`collection_id` 过滤，服务重启后无需重新上传即可继续检索。FAISS v1 仍作为进程内后备实现保留。详见 [docs/architecture.md](docs/architecture.md)。

---

## Knowledge Base Persistence

本仓库的主检索路径已经从 FAISS 内存索引升级为 PostgreSQL + pgvector。原因很直接：

- FAISS 是进程内索引，服务重启、滚动发布或多实例部署后，索引状态会丢失或不一致。
- 文档的新增、删除、更新需要事务一致性，pgvector 可以把 `documents`、`chunks`、`chunk_embeddings` 放进同一数据库事务里处理。
- PostgreSQL 天然支持按 `user_id`、`collection_id`、`document_id` 做过滤，适合做多用户知识库隔离。
- 元数据和向量统一落库后，服务重启后无需重新上传文档就能继续检索。

### 表职责

| 表 | 职责 |
|------|------|
| `collections` | 知识库集合，按用户分组和管理多个文档集合。 |
| `documents` | 文档元数据，保存文件名、状态、chunk 数、哈希、创建/更新时间等。 |
| `chunks` | 切分后的文本块，保存 `chunk_index`、正文内容及所属文档 / 集合 / 用户。 |
| `chunk_embeddings` | 每个 chunk 的 embedding 向量，保存向量、模型名、维度及关联 ID。 |

### 服务重启后是否可用

可用。文档上传或更新后，chunks 和 embeddings 会持久化到 PostgreSQL；重启服务后，检索直接读取数据库中的 pgvector 数据，不需要重新上传文档，也不依赖内存里的 FAISS 索引。

### 如何运行验证脚本

```bash
python scripts/verify_pgvector_persistence.py
```

脚本会：

1. 写入一个测试文档
2. 生成 chunks 和 embeddings
3. 模拟服务重启，清空内存知识库注册
4. 重新从数据库检索，验证无需重新上传也能命中相关 chunk

如果没有真实 embedding API Key，可使用 `EMBEDDING_PROVIDER=fake`。测试环境默认也是 fake embedding。

### 如何删除和更新文档

- 删除：`DELETE /documents/{document_id}`
- 更新：`PUT /documents/{document_id}`，上传新的 PDF 后替换原文档内容

这两个接口都要求当前登录用户是文档所有者。删除时会同步删除旧的 chunks 和 embeddings；更新时会先删除旧数据，再在同一事务中写入新 chunks 和 embeddings，避免留下半成品。

### 检索如何过滤

- `user_id` 是所有持久化检索的强制过滤条件
- `document_id` 用于限定到单个文档
- `collection_id` 用于限定到单个知识库集合
- 同时传入 `document_id` 和 `collection_id` 时，两者都会生效

`/documents/retrieve` 以及 `POST /ask/`、`POST /ask_rag/` 的底层检索都遵循这些过滤条件，不能跨用户访问其他人的文档。

---

## 快速启动

### 环境要求

- Python 3.10+
- 可访问阿里云 DashScope 的网络环境

### 0. 克隆仓库（首次）

```bash
git clone https://github.com/ShihangPENg-afk/rag-agentic-system.git
# 双服务联调时，将 predictive-maintenance-mini 克隆到同级目录：
git clone https://github.com/ShihangPENg-afk/predictive-maintenance-mini.git
# LoRA 实验为独立仓库（可选）：
git clone https://github.com/ShihangPENg-afk/llm-finetune-for-manufacturing.git
```

### 1. 安装依赖

```bash
cd rag-agentic-system
make install          # 创建 .venv 并安装 requirements.txt
# 或手动：
python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
make env-init    # 仅当 .env 不存在时从 .env.example 复制，不会覆盖已有 .env
make env-check   # 检查 DASHSCOPE_API_KEY 是否已填入真实值
```

```env
DASHSCOPE_API_KEY=你的_API_Key
EMBEDDING_PROVIDER=dashscope   # 测试/离线可设为 fake
EMBEDDING_MODEL_NAME=text-embedding-v1
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1   # 可选

# PostgreSQL + pgvector（文档元信息 / chunks / embeddings / QA 日志）
POSTGRES_USER=rag_agent_user
POSTGRES_PASSWORD=请改成你自己的数据库密码
POSTGRES_DB=rag_agent_db
DATABASE_URL=postgresql+psycopg2://rag_agent_user:请改成你自己的数据库密码@localhost:5432/rag_agent_db

# 工业设备健康预测 API（predictive-maintenance-mini，默认 :8010）
HEALTH_API_URL=http://127.0.0.1:8010

# Redis（用于 chat 接口限流）
REDIS_URL=redis://localhost:6379/0
```

> 不要使用 `cp .env.example .env` 覆盖已有 `.env`，否则会把真实 API Key 替换成占位符。  
> 若已有 `.env` 但缺少 PostgreSQL 变量，可执行 `make env-init` 自动从 `.env.example` 补全。

如果你只是跑测试或离线调试 embedding，可把 `EMBEDDING_PROVIDER` 设为 `fake`。这个模式不会调用真实 API，也不需要 `DASHSCOPE_API_KEY`。

### 2.1 启动 PostgreSQL + pgvector

PostgreSQL 使用 `pgvector/pgvector:pg16` 镜像，负责保存文档元数据、chunks、embedding 向量和 QA 日志。本地开发可先单独启动数据库容器：

```bash
docker compose up postgres -d
```

或使用 `make docker-up` 同时启动 PostgreSQL 与 API 服务（见下文 Docker 启动）。

最小 Docker 启动命令：

```bash
make env-init
# 编辑 .env：填入 DASHSCOPE_API_KEY，并设置 POSTGRES_USER / POSTGRES_PASSWORD
docker compose up --build
```

### 3. 本地启动

```bash
make run
# 或：python main.py
```

服务默认监听 `http://127.0.0.1:8000`，交互式 API 文档：`http://127.0.0.1:8000/docs`。

启动时会尝试连接 PostgreSQL 并自动建表；数据库暂不可用时，核心 RAG 功能仍可运行，但元数据与 QA 日志不会落库。

### 4. Streamlit UI 启动

UI 为独立前端，通过 HTTP 调用 FastAPI 后端，不直接访问数据库或向量库。

**终端 1 — 启动后端**（需 PostgreSQL 已就绪，见 2.1）：

```bash
make env-check && make run
```

**终端 2 — 启动 Streamlit**：

```bash
source .venv/bin/activate
pip install -r ui/requirements-ui.txt
streamlit run ui/streamlit_app.py
```

浏览器默认打开 `http://127.0.0.1:8501`。侧边栏可配置 `API_BASE_URL`（默认 `http://127.0.0.1:8000`），也可通过环境变量覆盖：

```bash
export API_BASE_URL=http://127.0.0.1:8000
export HEALTH_API_URL=http://127.0.0.1:8010
streamlit run ui/streamlit_app.py
```

UI 主要能力：PDF 上传与向量库构建、多轮 Agent 问答、Debug Trace 可视化、「历史记录」页查看 PostgreSQL 中的 QA 日志、**「设备健康预测」** Tab 调用工业健康 API。演示步骤见 [docs/ui_demo_guide.md](docs/ui_demo_guide.md) 与 [docs/industrial_demo_guide.md](docs/industrial_demo_guide.md)。

### 4.1 双服务联动（rag-agentic-system + predictive-maintenance-mini）

两个仓库通过 **HTTP 松耦合**：rag-agentic-system 占 **8000**，predictive-maintenance-mini 占 **8010**，互不共用进程或数据库。

| 服务 | 端口 | 职责 |
|------|------|------|
| **rag-agentic-system** | `8000` | PDF 上传、Agent 问答、PostgreSQL 元数据 |
| **predictive-maintenance-mini** | `8010` | 传感器特征 → 设备健康分类（`/health`、`/model-info`、`/predict`） |

**一键启动双服务栈**（需同级目录存在 `../predictive-maintenance-mini`）：

```bash
# rag-agentic-system 仓库内
make stack-up          # 先起 predictive-maintenance-mini Docker，再起 rag-agentic-system Docker
make stack-verify      # 验证 8000 + 8010 均正常
```

或分步启动：

```bash
# 终端 A — predictive-maintenance-mini（无 make run，仅 Docker 或 uvicorn）
cd ../predictive-maintenance-mini
make docker-up         # 若缺 model.pkl 会先 train
sleep 5                # 等待 uvicorn 加载模型后再 verify
make docker-verify     # curl /health /model-info + 样例 /predict

# 终端 B — rag-agentic-system
cd ../rag-agentic-system
make env-check && make docker-up
make stack-verify
```

**启动 Streamlit UI**（终端 C）：

```bash
cd rag-agentic-system
source .venv/bin/activate
pip install -r ui/requirements-ui.txt
export API_BASE_URL=http://127.0.0.1:8000
export HEALTH_API_URL=http://127.0.0.1:8010
make ui
# 或: streamlit run ui/streamlit_app.py
```

在 UI 中：

- **侧边栏** `API_BASE_URL` → rag-agentic-system（PDF / 聊天 / Debug Trace）
- **「设备健康预测」Tab** `HEALTH_API_URL` → predictive-maintenance-mini（默认 `http://127.0.0.1:8010`）
- 点击「获取模型信息」加载特征字段 → 输入传感器参数 →「预测设备健康状态」

> **端口冲突注意**：不要在宿主机用 `uvicorn ... --port 8000` 启动 predictive-maintenance-mini；该服务应仅监听 **8010**（Docker 已配置）。若 `make smoke` 报「指向了错误的服务」，说明 8000 被其他进程占用，停止后仅保留 rag-agentic-system 容器即可。

> **Docker 内调用工业 API**：`docker-compose.yml` 中 `HEALTH_API_URL` 默认为 `http://host.docker.internal:8010`（适用于 Docker Desktop / macOS）。在 **Linux** 上若 Agent 容器无法访问宿主机 `:8010`，需在 compose 中增加 `extra_hosts: ["host.docker.internal:host-gateway"]`，或改为宿主机局域网 IP。

### 5. Docker 启动

```bash
make env-init && make env-check
make docker-up          # 后台构建并启动
# 或前台运行：
docker compose up --build
```

启动后访问 [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)。Compose 会同时拉起 `postgres`（端口 `5432`）、`redis`（端口 `6379`）与 `rag-agentic-system`（端口 `8000`）。数据库名为 `rag_agent_db`，并通过 `DATABASE_URL` 将 API 服务指向数据库容器；`REDIS_URL` 指向 Redis 容器，用于 `/ask/` 与 `/ask_rag/` 的用户级限流（同一用户每分钟最多 20 次）。`POSTGRES_USER` 与 `POSTGRES_PASSWORD` 从本地 `.env` 读取，请勿提交真实密码或 API Key。

> **pgvector 向量库**持久化保存在 PostgreSQL 中，容器重启后无需重新上传 PDF 即可检索；FAISS v1 仅作为进程内后备实现保留。

Streamlit UI 需在宿主机单独启动（见上文第 4 节），默认连接 `http://127.0.0.1:8000`。

### 6. Smoke Test

服务启动后，在项目根目录运行端到端冒烟测试（4 步：文档可达 → 上传 PDF → 解析 `knowledge_base_id` → Agent 问答）：

```bash
make smoke
# 自定义目标地址或 PDF：
make smoke BASE_URL=http://127.0.0.1:8000 PDF=test.pdf
```

上传与向量化依赖 DashScope 网络，**完整跑通通常需要 2–4 分钟**。全部通过时输出 `Smoke Test 全部通过 (4/4)`。

---

## API 示例

### 上传 PDF — `POST /upload_pdf/`

```bash
curl -X POST "http://127.0.0.1:8000/upload_pdf/" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@test.pdf"
```

响应示例：

```json
{
  "knowledge_base_id": "d8ce7916-1584-4b9a-ae81-29ac1a374f7a",
  "status": "success",
  "message": "知识库构建成功，包含 83 个文本块",
  "chunks_count": 83,
  "filename": "test.pdf"
}
```

### Agent 问答 — `POST /ask/`

```bash
curl -X POST "http://127.0.0.1:8000/ask/" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "这份文档主要讲什么？",
    "knowledge_base_id": "<上一步返回的 ID>",
    "history": [],
    "debug": true
  }'
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `question` | string | 当前用户问题 |
| `knowledge_base_id` | string | 知识库 ID |
| `history` | array | 多轮历史，每项含 `user`、`assistant`；服务端保留最近 3 轮 |
| `debug` | bool | 为 `true` 时返回工具调用轨迹与推理快照 |

响应中 `mode` 为 `"agent"`；`history` 为更新后的对话列表。

多轮对话示例（第二轮追问时传入上一轮 history）：

```bash
curl -X POST "http://127.0.0.1:8000/ask/" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "软件由哪三个要素构成？",
    "knowledge_base_id": "<知识库 ID>",
    "history": [
      {"user": "这份文档主要讲什么？", "assistant": "文档主要介绍软件工程概述..."}
    ]
  }'
```

### 经典 RAG — `POST /ask_rag/`

```bash
curl -X POST "http://127.0.0.1:8000/ask_rag/" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "这份文档主要讲什么？",
    "knowledge_base_id": "<知识库 ID>",
    "history": []
  }'
```

响应中 `mode` 为 `"rag"`，不走 Agent 工具链，无 `debug` 字段。

### 设备健康预测 — Agent 触发 `check_machine_health`

需先 `make smoke` 或上传 PDF 获得 `knowledge_base_id`；工业 API 需已在 `:8010` 运行（见 [4.1 双服务联动](#41-双服务联动rag-agentic-system--predictive-maintenance-mini)）。

```bash
curl -X POST "http://127.0.0.1:8000/ask/" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "请根据以下传感器读数判断设备健康状态：temperature=75, pressure=1.2, vibration=0.6, speed=118.0, humidity=48.0",
    "knowledge_base_id": "<知识库 ID>",
    "history": [],
    "debug": true
  }'
```

`debug.tool_trace` 中应出现 `check_machine_health`；工具内部请求 `HEALTH_API_URL/predict` 并返回 `prediction`、`risk_level` 等字段的自然语言解读。

### 其他接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/health` | 健康检查（网络、知识库数量） |
| `POST` | `/upload_pdfs/` | 批量上传 PDF |
| `GET` | `/knowledge_bases` | 列出当前已加载的知识库兼容视图 |
| `GET` | `/documents/` | 最近上传文档（PostgreSQL 元信息） |
| `POST` | `/documents/retrieve` | 按 `user_id` / `document_id` / `collection_id` 检索 chunk |
| `PUT` | `/documents/{document_id}` | 替换当前用户文档内容 |
| `DELETE` | `/documents/{document_id}` | 删除当前用户文档并同步删除 chunks / embeddings |
| `GET` | `/qa_logs/?knowledge_base_id=...` | 按知识库查询历史问答（PostgreSQL） |
| `DELETE` | `/knowledge_base/{kb_id}` | 删除指定知识库（仅内存，不删 PG 记录） |
| `DELETE` | `/clear_all_knowledge_bases` | 清空所有内存知识库 |

---

## RAGAS 评估结果

使用 [RAGAS](https://docs.ragas.io/) 对 Agent 问答质量进行离线评估。样本文件 `evals/ragas_samples.json` 含 **10 条手工样本**（问题 + 参考答案）；脚本先逐条调用 Agent 生成回答，再交给 RAGAS 打分。

### 基线评估结果（`test.pdf`，2026-06-10，3/10 样本）

> 完整样本与复现说明见 [docs/ragas_baseline.md](docs/ragas_baseline.md)。

运行配置：`RAGAS_LIMIT=3`、`RAGAS_METRICS=all`、`RAGAS_TIMEOUT=600`

| 指标 | 分数 |
|------|------|
| **faithfulness** | **0.8750** |
| **answer_relevancy** | **0.8858** |

运行状态：知识库 83 块 / 83 向量；Agent 3/3 完成；RAGAS 6/6 Job 无超时。

### 运行命令

```bash
# 默认安全模式：3 条样本 + answer_relevancy 单指标
make eval-ragas

# 双指标基线（faithfulness + answer_relevancy，limit=3）
make eval-ragas RAGAS_LIMIT=3 RAGAS_METRICS=all RAGAS_TIMEOUT=600

# 指定 PDF 或扩大样本数
make eval-ragas PDF=test.pdf RAGAS_LIMIT=5 RAGAS_METRICS=faithfulness
```

也可直接调用脚本：

```bash
python evals/run_ragas_eval.py \
  --pdf test.pdf \
  --samples evals/ragas_samples.json \
  --limit 3 \
  --metrics all \
  --eval-timeout 600
```

### 报告路径

| 文件 | 内容 |
|------|------|
| `docs/ragas_baseline.md` | 已入库的基线快照（分数 + 样本摘要 + 复现命令） |
| `evals/out/ragas_report.json` | 本地运行生成的完整 JSON（`evals/out/` 未纳入 Git） |
| `evals/out/ragas_report.md` | 本地运行生成的 Markdown 报告 |

> `make eval-ragas` 默认仅跑 `relevancy` 单指标以避免超时；**正式基线以 `metrics=all` 报告为准**。`faithfulness` 评估调用 LLM 判分，耗时明显长于 `answer_relevancy`。

---

## RAG Evaluation

这部分和上面的 RAGAS 评估互补：

- **RAGAS** 关注“回答质量”
- **RAG Evaluation** 关注“检索质量”

如果检索没召回到对的 chunk，后面的生成再流畅也很容易缺少依据，所以这部分更适合做检索回归测试和面试演示。

### 为什么需要评估 RAG

- 检索是 RAG 的第一道门，召回质量直接影响最终回答
- 改 chunking、embedding、BM25、fusion 或 rerank 时，需要可重复的回归指标
- 工业运维场景里，很多问题依赖关键词命中，比如报警名、零件名、维护动作和手册章节

### `golden_questions.jsonl` 是什么

文件路径：[`evals/golden_questions.jsonl`](evals/golden_questions.jsonl)

它是一个 JSONL 评估集，每行一条样本，包含：

- `question`
- `expected_keywords`
- `expected_doc_id` 或 `expected_source`

用途是做检索评估，不是直接给模型当标准答案。

### 如何运行评估脚本

脚本路径：[`evals/evaluate_retrieval.py`](evals/evaluate_retrieval.py)

默认会分别跑：

- `v1` baseline：pgvector dense retrieval
- `v2` hybrid：BM25 + pgvector，支持 `use_rerank`

运行示例：

```bash
EVAL_USER_ID=<user_id> python3 evals/evaluate_retrieval.py --top-k 5
```

可选参数：

```bash
EVAL_USER_ID=<user_id> python3 evals/evaluate_retrieval.py \
  --collection-id <collection_id> \
  --document-id <document_id> \
  --top-k 5 \
  --use-rerank
```

如果当前环境没有 LLM 评估条件，可以只跑检索指标；`--with-ragas` 是可选项。

脚本会输出：

- `evals/results_v1.json`
- `evals/results_v2.json`

### v1 baseline 和 v2 hybrid + rerank 的区别

- **v1 baseline**：只用 pgvector dense retrieval，偏语义相似度
- **v2 hybrid**：BM25 关键词召回 + pgvector 语义召回，再做融合排序
- **v2 + rerank**：在 hybrid 候选结果上再做二次排序，保留 `rerank_score`

简单说，v1 更像“语义找相近内容”，v2 更像“语义 + 关键词 双通道召回，再精排”。

### 报告文件在哪里

报告路径：[`evals/report_v1_vs_v2.md`](evals/report_v1_vs_v2.md)

如果你先跑完评估脚本，再打开这个报告，就能把结果文件里的指标对照着看。

### 面试官可以如何复现

1. 准备一批已入库的 PDF 文档，确保能拿到当前用户的 `user_id`
2. 跑评估脚本：

```bash
EVAL_USER_ID=<user_id> python3 evals/evaluate_retrieval.py --top-k 5
```

3. 查看结果文件：
   - `evals/results_v1.json`
   - `evals/results_v2.json`
4. 打开对比报告：
   - `evals/report_v1_vs_v2.md`

如果面试官想看更细的对比，可以固定同一个 `document_id` 或 `collection_id`，这样 v1 和 v2 就是在同一批文档上比较，更容易观察差异。

---

## 与 predictive-maintenance-mini 的关系

**[predictive-maintenance-mini](https://github.com/ShihangPENg-afk/predictive-maintenance-mini)** 是独立的工业预测仓库：EDA → RandomForest 训练 → MLflow → FastAPI 推理（`:8010`）。**非生产级 baseline 模型**，用于演示「传感器特征 → 质量/风险分类」的服务化流程。

| 项目 | 端口 | 职责 |
|------|------|------|
| **rag-agentic-system**（本仓库） | `8000` | PDF 问答、Agent 编排、PostgreSQL 日志、Streamlit |
| **predictive-maintenance-mini** | `8010` | `/health`、`/model-info`、`POST /predict`（含 `risk_level`） |

**联动方式：**

- **Agent 工具**：`check_machine_health` → `app/tools/machine_health_tool.py` → `POST {HEALTH_API_URL}/predict`
- **Streamlit 直连**：「设备健康预测」Tab 不经过 Agent，直接调 `:8010`
- **解耦边界**：两仓库无共享进程、无共享数据库；工业服务可独立升级或替换

工业预测 API 本地启动（在 `predictive-maintenance-mini` 目录）：

```bash
make docker-up && make docker-verify   # 无 make run；Docker 映射 :8010
```

---

## 与 llm-finetune-for-manufacturing 的关系

**[llm-finetune-for-manufacturing](https://github.com/ShihangPENg-afk/llm-finetune-for-manufacturing)** 是独立的 LoRA 微调实验仓库，负责将 PDF 技术手册处理为 Alpaca 格式数据，并在 CPU 环境下完成 Qwen2-7B LoRA 微调验证。

| 项目 | 职责 | 当前状态 |
|------|------|----------|
| **rag-agentic-system**（本仓库） | Agentic RAG 问答、工业工具集成、RAGAS 评估 | 工程化 POC 演示 |
| **predictive-maintenance-mini** | 工业 ML 训练与推理 API | 独立服务，HTTP 联动 |
| **llm-finetune-for-manufacturing** | PDF → Alpaca 数据集 → LoRA 微调 | 独立实验，已完成 CPU 微调验证 |

**LoRA 与 RAGAS：**

- **当前 LoRA 微调模型尚未接入 rag-agentic-system**；问答生成仍使用 DashScope 在线 API（`qwen-plus`）。
- **RAGAS 基线（faithfulness 0.8750、answer_relevancy 0.8858）仅属于 rag-agentic-system**，与微调实验无关。快照见 [docs/ragas_baseline.md](docs/ragas_baseline.md)。

---

## 当前限制

- **FAISS v1 为后备路径**：主检索路径已迁移到 PostgreSQL + pgvector；FAISS 仍保留为进程内兼容实现。
- **集合管理仍较轻量**：上传接口支持可选 `collection_id`，但 UI 中尚未提供完整 collection 管理页面。
- **工业模型为演示 baseline**：predictive-maintenance-mini 使用 RandomForest + 小规模样本，**不可直接用于生产决策**；`/predict` 要求完整特征字段（如 `speed`、`humidity`）。
- **LoRA 微调模型尚未接入**：生成与评估均依赖 DashScope 在线 API（`qwen-plus`），未加载本地微调权重。
- **faithfulness 评估较慢**：RAGAS `Faithfulness` 需额外 LLM 判分，多样本并发时易超时；脚本在 `metrics=faithfulness` 时会自动切换逐条串行模式。
- **文档结构工具为启发式**：`list_headings`、`count_tables` 基于切块文本规则，不解析 PDF 原生目录或表格对象。
- **Memory 为请求级**：多轮对话由客户端在 `history` 字段中传递；跨会话长期记忆依赖 QA 日志查询，非自动注入上下文。
- **经典 RAG 不写 QA 日志**：`POST /ask_rag/` 不写入 PostgreSQL `qa_logs`；仅 `POST /ask/`（Agent 模式）持久化问答历史。
- **无生产鉴权、未云部署**：HTTP 接口面向本地 POC 演示，不具备生产级访问控制与云端部署。

---

## 后续计划

- [x] **pgvector 向量持久化** — PostgreSQL + pgvector 保存 chunks 与 embeddings，支持重启后无需重新上传即可检索
- [ ] **接入微调模型** — 将 [llm-finetune-for-manufacturing](https://github.com/ShihangPENg-afk/llm-finetune-for-manufacturing) 产出的 LoRA 权重接入 Agent 生成节点（**尚未接入**）
- [ ] **增加评估样本** — 扩充 `evals/ragas_samples.json`，覆盖多跳推理与结构类问题
- [x] **CI 基础流水线** — GitHub Actions 运行离线单元测试与编译检查（见 `.github/workflows/ci.yml`）
- [ ] **Smoke / RAGAS 接入 CI** — 需 DashScope Key 的端到端与评估流水线

---

## 项目结构

```
rag-agentic-system/
├── main.py                      # 服务启动入口
├── config.py                    # 全局配置
├── Makefile                     # run / docker-up / smoke / eval-ragas
├── Dockerfile / docker-compose.yml
├── LICENSE                      # MIT License
├── README.md / README.en.md     # 中文 / 英文说明
├── app/
│   ├── api/routes.py            # HTTP 路由
│   ├── agent/                   # LangGraph 状态图与节点
│   ├── services/                # 上传、索引、问答服务
│   ├── tools/                   # Agent 工具（含 machine_health_tool.py）
│   ├── retrievers/              # FAISS v1 / pgvector v2 检索实现
│   └── vectordb/faiss_store.py  # FAISS v1 后备封装
├── ui/
│   ├── streamlit_app.py         # Streamlit 演示 UI
│   └── requirements-ui.txt      # UI 独立依赖
├── app/db/                      # PostgreSQL ORM 与 repository
├── evals/
│   ├── run_ragas_eval.py        # RAGAS 回答质量评估脚本
│   ├── evaluate_retrieval.py    # 检索评估脚本（v1 / v2）
│   ├── ragas_samples.json       # RAGAS 评估样本
│   ├── golden_questions.jsonl   # 检索 golden set
│   ├── report_v1_vs_v2.md       # v1 vs v2 检索评估报告
│   └── out/                     # 本地评估报告输出（gitignore）
├── tests/
│   └── test_offline.py          # 离线单元测试（CI 使用）
├── scripts/
│   ├── smoke_test.sh            # 端到端冒烟测试
│   ├── verify_health_stack.sh   # 双服务联动检查（8000 + 8010）
│   ├── start_stack.sh           # 一键启动双服务栈
│   ├── final_demo_check.sh      # 端到端演示验收脚本
│   └── check_env.sh             # 环境变量检查
└── docs/
    ├── architecture.md          # 详细架构说明
    ├── delivery_checklist.md    # 功能验收清单
    ├── final_report.md          # 项目总结报告
    ├── project_summary.md       # 三仓库生态总览
    ├── ragas_baseline.md        # RAGAS 基线快照
    ├── industrial_demo_guide.md # 工业预测联动演示
    └── ui_demo_guide.md         # UI 录屏演示步骤
```

## 常用命令

```bash
make help             # 查看所有命令
make run              # 本地启动 FastAPI (:8000)
make docker-up        # Docker 后台启动（API + PostgreSQL）
make docker-down      # 停止容器
make stack-up         # 启动 rag-agentic-system + predictive-maintenance-mini 双栈
make stack-verify     # 验证 :8000 与 :8010 均正常
make smoke            # 端到端冒烟测试（4/4）
make eval-ragas       # RAGAS 评估
make ui               # 启动 Streamlit UI

# Streamlit UI（另开终端，需设置 HEALTH_API_URL 以使用设备健康 Tab）
export API_BASE_URL=http://127.0.0.1:8000
export HEALTH_API_URL=http://127.0.0.1:8010
pip install -r ui/requirements-ui.txt && streamlit run ui/streamlit_app.py
```

## License

本项目采用 [MIT License](LICENSE) 开源。
