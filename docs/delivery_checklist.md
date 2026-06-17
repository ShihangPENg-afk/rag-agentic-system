# rag-agentic-system 验收清单

> 最后核对：2026-06-11  
> 关联文档：[final_report.md](final_report.md) · [README.md](../README.md) · [ui_demo_guide.md](ui_demo_guide.md)

---

## 验收状态总览

| 类别 | 状态 |
|------|------|
| 核心功能 | 已完成 |
| Streamlit UI | 已完成 |
| PostgreSQL 混合持久化 | 已完成（元数据 + QA 日志；向量仍为 FAISS） |
| 容器化与验收 | 已完成 |
| 文档与配置模板 | 已完成 |
| 生产化 / 扩展能力 | 未完成（见「当前未完成项」） |

---

## 1. 本地运行

- [x] `make install` 可创建 `.venv` 并安装 `requirements.txt`
- [x] `make env-init` / `make env-check` 可初始化并校验 `.env`
- [x] `make run`（或 `python main.py`）可启动服务，监听 `http://127.0.0.1:8000`
- [x] `/docs` 与 `/openapi.json` 可正常访问
- [x] 依赖 DashScope API Key 与网络可达（`config.py` 启动时校验 Key）

**验收命令：**

```bash
make install && make env-check && make run
```

---

## 2. Docker 运行

- [x] `Dockerfile` 存在（`python:3.10-slim` + `libgomp1` + uvicorn）
- [x] `docker-compose.yml` 存在（`rag-agentic-system` + `postgres:16-alpine`）
- [x] API 端口 `8000:8000`，PostgreSQL 端口 `5432:5432`
- [x] `rag-agentic-system` 通过 `DATABASE_URL` 连接 `postgres` 服务（`depends_on` + healthcheck）
- [x] `make docker-up` 可构建镜像并后台启动容器
- [x] `make docker-down` / `make docker-logs` 可用
- [x] 容器 healthcheck 探测 `GET /health`

**验收命令：**

```bash
make env-check && make docker-up
curl -fsS http://127.0.0.1:8000/health
docker compose ps   # postgres 与 rag-agentic-system 均为 healthy / running
```

**已知约束：** **FAISS 向量索引**在 API 进程内存中，容器重启后需重新上传 PDF 才能问答；**PostgreSQL** 中的 `documents` / `qa_logs` 记录会保留。

---

## 3. Smoke Test

- [x] `scripts/smoke_test.sh` 存在
- [x] `make smoke` 可执行端到端冒烟测试
- [x] 四步全部通过（2026-06-10，Docker 环境下验收）

| 步骤 | 检查项 | 状态 |
|------|--------|------|
| 1/4 | `/openapi.json` 或 `/docs` 可达 | 通过 |
| 2/4 | `POST /upload_pdf/` 上传 `test.pdf` | 通过 |
| 3/4 | 解析 `knowledge_base_id` | 通过 |
| 4/4 | `POST /ask/` 返回 `answer` 且 `mode=agent` | 通过 |

**验收命令：**

```bash
make smoke
# 预期输出：Smoke Test 全部通过 (4/4)
```

**备注：** 上传与向量化通常需 2–4 分钟，服务须先启动。

---

## 4. PDF 上传

- [x] `POST /upload_pdf/` 单文件上传可用
- [x] `POST /upload_pdfs/` 批量上传可用
- [x] 校验 `.pdf` 扩展名与 `%PDF` 魔数
- [x] 上传后自动切块、向量化并注册知识库（`test.pdf` → 83 块）
- [x] 响应返回 `knowledge_base_id`、`chunks_count`、`status`

**验收示例：**

```bash
curl -X POST "http://127.0.0.1:8000/upload_pdf/" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@test.pdf"
```

---

## 5. Agent 问答

- [x] `POST /ask/` 为默认主入口（LangGraph Agent）
- [x] Agent 图节点：`planner → agent ⇄ tools → evaluator → answer`
- [x] 工具可用：`retrieve_chunks`、`list_headings`、`count_tables`
- [x] 多步推理：`planner` 拆子问题，`evaluator` 决定是否继续检索
- [x] 对话 Memory：请求体 `history` 保留最近 3 轮
- [x] 响应 `mode` 为 `"agent"`，返回更新后的 `history`
- [x] `POST /ask_rag/` 经典 RAG 回退链路可用（对照基线）

**验收示例：**

```bash
curl -X POST "http://127.0.0.1:8000/ask/" \
  -H "Content-Type: application/json" \
  -d '{"question":"这份文档主要讲什么？","knowledge_base_id":"<KB_ID>","history":[]}'
```

---

## 6. Debug trace

