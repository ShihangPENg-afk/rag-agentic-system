# 当前项目审计报告

审计范围：基于当前仓库静态阅读完成。除本报告文件外，未修改任何业务代码。

## 1. 当前项目的入口文件

当前后端主入口是：

- `main.py`
  - 导入 `app.api.routes` 中的 `app`
  - 直接运行时调用 `uvicorn.run(app, host="127.0.0.1", port=8000)`

Docker 容器入口是：

- `Dockerfile`
  - `CMD ["uvicorn", "app.api.routes:app", "--host", "0.0.0.0", "--port", "8000"]`

辅助入口包括：

- `ui/streamlit_app.py`：Streamlit 演示 UI
- `evals/run_ragas_eval.py`：RAGAS 评估脚本
- `test_langgraph_agent.py`、`test_retrieval_tool.py`、`test_document_tools.py`：本地手工验证脚本
- `Makefile`：封装本地运行、Docker、测试、冒烟和评估命令

## 2. FastAPI app 是在哪里创建的

FastAPI app 在 `app/api/routes.py` 中创建：

```python
app = FastAPI(
    title="RAG PDF 智能问答系统",
    description="基于FastAPI的PDF知识库问答服务",
    lifespan=lifespan,
)
```

同一文件中还定义了 `lifespan`。服务启动时会调用 `create_tables()` 初始化 PostgreSQL 表结构；如果数据库不可用，会记录 warning，并允许核心 RAG 功能继续运行。

## 3. 当前已有 API 路由列表

API 路由集中定义在 `app/api/routes.py`：

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/upload_pdf/` | 上传单个 PDF，校验文件名、大小、PDF magic header，并构建知识库 |
| `POST` | `/upload_pdfs/` | 批量上传多个 PDF，并逐个构建知识库 |
| `POST` | `/ask/` | Agent 问答主入口，使用 LangGraph Agent |
| `POST` | `/ask_rag/` | 经典 RAG 问答入口，作为回退模式 |
| `GET` | `/documents/` | 查询最近上传文档记录，数据来自 PostgreSQL |
| `GET` | `/qa_logs/` | 按知识库 ID 查询历史问答日志，数据来自 PostgreSQL |
| `GET` | `/knowledge_bases` | 获取当前进程内知识库列表 |
| `DELETE` | `/knowledge_base/{kb_id}` | 删除当前进程内指定知识库 |
| `DELETE` | `/clear_all_knowledge_bases` | 清空当前进程内全部知识库 |
| `GET` | `/health` | 健康检查，返回网络状态和当前内存知识库数量 |
| `GET` | `/` | API 信息与接口提示 |

## 4. 当前 RAG 流程涉及哪些文件

当前 RAG 流程是 PDF 上传后即时构建内存知识库：PDF 文本抽取 -> 文本切块 -> DashScope embedding -> FAISS index -> 基于 index 检索 -> DashScope/Qwen 生成回答。

关键文件如下：

- `app/api/routes.py`
  - 接收 PDF 上传请求
  - 校验文件名、文件大小和 PDF 文件头
  - 调用 `create_knowledge_base_from_saved_pdf()` 构建知识库
  - `/ask/` 调用 Agent 问答
  - `/ask_rag/` 调用经典 RAG 问答

- `app/services/upload_service.py`
  - 创建 `RAGSystem`
  - 调用 `RAGSystem.init_from_pdf()` 初始化知识库
  - 生成 `knowledge_base_id`
  - 注册内存知识库
  - 写入文档元数据到 PostgreSQL

- `rag.py`
  - 定义 `RAGSystem`
  - 保存 `index` 和 `chunks`
  - 暴露 `init_from_pdf()` 和 `query()`

- `app/services/pdf_service.py`
  - 使用 `pypdf.PdfReader` 提取 PDF 文本

- `app/services/index_service.py`
  - 使用 `RecursiveCharacterTextSplitter` 切块
  - 调用 DashScope `TextEmbedding` 生成向量
  - 调用 `build_faiss_index()` 构建 FAISS index

- `app/vectordb/faiss_store.py`
  - 使用 FAISS 建立向量索引

- `app/services/kb_registry.py`
  - 使用模块级字典 `knowledge_bases` 保存 `knowledge_base_id -> RAGSystem`
  - 当前 chunks 和 FAISS index 都保存在进程内内存

- `app/services/chat_service.py`
  - 经典 RAG 编排
  - 处理对话历史、追问增强、向量检索、prompt 组装和 DashScope Generation 调用

- `app/tools/retrieval_tools.py`
  - Agent 使用的检索工具
  - 复用 `chat_service.retrieve_relevant_chunks()`

- `app/tools/document_tools.py`
  - 文档结构工具
  - 基于 chunks 启发式提取章节标题、统计表格迹象

## 5. 当前 LangGraph 或 Agent 相关代码在哪里

LangGraph / Agent 相关代码主要在 `app/agent/` 和 `app/services/agent_chat_service.py`：

- `app/agent/graph.py`
  - 创建 `StateGraph(AgentState)`
  - 节点包括 `planner`、`agent`、`tools`、`evaluator`、`answer`
  - 使用 `ToolNode`
  - 定义 `after_agent()` 和 `after_evaluator()` 条件路由

- `app/agent/state.py`
  - 定义 `AgentState`
  - 包含 `messages`、`knowledge_base_id`、`chat_history_pairs`、`current_question`、`retrieved_evidence`、`memory_summary`、多跳推理状态等字段

- `app/agent/nodes.py`
  - 通过 `ChatOpenAI` 接入 DashScope OpenAI-compatible Qwen 模型
  - 定义 Agent 系统提示词
  - 注册工具：`retrieve_chunks`、`list_headings`、`count_tables`、`check_machine_health`
  - 实现 planner、agent、evaluator、answer 节点
  - 包含追问识别、多跳问题拆解、设备健康问题识别等规则逻辑

- `app/services/agent_chat_service.py`
  - 将 API 请求转换为 AgentState
  - 构建并调用 LangGraph
  - 提取最终回答、更新 history、构造 debug tool trace

- `app/tools/machine_health_tool.py`
  - 调用外部 `HEALTH_API_URL/predict`
  - 将工业设备健康预测结果格式化为工具输出

当前 Agent 能力已经不只是传统 RAG，还包括：

- 文档内容检索
- 文档结构查询
- 粗略表格统计
- 多跳问题拆解和综合
- 对话历史摘要注入
- 工业设备健康预测 API 工具调用

## 6. 当前是否使用数据库，如果使用，在哪里连接

当前使用数据库：PostgreSQL + SQLAlchemy。

连接位置：

- `app/db/database.py`
  - 从环境变量读取 `DATABASE_URL`
  - 默认值：`postgresql+psycopg2://ragagent:ragagent_secret@localhost:5432/ragagent`
  - 创建 `engine = create_engine(DATABASE_URL, pool_pre_ping=True)`
  - 创建 `SessionLocal`

