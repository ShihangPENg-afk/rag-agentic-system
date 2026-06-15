# rag-agent

基于 **Agentic RAG** 的 PDF 智能问答系统，并集成 **工业设备健康预测** 能力：上传 PDF 后自动切块、向量化并建立 FAISS 索引，通过 LangGraph Agent 进行工具调用、多步推理与对话记忆；同时通过 `check_machine_health` 工具 HTTP 调用独立工业预测服务，实现「文档问答 + 传感器风险预测」双链路编排。

项目覆盖 **Web API（FastAPI）**、**Streamlit 前端**、**PostgreSQL 结构化日志**、**Docker 部署**、**RAGAS 离线评估** 与 **双服务联动验收**，可作为 RAG + Agent + 工业场景 AI 的工程化 POC 展示。

详细架构见 [docs/architecture.md](docs/architecture.md)；工业联动演示见 [docs/industrial_demo_guide.md](docs/industrial_demo_guide.md)。

---

## 视频演示

完整功能演示视频（PDF 问答、Debug Trace、PostgreSQL 历史、设备健康预测 Tab、Agent 调用 `check_machine_health`）可通过百度网盘观看：

| 项 | 内容 |
|----|------|
| 文件 | `rag-demo.mp4` |
| 链接 | https://pan.baidu.com/s/1G3FDGbw7h37hDuddjUFpRg |
| 提取码 | `iqcq` |

> 视频为端到端演示录屏。如需逐步操作，可参考 [docs/ui_demo_guide.md](docs/ui_demo_guide.md)（PDF 问答）与 [docs/industrial_demo_guide.md](docs/industrial_demo_guide.md)（工业预测联动）。

---

## 项目亮点（能力概览）

| 方向 | 实现要点 |
|------|----------|
| **RAG / Agent** | LangGraph 多步推理；`retrieve_chunks` / `list_headings` / `count_tables`；`/ask/` 与经典 RAG `/ask_rag/` 对照 |
| **Web 开发** | FastAPI REST API + Streamlit 宽屏 UI；Debug Trace 四面板可视化 |
| **DevOps** | Docker Compose（API + PostgreSQL）；`make smoke` 四步冒烟；`make stack-up` 双服务栈联动 |
| **RAG 评估** | RAGAS 离线评估（faithfulness **0.875**、answer_relevancy **0.886**，3/10 样本基线） |
| **工业场景 AI** | 联动 [industrial-health-demo](../industrial-health-demo)（`:8010`）；传感器 → `prediction` / `risk_level` / 运维建议 |
| **Agent 工具集成** | `check_machine_health` 经 HTTP 调工业 `/predict`；`debug.tool_trace` 可观测；与 PDF 问答链路解耦并存 |

**关联独立仓库（同级目录）：**

- **[industrial-health-demo](../industrial-health-demo)** — EDA、RandomForest 训练、FastAPI 推理、Docker（工业预测）
- **[llm-finetune-manual](../llm-finetune-manual)** — PDF → LoRA 微调实验（**尚未接入**本仓库）

---

## 核心功能

| 功能 | 说明 |
|------|------|
| **PDF 上传与文本切块** | 单文件 / 批量上传，校验 `%PDF` 魔数，pypdf 解析后切块、去重 |
| **FAISS 向量检索** | DashScope TextEmbedding 向量化，进程内 FAISS 相似度检索 |
| **Agent 工具调用** | LangGraph 驱动，支持 `retrieve_chunks`、`list_headings`、`count_tables`、**`check_machine_health`**（工业预测） |
| **工业预测联动** | Agent 工具 / Streamlit Tab 双入口，HTTP 调用 industrial-health-demo 的 `/predict` |
| **多步推理** | `planner` 拆解子问题，`evaluator` 汇总证据并决定是否继续检索 |
| **对话 Memory** | 请求体传入 `history`，保留最近 3 轮；Agent 将历史摘要注入 system message，检索工具也可利用历史做指代消解 |
| **Debug trace** | `/ask/` 设置 `debug: true`，返回 `tool_trace`、`reasoning_snapshot`、`retrieved_evidence_preview` |
| **Streamlit UI** | 浏览器端上传 PDF、多轮问答、Debug Trace 可视化、历史问答查看、**设备健康预测**（联动 industrial-health-demo） |
| **PostgreSQL 混合持久化** | 文档元信息与 QA 日志落库；**向量检索仍用进程内 FAISS** |
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
| 向量检索 | **FAISS**、NumPy（进程内，**不写入 PostgreSQL**） |
| 元数据 / 日志 | **PostgreSQL 16**、SQLAlchemy（`documents`、`qa_logs` 表） |
| 大模型 / 向量 | **DashScope**（`qwen-plus`、TextEmbedding），通过 **OpenAI-compatible API** 调用 |
| 容器化 | **Docker**、**Docker Compose**（`rag-agent` + `postgres`；工业服务见 sibling 仓库） |
| 工业预测（外部） | **[industrial-health-demo](../industrial-health-demo)**：scikit-learn、FastAPI `:8010`（本仓库通过 HTTP 调用） |
| 质量评估 | **RAGAS**（`Faithfulness`、`ResponseRelevancy`） |
| 文本处理 | pypdf、langchain-text-splitters |

