# 当前项目审计记录

本文档记录仓库当前结构和保留边界，用于投递前自查。它不是功能承诺，也不写未经验证的性能结论。

## 1. 入口与服务

| 项 | 当前文件 |
| --- | --- |
| FastAPI app | `app/main.py` |
| 路由聚合 | `app/api/routes.py` |
| Docker API 启动 | `Dockerfile` 中 `uvicorn app.main:app` |
| 本地入口兼容 | 根目录 `main.py` |
| Streamlit UI | `ui/streamlit_app.py` |
| Alembic | `alembic/versions/20260723_0003_add_pgvector_knowledge_base.py` 为当前 head |

FastAPI OpenAPI 标题为 `Industrial Maintenance Agent Platform`。

## 2. 当前 API 模块

| 文件 | 路由范围 |
| --- | --- |
| `app/api/routes_auth.py` | `/auth/register`、`/auth/login`、JWT 用户依赖 |
| `app/api/upload.py` | `/documents/upload`、兼容 `/upload_pdf/`、批量上传 `/upload_pdfs/` |
| `app/api/routes_documents.py` | `/documents/`、`/documents/retrieve`、`/documents/{document_id}`、`/qa_logs/` |
| `app/api/routes_chat.py` | `/ask`、`/chat`、`/ask/stream`、`/ask_rag/`、chat session 查询 |
| `app/api/routes_agent.py` | `/agent/invoke`、`/agent/stream`、`/agent/confirm` |
| `app/api/routes_feedback.py` | `/feedback` |
| `app/api/knowledge_base.py` | 进程内知识库兼容查询和清理 |
| `app/api/health.py` | `/health` 和根路径接口提示 |

## 3. RAG 实现现状

上传 PDF 后的主流程：

```text
PDF -> text extraction -> chunking -> embeddings -> PostgreSQL documents/chunks -> pgvector chunk_embeddings
```

当前主检索：

- v1 pgvector baseline：`app/retrievers/retriever_v2_pgvector.py`
- v2 hybrid + rerank：`app/retrievers/retriever_v2_hybrid.py` 与 `app/retrievers/rerank.py`
- FAISS fallback：`app/retrievers/retriever_v1_faiss.py` 与 `app/vectordb/faiss_store.py`

说明：FAISS 仍有价值，因为它表达早期 baseline 和兼容 fallback；不应误写成当前唯一向量库。

## 4. Agent 实现现状

通用 RAG + LangGraph Agent：

- 图定义：`app/agent/graph.py`
- 节点与工具绑定：`app/agent/nodes.py`
- API 服务包装：`app/services/agent_chat_service.py`
- 工具：`retrieve_chunks`、`list_headings`、`count_tables`、`check_machine_health`

工业运维 Agent：

- 图定义：`app/agents/maintenance_agent/graph.py`
- 状态：`app/agents/maintenance_agent/state.py`
- 工具：`app/agents/maintenance_agent/tools.py`
- 服务层：`app/services/agent_service.py`

该 Agent 负责意图判断、手册检索、设备健康检查、维护计划和高风险确认。当前工单为 mock ticket，不调用真实外部系统。

## 5. 数据库与缓存

PostgreSQL + pgvector 保存：

- users
- documents
- collections
- chunks
- chunk_embeddings
- qa_logs
- chat_sessions
- chat_messages
- feedback

Redis 用于 chat 接口用户级限流。当前实现中 Redis 不可用时会放行请求并记录 warning，保证本地 Demo 可继续使用。

## 6. 已清理内容

这次整理中保留核心功能，移除或移动的内容如下：

- 删除旧的未挂载重复路由：`app/api/chat.py`、`app/api/documents.py`。
- 删除空工具文件：`utils/network_utils.py`、`utils/text_utils.py`。
- 将根目录手动检查脚本移动到 `scripts/manual/`，避免被误认为 pytest 单测。
- 删除本地生成缓存：`__pycache__`、`.pytest_cache`。
- 删除过期报告 `docs/final_report.md`，因为它描述的是旧版 FAISS-only、匿名接口和旧 Docker 配置。

## 7. 仍需注意的边界

- Streamlit 是本地演示 UI，适合展示流程，不覆盖复杂企业前端能力。
- `predictive-maintenance-mini` 是独立 Tool 服务；本仓库不内嵌它的模型或训练代码。
- LoRA 位于独立仓库，当前未接入默认问答链路。
- 文档结构工具是启发式，不等于 PDF 原生目录/表格解析。
- mock rerank 与 deterministic health fallback 只用于离线测试和联调，不代表真实模型效果。

## 8. 建议验收命令

```bash
make test
make smoke
docker compose config --quiet
```

需要真实后端和用户文档时再运行：

```bash
EVAL_USER_ID=<user_id> python3 evals/evaluate_retrieval.py --top-k 5
```
