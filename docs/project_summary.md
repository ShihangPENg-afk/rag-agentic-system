# 项目总览

本组项目围绕工业设备维护场景拆成三个独立仓库。它们可以联动演示，但代码、依赖和部署边界保持清楚。

| 仓库 | 定位 | 关系 |
| --- | --- | --- |
| `rag-agentic-system` | Industrial Maintenance Agent Platform：FastAPI、RAG、LangGraph Agent、PostgreSQL + pgvector、Redis、Streamlit | 主应用，本仓库 |
| `predictive-maintenance-mini` | 工业设备健康预测 Tool 服务，FastAPI 暴露 `POST /predict` | 本仓库通过 HTTP 调用 |
| `llm-finetune-for-manufacturing` | LoRA 微调流程验证 | 尚未接入本仓库默认问答链路 |

## rag-agentic-system

核心链路：上传设备手册 PDF 后，系统解析文本、切块、生成 embeddings，并写入 PostgreSQL + pgvector。用户提问时，FastAPI 接口调用 RAG + LangGraph Agent，Agent 可根据问题调用检索工具、文档结构工具和设备健康预测 Tool。

| 能力方向 | 当前实现 |
| --- | --- |
| API | FastAPI，JWT 鉴权，OpenAPI 文档 |
| RAG | pgvector dense retrieval，v2 hybrid retrieval，optional rerank，FAISS fallback |
| Agent | `/ask` 通用 RAG + LangGraph Agent；`/agent/*` 工业运维 Agent |
| 数据 | PostgreSQL + pgvector 保存用户、文档、chunks、embeddings、QA logs、chat sessions |
| 缓存/限流 | Redis 用户级 chat rate limit |
| UI | Streamlit 本地演示：登录、上传、问答、Debug Trace、健康预测 |
| 测试 | pytest、smoke test、retrieval evaluation、可选 RAGAS |
| 部署 | Docker Compose 启动 API、PostgreSQL + pgvector、Redis |

## predictive-maintenance-mini

该仓库是独立预测服务，主要用于演示“传感器数据 -> 健康/风险判断”的 Tool 调用方式。

本仓库调用方式：

```text
LangGraph Agent -> check_machine_health -> POST {HEALTH_API_URL}/predict
```

默认端口为 `8010`。预测结果用于工程联调和面试展示，不应直接作为设备维护决策依据。

## llm-finetune-for-manufacturing

该仓库用于验证 LoRA 数据构造和训练流程。它不改变本仓库的默认推理路径。

当前边界：

- 本仓库默认 LLM provider 仍是 DashScope 或本地 OpenAI-compatible endpoint。
- LoRA adapter 未加载到 `rag-agentic-system`。
- 不基于 LoRA 实验声明线上效果提升。

## 三仓库关系

```text
rag-agentic-system (:8000)
  FastAPI / RAG / LangGraph Agent / pgvector / Redis
        |
        | HTTP POST /predict
        v
predictive-maintenance-mini (:8010)
  Sensor features -> prediction / risk_level

llm-finetune-for-manufacturing
  LoRA workflow validation, not wired into default runtime
```

## 推荐阅读

- [README.md](../README.md)
- [architecture.md](architecture.md)
- [agent_workflow.md](agent_workflow.md)
- [rag_vs_lora.md](rag_vs_lora.md)
- [delivery_checklist.md](delivery_checklist.md)