模型位置：

- `app/db/models.py`
  - `Document`
  - `QALog`

初始化位置：

- `app/db/init_db.py`
  - `Base.metadata.create_all(bind=engine)`
- `app/api/routes.py`
  - FastAPI `lifespan` 中调用 `create_tables()`

读写位置：

- `app/db/repository.py`
  - `record_document()`
  - `record_qa_log()`
  - `list_recent_documents()`
  - `list_qa_logs_by_knowledge_base()`

当前数据库只保存：

- 文档元数据：文件名、chunks 数量、状态、创建/更新时间
- 问答日志：问题、回答、模式、debug、创建时间

当前数据库没有保存：

- PDF 原文件路径或对象存储地址
- chunks 明细
- embedding 向量
- FAISS index 文件路径
- Agent 运行轨迹的结构化全量事件
- 用户、租户、权限、设备资产等平台级实体

## 7. 当前是否有 Docker / docker-compose

有。

- `Dockerfile`
  - 基于 `python:3.10-slim`
  - 安装 `libgomp1`，用于支持 `faiss-cpu` 运行
  - 安装 `requirements.txt`
  - 启动 `uvicorn app.api.routes:app`

- `docker-compose.yml`
  - `postgres` 服务：`postgres:16-alpine`
  - `rag-agentic-system` 服务：构建当前项目镜像
  - API 端口：`8000:8000`
  - PostgreSQL 端口：`5432:5432`
  - 数据卷：`postgres_data`
  - 挂载：`./data:/app/data`、`./evals/out:/app/evals/out`
  - 默认 `HEALTH_API_URL=http://host.docker.internal:8010`
  - 包含健康检查

- `Makefile`
  - 提供 `docker-up`、`docker-down`、`docker-logs`、`stack-up`、`stack-verify` 等命令

## 8. 当前是否有 pytest 测试

有，但覆盖较浅。

正式 pytest 文件：

- `tests/conftest.py`
- `tests/test_offline.py`

