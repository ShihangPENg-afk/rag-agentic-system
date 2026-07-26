# 投递前验收清单

> 适用项目：Industrial Maintenance Agent Platform<br>
> 关联文档：[README.md](../README.md) · [architecture.md](architecture.md) · [ui_demo_guide.md](ui_demo_guide.md)

本文档只记录当前版本应验证的事实，不写未经复现的性能提升比例。

## 1. 本地启动

| 检查项 | 命令 | 预期 |
| --- | --- | --- |
| 初始化环境 | `make env-init` | `.env` 不存在时从 `.env.example` 创建 |
| 校验配置 | `make env-check` | `.env` 存在且 API key 不是占位符 |
| 本地 API | `make run` | `uvicorn app.main:app` 监听 `127.0.0.1:8000` |
| Docker 后端栈 | `make docker-up` | API、PostgreSQL + pgvector、Redis 启动 |
| 停止 Docker 栈 | `make docker-down` | Compose 容器停止并移除 |

端口被占用时可覆盖：

```bash
API_PORT=58000 POSTGRES_PORT=55432 REDIS_PORT=56379 make docker-up
```

## 2. 核心接口验收

业务接口需要 Bearer token。先注册登录：

```bash
curl -X POST "http://127.0.0.1:8000/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@example.com","password":"password123"}'

curl -X POST "http://127.0.0.1:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@example.com","password":"password123"}'
```

| 接口 | 验收重点 |
| --- | --- |
| `POST /auth/register` | 可创建用户；重复邮箱返回 409 |
| `POST /auth/login` | 返回 `access_token` 与 `token_type` |
| `POST /documents/upload` | 带 token 上传 PDF，返回 `knowledge_base_id`、`chunks_count` |
| `DELETE /documents/{document_id}` | 只能删除当前用户文档，并级联 chunks / embeddings |
| `POST /ask` 或 `/chat` | 带 token 问答，返回 `answer`、`sources`、`mode=agent` |
| `POST /ask/stream` | 返回 SSE `final_answer` 或 `error` |
| `POST /agent/invoke` | 返回维护建议、风险等级、工具列表和 `trace_id` |
| `POST /agent/stream` | 返回节点级 SSE 事件 |
| `POST /agent/confirm` | 高风险确认后创建 mock ticket；拒绝时不创建 |
| `POST /feedback` | 记录当前用户反馈 |
| predictive service `POST /predict` | sibling repo 启动后可返回 `prediction`、`risk_level` |

## 3. 测试与评估

| 检查项 | 命令 | 说明 |
| --- | --- | --- |
| pytest | `make test` | 离线单测，不要求真实 LLM key |
| smoke test | `make smoke` | 注册登录、上传 PDF、调用 `/ask` |
| 双服务检查 | `make stack-verify` | 验证本仓库 API 与 predictive-maintenance-mini |
| 检索评估 | `EVAL_USER_ID=<user_id> python3 evals/evaluate_retrieval.py --top-k 5` | 对 v1/v2 检索输出 JSON |
| RAGAS 可选评估 | `make eval-ragas RAGAS_LIMIT=3 RAGAS_METRICS=all RAGAS_TIMEOUT=600` | 需要 LLM 与 embedding 服务可用 |

## 4. RAG 数据边界

- 当前主路径会持久化 documents、chunks 和 embeddings 到 PostgreSQL + pgvector。
- v1 pgvector baseline 是单路 dense retrieval。
- v2 hybrid 是 pgvector dense retrieval + BM25 + fusion，可选 rerank。
- FAISS 作为早期 baseline / fallback 保留，不再作为唯一知识库状态。
- Rerank 默认可使用 mock provider 验证流程，不代表真实 rerank 模型效果。

## 5. Agent 工作流验收

通用问答入口：`POST /ask`

```text
planner -> agent -> tools? -> evaluator -> agent? -> answer
```

工业运维入口：`POST /agent/invoke`

```text
classify_intent -> retrieve_manual? -> check_health? -> generate_plan -> confirmation? -> ticket? -> final_response
```

高风险确认逻辑：

- `risk_level` 为 `high` 或 `critical` 时返回 `confirmation_required=true`。
- 用户通过 `/agent/confirm` 决定是否创建 mock ticket。
- 当前 ticket 是本地模拟结果，不调用真实工单系统。

## 6. 文档投递检查

- README 开头能说明项目定位、价值和核心技术栈。
- README 和 docs 统一使用 `RAG`、`Agent`、`LangGraph`、`pgvector`、`FastAPI`。
- 不使用夸张表述或未经验证的提升比例。
- LoRA 只描述为独立实验仓库，明确未接入默认问答链路。
- predictive-maintenance-mini 描述为独立 Tool 服务，通过 HTTP 调用。

## 7. 保留的兼容路径

当前仍保留这些旧路径以避免破坏已有脚本或测试：

- `POST /upload_pdf/`：兼容上传路径，主文档使用 `/documents/upload`。
- `POST /ask/`：兼容问答路径，主文档使用 `/ask`。
- `POST /ask_rag/`：经典 RAG baseline，对照 LangGraph Agent 主路径。
