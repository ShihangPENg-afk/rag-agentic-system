# rag-agent 项目结项报告

> 报告日期：2026-06-10  
> 项目仓库：rag-agent  
> 相关文档：[architecture.md](architecture.md) · [README.md](../README.md)

---

## 1. 项目目标

本项目旨在将传统的「上传 PDF → 向量检索 → 生成回答」流程，升级为具备 **工具调用**、**多步推理** 与 **对话记忆** 的 **Agentic RAG** 系统，并通过可复现的工程化手段完成验收。

具体目标如下：

| 目标 | 完成情况 |
|------|----------|
| 支持 PDF 上传、文本切块与 FAISS 向量检索 | 已完成 |
| 以 LangGraph Agent 作为默认问答主路径（`/ask/`） | 已完成 |
| 保留经典 RAG 链路（`/ask_rag/`）作为对照基线 | 已完成 |
| 提供 Docker 容器化部署与 healthcheck | 已完成 |
| 提供端到端 Smoke Test 脚本 | 已完成 |
| 使用 RAGAS 对 Agent 回答质量进行离线评估 | 已完成（3 条样本基线） |

**未纳入本期范围：** 知识库持久化、本地 LoRA 模型接入、生产级鉴权与 CI/CD。这些能力列入后续优化方向，见第 8 节。

---

## 2. 系统架构

### 2.1 总体分层

```
┌─────────────────────────────────────────────────────────┐
│  API 层（FastAPI / Uvicorn）                             │
│  /upload_pdf/  /ask/  /ask_rag/  /health  ...           │
├─────────────────────────────────────────────────────────┤
│  服务层                                                  │
│  upload_service · index_service · agent_chat_service    │
│  chat_service · kb_registry（进程内知识库注册表）          │
├─────────────────────────────────────────────────────────┤
│  Agent 层（LangGraph）                                   │
│  planner → agent ⇄ tools → evaluator → answer           │
├─────────────────────────────────────────────────────────┤
│  工具层                                                  │
│  retrieve_chunks · list_headings · count_tables          │
├─────────────────────────────────────────────────────────┤
│  向量层（FAISS + DashScope TextEmbedding）               │
└─────────────────────────────────────────────────────────┘
```

### 2.2 技术选型

| 组件 | 选型 | 说明 |
|------|------|------|
| Web 框架 | FastAPI + Uvicorn | HTTP API 与交互式文档 |
| Agent 编排 | LangGraph | 状态图驱动多节点推理 |
| 向量检索 | FAISS（进程内） | 无需外部向量数据库 |
| 大模型 | DashScope `qwen-plus` | OpenAI 兼容 API |
| 向量化 | DashScope TextEmbedding | 固定维度 1536 |
| 容器化 | Docker + Docker Compose | 单服务编排 |
| 质量评估 | RAGAS | Faithfulness、ResponseRelevancy |

### 2.3 知识库生命周期

1. 客户端上传 PDF → `upload_service` 校验魔数与扩展名  
2. `index_service` 解析 PDF、切块（默认 300 字 / 50 重叠）、去重  
3. 调用 DashScope 批量向量化 → 写入 FAISS 索引  
4. `kb_registry` 以 UUID 注册知识库，保存在**进程内存**  
5. 问答时按 `knowledge_base_id` 查找索引与 chunk 列表  

服务或容器重启后，内存中的知识库会丢失，需重新上传 PDF。

---

## 3. Agentic RAG 主流程

默认问答入口为 `POST /ask/`，由 LangGraph 状态图（`app/agent/graph.py`）编排。

### 3.1 图节点

```text
START → planner → agent ──(有 tool_calls)──→ tools → evaluator
                      └──(无 tool_calls)──────────────→ evaluator
evaluator ──(need_more_retrieval / next_sub_query)──→ agent
          └──(enough_to_answer)──────────────────────→ answer → END
```

| 节点 | 职责 |
|------|------|
| `planner` | 判断是否需要多跳，将复杂问题拆解为 `sub_queries` |
| `agent` | 绑定工具，由 Qwen 决定是否发起 `tool_calls` |
| `tools` | 执行 `retrieve_chunks`、`list_headings`、`count_tables` |
| `evaluator` | 汇总各子问题证据，决定继续检索或进入回答 |
| `answer` | 基于已收集证据生成最终答复 |

### 3.2 Agent 工具

| 工具 | 适用场景 |
|------|----------|
| `retrieve_chunks` | 文档内容、概念、段落相关问答；可利用 `history` 做指代消解 |
| `list_headings` | 章节、目录、文档结构（基于 chunk 启发式提取） |
| `count_tables` | 表格迹象统计（启发式，非 PDF 原生表格解析） |

### 3.3 对话 Memory