- [x] `/ask/` 支持请求体字段 `debug: true`
- [x] 响应 `debug` 含 `tool_trace`（工具名、输入、输出预览）
- [x] 响应 `debug` 含 `reasoning_snapshot`（子问题、检索轮次、`decision`）
- [x] 响应 `debug` 含 `retrieved_evidence_preview`
- [x] 响应 `debug` 含 `memory_snapshot`
- [x] Smoke Test 第 4 步以 `debug=true` 验收通过

**验收示例：**

```bash
curl -X POST "http://127.0.0.1:8000/ask/" \
  -H "Content-Type: application/json" \
  -d '{"question":"这份文档主要讲什么？","knowledge_base_id":"<KB_ID>","history":[],"debug":true}'
```

---

## 7. RAGAS 评估

- [x] `evals/run_ragas_eval.py` 评估脚本可用
- [x] `evals/ragas_samples.json` 样本文件存在（10 条手工样本）
- [x] `make eval-ragas` 可通过 Makefile 调用
- [x] 基线评估已完成（`metrics=all`，`limit=3`，`eval_timeout=600`，2026-06-10）
- [x] 报告已生成

| 指标 | 分数 |
|------|------|
| faithfulness | **0.8750** |
| answer_relevancy | **0.8858** |

| 报告文件 | 状态 |
|----------|------|
| `evals/out/ragas_report.json` | 已生成 |
| `evals/out/ragas_report.md` | 已生成 |

**验收命令：**

```bash
make eval-ragas RAGAS_LIMIT=3 RAGAS_METRICS=all RAGAS_TIMEOUT=600
```

**备注：** 默认 `make eval-ragas` 仅跑 `relevancy` 单指标；正式基线以 `metrics=all` 为准。当前仅评估 3/10 条样本。

---

## 8. README

- [x] `README.md` 已更新至项目展示级别
- [x] 含项目简介（Agentic RAG）
- [x] 含核心功能、技术栈、架构概览
- [x] 含本地启动、Docker 启动、Smoke Test 说明
- [x] 含 **Streamlit UI** 启动方法（`ui/streamlit_app.py`）
- [x] 含 **PostgreSQL 混合持久化**说明（向量 FAISS / 元数据与日志 PG）
- [x] 含 API 示例（`/upload_pdf/`、`/ask/`、`/ask_rag/`、`/documents/`、`/qa_logs/`）
- [x] 含 RAGAS 基线结果与报告路径（3/10 样本）
- [x] 含与 `llm-finetune-manual` 的关系说明（**未接入 LoRA**）
- [x] 含当前限制与后续计划

---

## 9. .env.example

- [x] `.env.example` 存在
- [x] 仅含占位符 `your_dashscope_api_key_here`，无真实 Key
- [x] 含 `DASHSCOPE_BASE_URL`、`MODEL_NAME` 示例
- [x] 含 `POSTGRES_*`、`DATABASE_URL`（混合持久化，非向量存储）
- [x] `make env-init` 可在 `.env` 不存在时从模板复制；已有 `.env` 可补全 PG 变量
- [x] `.gitignore` 已忽略 `.env`

**文件路径：** `.env.example`

---

## 10. .dockerignore

- [x] `.dockerignore` 存在
- [x] 排除 `.venv/`、`venv/`
- [x] 排除 `.env`、`.env.*`（保留 `!.env.example`）
- [x] 排除 `data/`、`evals/out/`、`outputs/`
- [x] 排除 `.git/`、IDE 配置、缓存与临时文件

**文件路径：** `.dockerignore`

---

## 11. Streamlit UI

- [x] `ui/streamlit_app.py` 存在，依赖 `ui/requirements-ui.txt`
- [x] 侧边栏可配置 `API_BASE_URL`，检测 `/openapi.json` 连通性
- [x] 支持 PDF 上传 → 调用 `POST /upload_pdf/` 构建 FAISS 向量库
- [x] 「聊天」页多轮 Agent 问答，默认 `debug=true`，可展开 Debug Trace 四面板
- [x] 侧边栏区分 **可用知识库**（内存 FAISS）与 **历史文档**（仅 PG 记录）
- [x] 「历史记录」页调用 `GET /qa_logs/` 展示 PostgreSQL 持久化问答
- [x] 「调试说明」页列出相关 API 与连接状态
- [x] 录屏步骤文档：`docs/ui_demo_guide.md`

**验收命令：**

```bash
# 终端 1
make env-check && docker compose up postgres -d && make run

# 终端 2
source .venv/bin/activate
pip install -r ui/requirements-ui.txt
streamlit run ui/streamlit_app.py
# 浏览器打开 http://127.0.0.1:8501
```

**手动验收：** 上传 `test.pdf` → 提问并展开 Debug → 「历史记录」可见 QA 日志 → 重启 `make run` 后历史仍在但需重新上传才可问答。

