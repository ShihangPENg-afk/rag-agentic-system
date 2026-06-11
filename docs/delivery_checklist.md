# rag-agent 交付清单

> 最后核对：2026-06-10  
> 关联文档：[final_report.md](final_report.md) · [README.md](../README.md)

---

## 交付状态总览

| 类别 | 状态 |
|------|------|
| 核心功能 | 已完成 |
| 容器化与验收 | 已完成 |
| 文档与配置模板 | 已完成 |
| 生产化 / 扩展能力 | 未完成（见第 11 节） |

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
- [x] `docker-compose.yml` 存在（端口 `8000:8000`、`env_file`、healthcheck）
- [x] `make docker-up` 可构建镜像并后台启动容器 `rag-agent`
- [x] `make docker-down` / `make docker-logs` 可用
- [x] 容器 healthcheck 探测 `GET /health`

**验收命令：**

```bash
make env-check && make docker-up
curl -fsS http://127.0.0.1:8000/health
```

**已知约束：** 知识库在进程内存中，容器重启后需重新上传 PDF。

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
- [x] Day 5 基线评估已完成（`metrics=all`，`limit=3`，`eval_timeout=600`）
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
- [x] 含 API 示例（`/upload_pdf/`、`/ask/`、`/ask_rag/`）
- [x] 含 RAGAS Day 5 结果与报告路径
- [x] 含与 `llm-finetune-manual` 的关系说明
- [x] 含当前限制与后续计划

---

## 9. .env.example

- [x] `.env.example` 存在
- [x] 仅含占位符 `your_dashscope_api_key_here`，无真实 Key
- [x] 含 `DASHSCOPE_BASE_URL`、`MODEL_NAME` 示例
- [x] `make env-init` 可在 `.env` 不存在时从模板复制
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

## 11. 当前未完成项

以下能力**不在本期交付范围内**，或仅有规划、尚未实现：

### 基础设施与持久化

- [ ] 知识库持久化（FAISS 索引落盘或接入外部向量数据库）
- [ ] 外部数据库（Redis / PostgreSQL 等）
- [ ] 服务端跨会话 Memory 持久化
- [ ] 生产级鉴权、限流与访问控制

### 模型与评估

- [ ] 接入 `llm-finetune-manual` 产出的 LoRA 微调模型
- [ ] RAGAS 全量 10 条样本评估（当前基线仅 3 条）
- [ ] RAGAS 自动化回归（faithfulness 大规模评估仍较慢，易超时）

### 工程化

- [ ] CI/CD 流水线（自动 Smoke Test / RAGAS 对比）
- [ ] Git 仓库初始化与提交规范（本地目录曾未初始化 Git）
- [ ] `.gitignore` 补强（`outputs/`、`data/` 等，与 `.dockerignore` 对齐）

### 功能增强

- [ ] PDF 原生目录 / 表格解析（当前 `list_headings`、`count_tables` 为启发式）
- [ ] 多副本部署与负载均衡

---

## 签收参考

全部 **第 1–10 节** 勾选项满足后，可认为 rag-agent **Day 6 核心交付完成**。第 11 节未完成项作为后续迭代 backlog，不影响当前 Agentic RAG 演示与验收结论。

**推荐最终验收顺序：**

```bash
make env-check
make docker-up
make smoke
make eval-ragas RAGAS_LIMIT=3 RAGAS_METRICS=all RAGAS_TIMEOUT=600
```
