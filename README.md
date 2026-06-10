# rag-agent

基于 **Agentic RAG** 的 PDF 智能问答系统：上传 PDF 后自动切块、向量化并建立 FAISS 索引，通过 LangGraph Agent 进行工具调用、多步推理与对话记忆，最终以 HTTP API 对外提供问答能力。

项目同时支持 **Docker 一键部署**、**端到端 Smoke Test** 与 **RAGAS 离线评估**，可作为完整的 RAG + Agent 工程实践展示。

详细架构见 [docs/architecture.md](docs/architecture.md)。

---

## 核心功能

| 功能 | 说明 |
|------|------|
| **PDF 上传与文本切块** | 单文件 / 批量上传，校验 `%PDF` 魔数，pypdf 解析后切块、去重 |
| **FAISS 向量检索** | DashScope TextEmbedding 向量化，进程内 FAISS 相似度检索 |
| **Agent 工具调用** | LangGraph 驱动，支持 `retrieve_chunks`、`list_headings`、`count_tables` |
| **多步推理** | `planner` 拆解子问题，`evaluator` 汇总证据并决定是否继续检索 |
| **对话 Memory** | 请求体传入 `history`，保留最近 3 轮；Agent 将历史摘要注入 system message，检索工具也可利用历史做指代消解 |
| **Debug trace** | `/ask/` 设置 `debug: true`，返回 `tool_trace`、`reasoning_snapshot`、`retrieved_evidence_preview` |
| **Docker 部署** | `Dockerfile` + `docker-compose.yml`，含 healthcheck |
| **RAGAS 评估** | 离线脚本对 Agent 回答打分，输出 JSON / Markdown 报告 |

**问答入口：**

- `POST /ask/` — LangGraph Agent（默认主路径）
- `POST /ask_rag/` — 经典 RAG 单链路（检索 → Prompt → 生成，用于对照基线）

---

## 技术栈

| 类别 | 技术 |
|------|------|
| Web 框架 | **FastAPI**、Uvicorn |
| Agent 编排 | **LangGraph**、LangChain OpenAI 兼容接口 |
| 向量检索 | **FAISS**、NumPy |
| 大模型 / 向量 | **DashScope**（`qwen-plus`、TextEmbedding），通过 **OpenAI-compatible API** 调用 |
| 容器化 | **Docker**、**Docker Compose** |
| 质量评估 | **RAGAS**（`Faithfulness`、`ResponseRelevancy`） |
| 文本处理 | pypdf、langchain-text-splitters |

---

## 架构概览

```
上传 PDF → 切块 / 向量化 → FAISS 索引（进程内知识库）
                              ↓
                    POST /ask/（Agent，默认）
                              ↓
         planner → agent ⇄ tools → evaluator → answer
                              ↓
              retrieve_chunks / list_headings / count_tables

                    POST /ask_rag/（经典 RAG，回退）
                              ↓
         历史增强 → FAISS 检索 → Prompt → DashScope 生成
```

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
```

> 不要使用 `cp .env.example .env` 覆盖已有 `.env`，否则会把真实 API Key 替换成占位符。

### 3. 本地启动

```bash
make run
# 或：python main.py
```

服务默认监听 `http://127.0.0.1:8000`，交互式 API 文档：`http://127.0.0.1:8000/docs`。

### 4. Docker 启动

```bash
make env-init && make env-check
make docker-up          # 后台构建并启动
# 或前台运行：
docker compose up --build
```

启动后访问 [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)。

> 知识库保存在**进程内存**中，容器重启后需重新上传 PDF。

### 5. Smoke Test

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

### 其他接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/health` | 健康检查（网络、知识库数量） |
| `POST` | `/upload_pdfs/` | 批量上传 PDF |
| `GET` | `/knowledge_bases` | 列出所有知识库 |
| `DELETE` | `/knowledge_base/{kb_id}` | 删除指定知识库 |
| `DELETE` | `/clear_all_knowledge_bases` | 清空所有知识库 |

---

## RAGAS 评估结果

使用 [RAGAS](https://docs.ragas.io/) 对 Agent 问答质量进行离线评估。样本文件 `evals/ragas_samples.json` 含 **10 条手工样本**（问题 + 参考答案）；脚本先逐条调用 Agent 生成回答，再交给 RAGAS 打分。

### Day 5 评估结果（`test.pdf`，2026-06-10）

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

# Day 5 同款全量指标（faithfulness + answer_relevancy）
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

## 与 llm-finetune-manual 的关系

**[llm-finetune-manual](../llm-finetune-manual)** 是独立的 LoRA 微调实验仓库，负责将 PDF 技术手册处理为 Alpaca 格式数据，并在 CPU 环境下完成 Qwen2-7B LoRA 微调验证。

| 项目 | 职责 | 当前状态 |
|------|------|----------|
| **rag-agent**（本仓库） | Agentic RAG 问答服务、FAISS 检索、LangGraph Agent、RAGAS 评估 | 生产可用演示 |
| **llm-finetune-manual** | PDF → Alpaca 数据集 → LoRA 微调 | 独立实验，已完成 CPU 微调验证 |

**两者关系：**

- 同属 PDF 知识处理链路的不同阶段，但**代码与部署完全独立**，各自有独立的虚拟环境与依赖。
- **当前 LoRA 微调模型尚未接入 rag-agent**；本仓库问答仍使用 DashScope 在线 API（`qwen-plus`）。
- **Day 5 RAGAS 指标（faithfulness 0.8750、answer_relevancy 0.8858）仅属于 rag-agent**，与微调实验无关。

---

## 当前限制

- **知识库为进程级注册**：FAISS 索引与 chunk 数据保存在内存中，服务或容器重启后需重新上传 PDF。
- **未接入持久化数据库**：无 Redis / PostgreSQL / 向量数据库等外部存储。
- **LoRA 微调模型尚未接入**：生成与评估均依赖 DashScope 在线 API，未加载本地微调权重。
- **faithfulness 评估较慢**：RAGAS `Faithfulness` 需额外 LLM 判分，多样本并发时易超时；脚本在 `metrics=faithfulness` 时会自动切换逐条串行模式。
- **文档结构工具为启发式**：`list_headings`、`count_tables` 基于切块文本规则，不解析 PDF 原生目录或表格对象。
- **Memory 为请求级**：多轮对话由客户端在 `history` 字段中传递，服务端不跨会话持久化用户记忆。

---

## 后续计划

- [ ] **持久化知识库** — 将 FAISS 索引与元数据落盘或接入向量数据库，支持重启恢复
- [ ] **接入微调模型** — 将 llm-finetune-manual 产出的 LoRA 权重接入 Agent 生成节点，支持本地推理
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
│   ├── tools/                   # Agent 工具
│   └── vectordb/faiss_store.py  # FAISS 封装
├── evals/
│   ├── run_ragas_eval.py        # RAGAS 评估脚本
│   ├── ragas_samples.json       # 评估样本
│   └── out/                     # 评估报告输出
├── scripts/
│   ├── smoke_test.sh            # 端到端冒烟测试
│   └── check_env.sh             # 环境变量检查
└── docs/architecture.md         # 详细架构说明
```

## 常用命令

```bash
make help             # 查看所有命令
make run              # 本地启动
make docker-up        # Docker 后台启动
make docker-down      # 停止容器
make smoke            # 端到端冒烟测试
make eval-ragas       # RAGAS 评估
make test-agent       # Agent 本地测试
make test-retrieval   # 检索工具测试
make test-doc-tools   # 文档结构工具测试
```

## License

未指定开源协议时，请按项目所有者要求使用与分发。