- 客户端在请求体中传入 `history`（`user` / `assistant` 对），服务端保留最近 **3 轮**。
- Agent 将历史摘要写入 `memory_summary`，以额外 system message 注入 LLM。
- Memory 为**请求级传递**，服务端不跨会话持久化用户对话。

### 3.4 Debug Trace

`debug: true` 时，响应附带：

- `tool_trace` — 工具名、输入、输出预览  
- `reasoning_snapshot` — 子问题列表、检索轮次、`decision`  
- `retrieved_evidence_preview` — 证据片段预览  
- `memory_snapshot` — 当前问题与历史摘要  

### 3.5 经典 RAG 回退路径

`POST /ask_rag/` 不走 Agent 工具链，流程为：

```text
history 指代增强 → FAISS 检索 → Prompt 组装 → DashScope 生成
```

用于简单事实问答及与 Agent 结果的对照排查。

---

## 4. Docker 验收结果

### 4.1 交付物

| 文件 | 说明 |
|------|------|
| `Dockerfile` | 基于 `python:3.10-slim`，安装 `libgomp1`（FAISS 依赖），CMD 为 uvicorn |
| `docker-compose.yml` | 单服务 `rag-agent`，端口 8000，挂载 `.env`、`data/`、`evals/out/` |
| `.dockerignore` | 排除 `.venv`、`.env`、`data/`、`evals/out/` 等本地文件 |

### 4.2 验收操作与结果

```bash
make env-init && make env-check
make docker-up          # docker compose up --build -d
```

| 验收项 | 结果 |
|--------|------|
| 镜像构建 | 通过（`rag-agent-rag-agent:latest`） |
| 容器启动 | 通过（容器名 `rag-agent`） |
| 端口映射 | `8000:8000` 正常 |
| healthcheck | 已配置，探测 `GET /health`（间隔 30s，启动宽限 40s） |
| API 文档可达 | 通过（`/openapi.json` 可访问） |

### 4.3 已知约束

- 知识库仍在进程内存中，**容器重启后需重新上传 PDF**。
- `docker-compose.yml` 通过 `env_file: .env` 注入 API Key，部署前须确保 `.env` 已配置且不被提交到版本库。
- 本次验收为单节点 Compose 演示，未覆盖多副本、负载均衡或外部持久化存储。

---

## 5. Smoke Test 验收结果

### 5.1 测试说明

脚本：`scripts/smoke_test.sh`  
入口：`make smoke`（默认 `BASE_URL=http://127.0.0.1:8000`，`PDF=test.pdf`）

共 **4 步**，任一步失败则整体失败：

| 步骤 | 检查内容 |
|------|----------|
| 1/4 | `/openapi.json` 或 `/docs` 可达 |
| 2/4 | `POST /upload_pdf/` 上传成功 |
| 3/4 | 响应中可解析 `knowledge_base_id` |
| 4/4 | `POST /ask/` 返回非空 `answer` 且 `mode=agent` |

### 5.2 验收结果（2026-06-10）

在 **Docker 容器启动后** 对 `http://127.0.0.1:8000` 执行 `make smoke`：

```
✅ [1/4] /openapi.json 可访问
✅ [2/4] PDF 上传成功（83 个文本块）
✅ [3/4] knowledge_base_id 解析成功
✅ [4/4] Agent 问答成功（mode=agent，debug trace 正常返回）

Smoke Test 全部通过 (4/4)
```

### 5.3 补充说明

- 上传与向量化依赖 DashScope 网络，完整跑通通常需要 **2–4 分钟**，属预期范围。
- Smoke Test 验证的是**链路可用性**（接口可达、知识库可建、Agent 可答），不评估回答内容的语义质量。
- 本地直启（`make run`）与 Docker 启服均可作为 Smoke Test 的前置条件，本次记录在 Docker 环境下验收通过。

---

## 6. RAGAS 评估结果

### 6.1 评估配置

| 参数 | 值 |
|------|-----|
| 评估脚本 | `evals/run_ragas_eval.py` |
| 测试 PDF | `test.pdf`（83 块文本） |
| 样本文件 | `evals/ragas_samples.json`（共 10 条，本次取前 3 条） |
| `limit` | 3 |
| `metrics` | `all`（Faithfulness + ResponseRelevancy） |
| `eval_timeout` | 600 秒 |

运行命令：

```bash
make eval-ragas RAGAS_LIMIT=3 RAGAS_METRICS=all RAGAS_TIMEOUT=600
```

### 6.2 Day 5 评估分数

| 指标 | 分数 | 含义 |
|------|------|------|
| **faithfulness** | **0.8750** | 回答是否忠实于检索上下文 |
| **answer_relevancy** | **0.8858** | 回答与问题的相关程度 |

### 6.3 运行状态

- Agent 生成阶段：3/3 条样本均正常完成  
- RAGAS 打分阶段：6/6 个 Job 全部完成，无超时异常  
- 每条样本 `retrieved_contexts_count` 均为 1  

