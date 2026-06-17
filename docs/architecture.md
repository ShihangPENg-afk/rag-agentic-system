# Agentic RAG Architecture

## 1. 项目目标

本项目将传统的「上传 PDF → 向量检索 → 回答」流程，升级为带有 **记忆（Memory）**、**工具调用（Tools）**、**多步推理（Multi-step Reasoning）** 的 Agentic RAG 系统，并通过 HTTP 集成独立的工业设备健康预测服务。

系统提供两种问答模式：

- `/ask/`：LangGraph Agent 主入口
- `/ask_rag/`：经典 RAG 回退入口

---

## 2. 经典 RAG 链路

经典链路用于基线对照与简单问答：

1. 根据 `knowledge_base_id` 获取内存中的 `RAGSystem`
2. 结合 `history` 做指代增强
3. 使用 FAISS 检索相关 chunk
4. 组装 Prompt
5. 调用 DashScope 生成答案

适用场景：简单事实问答、与 Agent 结果对照、排查 Agent 行为问题。

---

## 3. Agent 链路

默认问答入口 `/ask/` 走 LangGraph Agent：

```text
START → planner → agent ──(有 tool_calls)──→ tools → evaluator
                      └──(无 tool_calls)──────────────→ evaluator
evaluator ──(need_more_retrieval / next_sub_query)──→ agent
          └──(enough_to_answer)──────────────────────→ answer → END
```

### 3.1 Agent 工具

| 工具 | 适用场景 |
|------|----------|
| `retrieve_chunks` | 文档内容、概念、段落相关问答 |
| `list_headings` | 章节、目录、文档结构（启发式） |
| `count_tables` | 表格迹象统计（启发式） |
| `check_machine_health` | 传感器读数、设备健康、产线风险预测 |

`check_machine_health` 通过 HTTP 调用 [industrial-health-demo](https://github.com/ShihangPENg-afk/industrial-health-demo) 的 `POST /predict`（默认 `http://127.0.0.1:8010`），不在本仓库内嵌 ML 模型。

### 3.2 对话 Memory 与 Debug

- 客户端在请求体中传入 `history`，服务端保留最近 **3 轮**。
- `debug: true` 时返回 `tool_trace`、`reasoning_snapshot`、`retrieved_evidence_preview`、`memory_snapshot`。

---

## 4. 混合持久化（PostgreSQL + FAISS）

```text
上传 PDF → 切块 / 向量化 → FAISS 索引（进程内，可问答）
              │
              ├─→ PostgreSQL documents（元信息：文件名、块数、状态）
              └─→ PostgreSQL qa_logs（问答历史 + 可选 debug JSONB）
```

**边界：** 向量索引与 chunk 文本保存在**进程内存**；PostgreSQL **不**存储向量。服务重启后，历史 QA 日志仍可查询，但 FAISS 索引丢失，需重新上传 PDF 才能继续问答。

数据库不可用时，核心 RAG 与 Agent 功能仍可运行；元数据与日志写入会降级为 warning，不阻断问答。

---

## 5. Streamlit UI

`ui/streamlit_app.py` 通过 HTTP 调用后端，不直连 FAISS 或 PostgreSQL：

| 配置项 | 默认 | 用途 |
|--------|------|------|
| `API_BASE_URL` | `http://127.0.0.1:8000` | PDF 上传、聊天、Debug Trace、历史记录 |
| `HEALTH_API_URL` | `http://127.0.0.1:8010` | 「设备健康预测」Tab 直连工业 API |

---

## 6. 工业预测服务联动

```text
rag-agentic-system (:8000)                    industrial-health-demo (:8010)
  check_machine_health ──HTTP──►     POST /predict
  Streamlit 设备健康 Tab ──HTTP──►  /health · /model-info · /predict
```

两服务**解耦**：无共享进程、无共享数据库；工业 API 可独立升级或替换。

---

## 7. 部署拓扑

| 组件 | 端口 | 说明 |
|------|------|------|
| rag-agentic-system API | 8000 | FastAPI + LangGraph |
| PostgreSQL | 5432 | 元数据与 QA 日志 |
| industrial-health-demo | 8010 | 独立仓库（[GitHub](https://github.com/ShihangPENg-afk/industrial-health-demo)），Docker 部署 |
| Streamlit UI | 8501 | 宿主机启动 |

Docker Compose（rag-agentic-system 仓库）包含 `postgres` 与 `rag-agentic-system`；工业服务与 Streamlit 需单独启动。双栈验收：`make stack-verify`。

---

## 8. 当前限制

- FAISS 向量不持久化；PostgreSQL 不存向量或 chunk 正文。
- LoRA 微调模型**未接入**；生成仍走 DashScope `qwen-plus`。
- 工业预测模型为 **baseline 演示**，非生产级。
- 无生产级鉴权、限流与 CI/CD；未云部署。

更多细节见 [README.md](../README.md) 与 [industrial_demo_guide.md](industrial_demo_guide.md)。