---

## 架构概览

```
上传 PDF → 切块 / 向量化 → FAISS 索引（进程内，可问答）
              │                    ↓
              │          POST /ask/（Agent，默认）
              │                    ↓
              │   planner → agent ⇄ tools → evaluator → answer
              │                    ↓
              │    retrieve_chunks / list_headings / count_tables
              │    check_machine_health ──HTTP──► industrial-health-demo :8010
              │                                      POST /predict → risk_level
              ↓
     PostgreSQL documents 表（元信息：文件名、块数、状态）
                              ↓
                    qa_logs 表（问答历史 + 可选 debug JSON）

Streamlit UI（:8501）──┬── API_BASE_URL → rag-agent :8000（PDF / 聊天 / Debug）
                       └── HEALTH_API_URL → industrial-health-demo :8010（设备健康 Tab 直连）

                    POST /ask_rag/（经典 RAG，回退）
                              ↓
         历史增强 → FAISS 检索 → Prompt → DashScope 生成
```

**混合持久化说明：** 向量索引与 chunk 文本保存在**进程内存**（FAISS + `kb_registry`）；PostgreSQL **仅**持久化上传文档的元信息（`documents`）与 Agent 问答日志（`qa_logs`）。服务重启后，数据库中的历史记录仍可查询，但 FAISS 索引会丢失，需重新上传 PDF 才能继续问答。详见 [docs/architecture.md](docs/architecture.md)。

---

## 快速启动

### 环境要求

- Python 3.10+
- 可访问阿里云 DashScope 的网络环境

### 1. 安装依赖

```bash
cd rag-agent
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
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1   # 可选

# PostgreSQL（文档元信息 / QA 日志；向量仍走 FAISS）
POSTGRES_USER=ragagent
POSTGRES_PASSWORD=ragagent_secret
POSTGRES_DB=ragagent
DATABASE_URL=postgresql+psycopg2://ragagent:ragagent_secret@localhost:5432/ragagent

# 工业设备健康预测 API（industrial-health-demo，默认 :8010）
HEALTH_API_URL=http://127.0.0.1:8010
```

> 不要使用 `cp .env.example .env` 覆盖已有 `.env`，否则会把真实 API Key 替换成占位符。  
> 若已有 `.env` 但缺少 PostgreSQL 变量，可执行 `make env-init` 自动从 `.env.example` 补全。

### 2.1 启动 PostgreSQL（混合持久化）

PostgreSQL 只存元数据与 QA 日志，**不参与向量检索**。本地开发可先单独启动数据库容器：

```bash
docker compose up postgres -d
```

或使用 `make docker-up` 同时启动 PostgreSQL 与 API 服务（见下文 Docker 启动）。

### 3. 本地启动

```bash
make run
# 或：python main.py
```

服务默认监听 `http://127.0.0.1:8000`，交互式 API 文档：`http://127.0.0.1:8000/docs`。

启动时会尝试连接 PostgreSQL 并自动建表；数据库暂不可用时，核心 RAG 功能仍可运行，但元数据与 QA 日志不会落库。

### 4. Streamlit UI 启动

UI 为独立前端，通过 HTTP 调用 FastAPI 后端，不直接访问 FAISS 或 PostgreSQL。

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

### 4.1 双服务联动（rag-agent + industrial-health-demo）

两个仓库通过 **HTTP 松耦合**：rag-agent 占 **8000**，industrial-health-demo 占 **8010**，互不共用进程或数据库。

| 服务 | 端口 | 职责 |
|------|------|------|
| **rag-agent** | `8000` | PDF 上传、Agent 问答、PostgreSQL 元数据 |
| **industrial-health-demo** | `8010` | 传感器特征 → 设备健康分类（`/health`、`/model-info`、`/predict`） |

**一键启动双服务栈**（需同级目录存在 `../industrial-health-demo`）：

```bash
# rag-agent 仓库内
make stack-up          # 先起 industrial-health-demo Docker，再起 rag-agent Docker
make stack-verify      # 验证 8000 + 8010 均正常
```

或分步启动：

```bash
# 终端 A — industrial-health-demo（无 make run，仅 Docker 或 uvicorn）
cd ../industrial-health-demo
make docker-up         # 若缺 model.pkl 会先 train
sleep 5                # 等待 uvicorn 加载模型后再 verify
make docker-verify     # curl /health /model-info + 样例 /predict

# 终端 B — rag-agent
cd ../rag-agent
make env-check && make docker-up
make stack-verify
```