### 6.4 报告路径

| 文件 | 说明 |
|------|------|
| `evals/out/ragas_report.json` | 机器可读，含 `summary`、`samples`、`eval_config` |
| `evals/out/ragas_report.md` | 人类可读的 Markdown 版本 |

### 6.5 结果解读（如实说明）

- 本次评估基于 **3 条样本、1 份 PDF**，属于阶段性基线，不能代表全量 10 条样本或任意文档上的泛化表现。
- `make eval-ragas` 默认仅跑 `relevancy` 单指标；正式基线以 `metrics=all` 报告为准。
- `faithfulness` 需额外 LLM 判分，耗时明显长于 `answer_relevancy`；扩大样本数时存在超时风险，脚本会在 `metrics=faithfulness` 时自动切换逐条串行模式。
- 报告 JSON 中 `summary` 可能以 `raw_result` 字符串形式呈现，分数含义不变。

---

## 7. 当前限制

| 限制 | 说明 |
|------|------|
| **进程级知识库** | FAISS 索引与 chunk 保存在内存，`kb_registry` 不做落盘；重启即失 |
| **无持久化数据库** | 未接入 Redis、PostgreSQL 或外部向量库 |
| **LoRA 模型未接入** | 生成与评估均使用 DashScope 在线 API（`qwen-plus`），未加载本地微调权重 |
| **Memory 非服务端持久化** | 多轮对话依赖客户端传递 `history`，无跨会话用户记忆 |
| **文档结构工具为启发式** | `list_headings`、`count_tables` 基于切块文本规则，不解析 PDF 原生结构 |
| **RAGAS 样本规模有限** | 当前基线仅 3 条样本，faithfulness 全量评估较慢 |
| **无鉴权与限流** | HTTP 接口对公网开放时不具备生产级安全防护 |
| **无 CI/CD** | Smoke Test 与 RAGAS 需手动触发，未接入自动化流水线 |

---

## 8. 后续优化方向

1. **持久化知识库** — 将 FAISS 索引与元数据落盘，或接入 Chroma / Milvus 等向量数据库，支持重启恢复。  
2. **接入微调模型** — 将 `llm-finetune-manual` 产出的 LoRA 权重接入 Agent `answer` 节点，支持本地推理与线上一致性对比。  
3. **扩充评估样本** — 将 `evals/ragas_samples.json` 扩展至全量 10 条乃至更多，覆盖多跳推理与结构类问题。  
4. **CI/CD 集成** — 在流水线中自动执行 `make smoke`，并对 RAGAS 基线分数做回归对比。  
5. **生产化补强** — 鉴权、限流、日志结构化、知识库 TTL 管理等（按实际部署需求逐步引入）。

---

## 9. 与 llm-finetune-manual 的关系说明

### 9.1 两个项目的定位

| 项目 | 路径 | 职责 |
|------|------|------|
| **rag-agent**（本仓库） | `rag-agent/` | Agentic RAG 问答服务：PDF 上传、FAISS 检索、LangGraph Agent、RAGAS 评估、Docker 部署 |
| **llm-finetune-manual** | `../llm-finetune-manual/` | 独立微调实验：PDF → Alpaca 数据集 → Qwen2-7B LoRA CPU 微调验证 |

### 9.2 关系边界

- 两个仓库**代码独立、依赖独立、部署独立**，不存在代码引用或共享运行时。
- 二者在业务上同属「PDF 技术手册知识处理」链路的不同阶段：微调仓库解决「如何让模型更懂手册内容」，本仓库解决「如何基于手册内容进行可检索、可推理的问答」。
- **当前 LoRA 微调模型尚未接入 rag-agent**。本仓库的 Agent 生成节点与 RAGAS 评估均调用 DashScope 在线 API，未加载 `llm-finetune-manual/outputs/` 下的 adapter 权重。
- **Day 5 RAGAS 指标（faithfulness 0.8750、answer_relevancy 0.8858）仅反映 rag-agent 在 DashScope API 下的 Agent 问答表现**，与微调实验的训练 loss 或微调前后对比结果无直接关联。

### 9.3 预期衔接方式（尚未实现）

后续若接入微调模型，大致路径为：

```text
llm-finetune-manual 产出 LoRA adapter
        ↓
rag-agent Agent answer 节点切换为本地推理（或兼容 API 端点）
        ↓
重新运行 RAGAS，与当前 DashScope 基线对比
```

该衔接列入第 8 节优化方向，**不属于本期已交付能力**。

---

## 附录：关键命令速查

```bash
# 本地启动
make run

# Docker 启动
make docker-up

# 端到端验收
make smoke

# RAGAS 全量指标评估（Day 5 同款配置）
make eval-ragas RAGAS_LIMIT=3 RAGAS_METRICS=all RAGAS_TIMEOUT=600
```