---

## 12. PostgreSQL 混合持久化

> **边界：** 向量检索仍使用进程内 **FAISS**；PostgreSQL **仅**保存文档元信息与 QA 日志，**不存储向量或 chunk 正文**。

- [x] `app/db/models.py`：`documents`、`qa_logs` 表定义
- [x] `app/db/repository.py`：`record_document`、`record_qa_log`、`list_recent_documents`、`list_qa_logs_by_knowledge_base`
- [x] 启动时 `create_tables()` 自动建表（DB 不可用时降级，不影响核心 RAG）
- [x] 上传成功写入 `documents`（`upload_service` → `record_document`）
- [x] `POST /ask/` 成功后写入 `qa_logs`（含可选 `debug` JSONB）
- [x] `GET /documents/`、`GET /qa_logs/` API 可用
- [x] `docker-compose.yml` 含 `postgres` 服务与 `postgres_data` 卷
- [x] `.env.example` 含 `DATABASE_URL` 与 `POSTGRES_*` 变量

**验收命令：**

```bash
docker compose up postgres -d
make run   # 另终端

# 上传并问答（可用 make smoke 或 UI）
make smoke

# 查询 PG 元数据与日志
curl -fsS "http://127.0.0.1:8000/documents/?limit=5"
curl -fsS "http://127.0.0.1:8000/qa_logs/?knowledge_base_id=<KB_ID>&limit=5"

# 对比：内存中可问答知识库（FAISS）
curl -fsS http://127.0.0.1:8000/knowledge_bases
```

**重启验证：** 停止并重启 API 后，`/knowledge_bases` 为空或不含旧 ID，但 `/documents/` 与 `/qa_logs/` 仍可返回历史记录。

---

## 13. UI 录屏演示文档

- [x] `docs/ui_demo_guide.md` 已创建
- [x] 含录屏前环境准备与服务启动步骤
- [x] 含分步演示脚本（上传、问答、Debug、历史、可选重启对比）
- [x] 明确 FAISS / PostgreSQL 职责边界
- [x] 未声称 LoRA 已接入

---

## 14. 当前未完成项

以下能力**不在当前版本范围内**，或仅有规划、尚未实现：

### 基础设施与持久化

- [ ] **FAISS / 向量持久化**（索引落盘或接入专用向量数据库；当前向量仅在内存）
- [ ] 服务端跨会话 Memory 自动注入（当前依赖客户端 `history` + QA 日志查询）
- [ ] 生产级鉴权、限流与访问控制
- [ ] Redis 等缓存层

### 模型与评估

- [ ] 接入 `llm-finetune-manual` 产出的 LoRA 微调模型
- [ ] RAGAS 10 条样本完整评估（当前基线仅 3/10 条）
- [ ] RAGAS 自动化回归（faithfulness 大规模评估仍较慢，易超时）

### 工程化

- [ ] CI/CD 流水线（自动 Smoke Test / RAGAS 对比）
- [ ] `.gitignore` 补强（与 `.dockerignore` 对齐）

### 功能增强

- [ ] PDF 原生目录 / 表格解析（当前 `list_headings`、`count_tables` 为启发式）
- [ ] 多副本部署与负载均衡

---

## 15. 工业预测联动（industrial-health-demo）

- [x] `check_machine_health` 工具注册于 Agent（`app/tools/machine_health_tool.py`）
- [x] HTTP 调用 `HEALTH_API_URL/predict`（默认 `:8010`），无内嵌 ML 模型
- [x] Streamlit「设备健康预测」Tab 可直连工业 API
- [x] `make stack-up` / `make stack-verify` 双服务验收脚本
- [x] `docs/industrial_demo_guide.md` 演示文档

**验收命令：**

```bash
make stack-verify
# 预期：rag-agentic-system :8000 与 industrial-health :8010 均通过
```

---

## 签收参考

全部核心勾选项（含 PostgreSQL 混合持久化、Streamlit UI、工业预测联动）满足后，可认为 rag-agentic-system **当前版本功能验收通过**。「当前未完成项」所列能力作为后续迭代 backlog；**LoRA 微调模型尚未接入 rag-agentic-system**，不影响当前 POC 验收结论。

**推荐最终验收顺序：**

```bash
make env-check
make docker-up
make smoke
curl -fsS "http://127.0.0.1:8000/documents/?limit=5"
make eval-ragas RAGAS_LIMIT=3 RAGAS_METRICS=all RAGAS_TIMEOUT=600

# UI 验收（另开终端）
pip install -r ui/requirements-ui.txt && streamlit run ui/streamlit_app.py
# 按 docs/ui_demo_guide.md 走一遍演示流程
```