**启动 Streamlit UI**（终端 C）：

```bash
cd rag-agent
source .venv/bin/activate
pip install -r ui/requirements-ui.txt
export API_BASE_URL=http://127.0.0.1:8000
export HEALTH_API_URL=http://127.0.0.1:8010
make ui
# 或: streamlit run ui/streamlit_app.py
```

在 UI 中：

- **侧边栏** `API_BASE_URL` → rag-agent（PDF / 聊天 / Debug Trace）
- **「设备健康预测」Tab** `HEALTH_API_URL` → industrial-health-demo（默认 `http://127.0.0.1:8010`）
- 点击「获取模型信息」加载特征字段 → 输入传感器参数 →「预测设备健康状态」

> **端口冲突注意**：不要在宿主机用 `uvicorn ... --port 8000` 启动 industrial-health-demo；该服务应仅监听 **8010**（Docker 已配置）。若 `make smoke` 报「指向了错误的服务」，说明 8000 被其他进程占用，停止后仅保留 rag-agent 容器即可。

### 5. Docker 启动

```bash
make env-init && make env-check
make docker-up          # 后台构建并启动
# 或前台运行：
docker compose up --build
```

启动后访问 [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)。Compose 会同时拉起 `postgres`（端口 `5432`）与 `rag-agent`（端口 `8000`），并通过 `DATABASE_URL` 将 API 服务指向数据库容器。

> **FAISS 向量索引**仍在 API 进程内存中，容器重启后需重新上传 PDF 才能问答；**PostgreSQL** 中的文档元信息与 QA 日志会保留。

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