`tests/test_offline.py` 当前覆盖：

- `document_tools._unique_keep_order()`
- `document_tools._normalize_text()`
- `document_tools._sanitize_heading()`
- `kb_not_found_message()`

根目录还有脚本式验证文件：

- `test_retrieval_tool.py`
- `test_document_tools.py`
- `test_langgraph_agent.py`

这些脚本更接近本地验收或调试脚本，通常依赖 PDF、网络、DashScope API Key、真实模型调用或外部服务，不等价于稳定 CI 单元测试。

当前测试缺口：

- FastAPI 路由测试不足
- 上传流程测试不足
- 文件校验边界测试不足
- 数据库 repository 测试不足
- RAG 检索质量与异常分支测试不足
- LangGraph 节点、条件路由、工具调用测试不足
- Docker Compose 启动后的集成测试不足
- 工业健康预测工具的 mock 测试不足

## 9. 当前项目最大的问题是什么

最大的问题是：知识库核心状态没有工程化持久化，导致系统更像单进程 Demo，而不是可长期运行、可扩展的平台。

具体表现如下。

1. 知识库存储在进程内内存
   - `app/services/kb_registry.py` 用模块级字典保存 `RAGSystem`
   - `RAGSystem` 内部持有 FAISS index 和 chunks
   - 服务重启、容器重建、多 worker 部署都会导致知识库丢失或状态分裂

2. 数据库与知识库状态不一致
   - PostgreSQL 保存了 `documents` 和 `qa_logs`
   - 但没有保存 chunks、embedding、index 文件路径或原始 PDF 路径
   - 重启后 `/documents/` 可能仍能看到历史文档，但 `/ask/` 和 `/ask_rag/` 无法基于旧文档继续回答

3. 上传后临时 PDF 会被删除
   - `app/api/routes.py` 上传时保存到临时目录
   - 构建知识库后 finally 中删除临时目录
   - 后续无法重建索引，除非用户重新上传

4. Agent 与工具链仍偏演示型
   - 工具调用、规划、多跳拆解主要靠规则和 prompt
   - 缺少任务状态表、工具执行审计、可重试机制、超时治理和结构化事件记录
   - 对生产级排障、复盘、指标统计不够友好

5. 工业设备运维领域模型尚不完整
   - 当前只有 `check_machine_health` 一个外部预测工具
   - 缺少设备资产、传感器指标、告警、工单、维护计划、备件、产线、知识条目等核心领域对象
   - 还没有把 RAG 文档知识、实时设备数据和运维闭环统一起来

次要但重要的问题：

- `config.py` 在缺少 `DASHSCOPE_API_KEY` 时直接 raise，某些导入路径会变得不利于离线测试和服务局部启动
- 代码中仍有较多 `print()` 调试输出，缺少统一结构化日志
- 缺少 Alembic 迁移，当前用 `Base.metadata.create_all()` 初始化表结构，不利于长期演进
- 缺少认证鉴权、租户隔离和 API 权限控制
- 缺少请求限流、文件安全扫描、任务队列和后台索引任务状态管理

## 10. 如果要升级为“工业设备运维 Agent 平台”，建议的最小改造路径

目标不要一次性重写。建议按“保住现有能力 -> 补平台底座 -> 扩工业闭环”的方式做最小改造。

### 阶段 1：先把知识库从 Demo 状态升级为可恢复状态

最小改造项：

- 持久化原始文件
  - 上传 PDF 后保存到 `data/uploads/{knowledge_base_id}/original.pdf` 或对象存储
  - `documents` 表增加 `file_path`、`file_hash`、`file_size`、`mime_type`

- 持久化 chunks
  - 新增 `document_chunks` 表
  - 字段建议：`id`、`document_id`、`chunk_index`、`content`、`token_count`、`metadata`

- 持久化向量索引
  - 最小方案：FAISS index 保存到 `data/indexes/{knowledge_base_id}.faiss`
  - `documents` 表增加 `index_path`、`embedding_model`、`index_status`
  - 服务启动时根据数据库和 index 文件恢复 `kb_registry`

- 将上传建库变成可观测任务
  - 新增 `index_jobs` 表
  - 支持 `pending/running/succeeded/failed`
  - 当前可以先同步执行，但状态要落库，为后续后台队列预留接口

这样做以后，系统重启后仍能恢复知识库，是从 Demo 到平台的第一道门槛。

### 阶段 2：整理 API 与服务边界

最小改造项：

- 拆分 `app/api/routes.py`
  - `app/api/upload_routes.py`
  - `app/api/chat_routes.py`
  - `app/api/kb_routes.py`
  - `app/api/ops_routes.py`

- 保留兼容路径
  - 现有 `/upload_pdf/`、`/ask/`、`/ask_rag/` 先不要破坏
  - 新增更平台化路径，例如 `/api/v1/knowledge-bases`、`/api/v1/agent/chat`

- 把配置集中化
  - 用 Pydantic Settings 管理 `DASHSCOPE_API_KEY`、`DATABASE_URL`、`HEALTH_API_URL`
  - 避免模块 import 时直接因为缺少 API Key 失败

- 引入结构化日志
  - 统一 request id、knowledge_base_id、tool_name、latency、status

### 阶段 3：建立工业设备运维领域模型

最小领域表建议：

- `assets`：设备资产
  - 设备 ID、名称、类型、产线、位置、状态

- `sensor_readings`：传感器读数
  - 设备 ID、时间戳、指标名、指标值、单位、数据源

- `alerts`：告警事件
  - 设备 ID、告警级别、告警类型、描述、状态、触发时间、关闭时间

- `maintenance_work_orders`：维护工单
  - 设备 ID、问题描述、建议动作、负责人、状态、优先级、截止时间

- `maintenance_actions`：维护动作记录
  - 工单 ID、执行动作、执行人、执行时间、结果

- `knowledge_documents` / 复用 `documents`
  - 文档类型：说明书、维修手册、SOP、故障案例、点检规范

最小 API 建议：

- `GET /api/v1/assets`
- `GET /api/v1/assets/{asset_id}`
- `POST /api/v1/assets/{asset_id}/readings`
- `GET /api/v1/assets/{asset_id}/alerts`
- `POST /api/v1/work-orders`
- `PATCH /api/v1/work-orders/{id}`

### 阶段 4：把 Agent 从“问答 Agent”升级为“运维 Agent”

保留现有 LangGraph 架构，但增加平台工具：

- `retrieve_manual(asset_id, query)`
  - 从设备相关手册、SOP、故障案例中检索证据

- `get_asset_status(asset_id)`
  - 查询设备基础信息、当前状态、最近告警

- `get_recent_sensor_readings(asset_id, window)`
  - 查询最近传感器数据

- `predict_machine_health(asset_id | sensor_data)`
  - 封装当前 `check_machine_health_tool`
  - 支持直接按设备 ID 拉取最近传感器数据再预测

- `create_work_order(asset_id, issue, recommendation, priority)`
  - 将 Agent 建议转为工单

- `list_open_work_orders(asset_id)`
  - 查询未关闭工单，避免重复派单

LangGraph 最小改造：

- 新增 `intent_router` 节点
  - 区分文档问答、设备状态查询、故障诊断、工单创建、闲聊

- 新增 `ops_context` 节点
  - 根据 `asset_id` 汇总设备、告警、传感器、历史工单上下文

- 新增 `action_guard` 节点
  - 对创建工单、关闭告警等写操作做确认或权限检查

- 保留现有 `planner -> agent -> tools -> evaluator -> answer` 主结构

### 阶段 5：补测试和交付保障

最小测试路径：

- 给 FastAPI 增加 `TestClient` 路由测试
- 对数据库 repository 使用临时测试库或 SQLite 兼容层测试
- 对 DashScope embedding / chat 调用做 mock
- 对 LangGraph 的关键路径做工具 mock 测试
- 对 `check_machine_health_tool` 使用 `responses` 或 `requests-mock` 测试成功、超时、连接失败、HTTP 错误
- 给 Docker Compose 增加 smoke test，覆盖 `/health`、上传、问答、文档列表

### 推荐的最小落地顺序

1. 持久化 PDF、chunks、FAISS index，并实现服务启动恢复知识库。
2. 增加 Alembic，替代长期依赖 `create_all()`。
3. 拆分路由模块，保留现有 API 兼容。
4. 增加设备资产、传感器、告警、工单四类核心表。
5. 把 `check_machine_health_tool` 改造成可按 `asset_id` 工作的平台工具。
6. 在 LangGraph 中加入工业运维 intent router 和 action guard。
7. 补齐 API、DB、Agent 工具、Docker smoke 的自动化测试。

完成以上七步后，项目可以从“PDF RAG + 简单设备预测 Demo”升级为“可恢复、可审计、可扩展的工业设备运维 Agent 平台 MVP”。