需先 `make smoke` 或上传 PDF 获得 `knowledge_base_id`；工业 API 需已在 `:8010` 运行（见 [4.1 双服务联动](#41-双服务联动rag-agent--industrial-health-demo)）。

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
| `GET` | `/knowledge_bases` | 列出当前内存中可问答的知识库（FAISS 已加载） |
| `GET` | `/documents/` | 最近上传文档（PostgreSQL 元信息） |
| `GET` | `/qa_logs/?knowledge_base_id=...` | 按知识库查询历史问答（PostgreSQL） |
| `DELETE` | `/knowledge_base/{kb_id}` | 删除指定知识库（仅内存，不删 PG 记录） |
| `DELETE` | `/clear_all_knowledge_bases` | 清空所有内存知识库 |

---

## RAGAS 评估结果

使用 [RAGAS](https://docs.ragas.io/) 对 Agent 问答质量进行离线评估。样本文件 `evals/ragas_samples.json` 含 **10 条手工样本**（问题 + 参考答案）；脚本先逐条调用 Agent 生成回答，再交给 RAGAS 打分。

### 基线评估结果（`test.pdf`，2026-06-10，3/10 样本）

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
| `evals/out/ragas_report.json` | `summary`、`samples`（逐条 question / reference / answer）、`eval_config` |
| `evals/out/ragas_report.md` | 同上，Markdown 可读版本 |

> `make eval-ragas` 默认仅跑 `relevancy` 单指标以避免超时；**正式基线以 `metrics=all` 报告为准**。`faithfulness` 评估调用 LLM 判分，耗时明显长于 `answer_relevancy`。

---

## 与 industrial-health-demo 的关系

**[industrial-health-demo](../industrial-health-demo)** 是独立的工业预测仓库：EDA → RandomForest 训练 → MLflow → FastAPI 推理（`:8010`）。**非生产级 baseline 模型**，用于演示「传感器特征 → 质量/风险分类」的服务化流程。

| 项目 | 端口 | 职责 |
|------|------|------|
| **rag-agent**（本仓库） | `8000` | PDF 问答、Agent 编排、PostgreSQL 日志、Streamlit |
| **industrial-health-demo** | `8010` | `/health`、`/model-info`、`POST /predict`（含 `risk_level`） |

**联动方式：**

- **Agent 工具**：`check_machine_health` → `app/tools/machine_health_tool.py` → `POST {HEALTH_API_URL}/predict`
- **Streamlit 直连**：「设备健康预测」Tab 不经过 Agent，直接调 `:8010`
- **解耦边界**：两仓库无共享进程、无共享数据库；工业服务可独立升级或替换

工业预测 API 本地启动（在 `industrial-health-demo` 目录）：

```bash
make docker-up && make docker-verify   # 无 make run；Docker 映射 :8010
```

---

## 与 llm-finetune-manual 的关系

**[llm-finetune-manual](../llm-finetune-manual)** 是独立的 LoRA 微调实验仓库，负责将 PDF 技术手册处理为 Alpaca 格式数据，并在 CPU 环境下完成 Qwen2-7B LoRA 微调验证。

| 项目 | 职责 | 当前状态 |
|------|------|----------|
| **rag-agent**（本仓库） | Agentic RAG 问答、工业工具集成、RAGAS 评估 | 工程化 POC 演示 |
| **industrial-health-demo** | 工业 ML 训练与推理 API | 独立服务，HTTP 联动 |
| **llm-finetune-manual** | PDF → Alpaca 数据集 → LoRA 微调 | 独立实验，已完成 CPU 微调验证 |

**LoRA 与 RAGAS：**

- **当前 LoRA 微调模型尚未接入 rag-agent**；问答生成仍使用 DashScope 在线 API（`qwen-plus`）。
- **RAGAS 基线（faithfulness 0.8750、answer_relevancy 0.8858）仅属于 rag-agent**，与微调实验无关。

---

## 当前限制

- **向量仍为进程内 FAISS**：FAISS 索引与 chunk 文本保存在内存中，服务或容器重启后需重新上传 PDF 才能问答；PostgreSQL **不**存储向量或 chunk 正文。
- **PostgreSQL 仅混合持久化**：`documents` 表记录上传元信息，`qa_logs` 表记录 Agent 问答与 debug 快照；重启后可在 UI/API 查看历史，但无法仅凭数据库记录恢复检索能力。
- **工业模型为演示 baseline**：industrial-health-demo 使用 RandomForest + 小规模样本，**不可直接用于生产决策**；`/predict` 要求完整特征字段（如 `speed`、`humidity`）。
- **LoRA 微调模型尚未接入**：生成与评估均依赖 DashScope 在线 API（`qwen-plus`），未加载本地微调权重。
- **faithfulness 评估较慢**：RAGAS `Faithfulness` 需额外 LLM 判分，多样本并发时易超时；脚本在 `metrics=faithfulness` 时会自动切换逐条串行模式。
- **文档结构工具为启发式**：`list_headings`、`count_tables` 基于切块文本规则，不解析 PDF 原生目录或表格对象。
- **Memory 为请求级**：多轮对话由客户端在 `history` 字段中传递；跨会话长期记忆依赖 QA 日志查询，非自动注入上下文。

---

## 后续计划

- [ ] **FAISS / 向量持久化** — 将 FAISS 索引落盘或接入专用向量数据库，支持重启后无需重新上传即可问答
- [ ] **接入微调模型** — 将 llm-finetune-manual 产出的 LoRA 权重接入 Agent 生成节点（**当前阶段未接入**）
- [ ] **增加评估样本** — 扩充 `evals/ragas_samples.json`，覆盖多跳推理与结构类问题
- [ ] **增加 CI/CD** — 在流水线中自动运行 Smoke Test 与 RAGAS 基线对比

---

## 项目结构

```
rag-agent/
├── main.py                      # 服务启动入口
├── config.py                    # 全局配置
├── Makefile                     # run / docker-up / smoke / eval-ragas
├── Dockerfile / docker-compose.yml
├── app/
│   ├── api/routes.py            # HTTP 路由
│   ├── agent/                   # LangGraph 状态图与节点
│   ├── services/                # 上传、索引、问答服务
│   ├── tools/                   # Agent 工具（含 machine_health_tool.py）
│   └── vectordb/faiss_store.py  # FAISS 封装
├── ui/
│   ├── streamlit_app.py         # Streamlit 演示 UI
│   └── requirements-ui.txt      # UI 独立依赖
├── app/db/                      # PostgreSQL ORM 与 repository
├── evals/
│   ├── run_ragas_eval.py        # RAGAS 评估脚本
│   ├── ragas_samples.json       # 评估样本
│   └── out/                     # 评估报告输出
├── scripts/
│   ├── smoke_test.sh            # 端到端冒烟测试
│   ├── verify_health_stack.sh   # 双服务联动检查（8000 + 8010）
│   ├── start_stack.sh           # 一键启动双服务栈
│   ├── final_demo_check.sh      # 端到端演示验收脚本
│   └── check_env.sh             # 环境变量检查
└── docs/
    ├── architecture.md          # 详细架构说明
    ├── delivery_checklist.md    # 交付验收清单
    ├── industrial_demo_guide.md # 工业预测联动演示
    └── ui_demo_guide.md         # UI 录屏演示步骤
```

## 常用命令

```bash
make help             # 查看所有命令
make run              # 本地启动 FastAPI (:8000)
make docker-up        # Docker 后台启动（API + PostgreSQL）
make docker-down      # 停止容器
make stack-up         # 启动 rag-agent + industrial-health-demo 双栈
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

未指定开源协议时，请按项目所有者要求使用与分发。
