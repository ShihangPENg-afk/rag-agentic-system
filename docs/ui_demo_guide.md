# Streamlit UI 演示指南

> 适用版本：Industrial Maintenance Agent Platform<br>
> 关联文档：[README.md](../README.md) · [delivery_checklist.md](delivery_checklist.md)

本文档用于本地演示，不包含未经复现的效果指标。

## 1. 演示目标

展示一条可运行的 AI 应用链路：

1. 登录或注册本地用户，获取 JWT。
2. 通过 Streamlit 上传 PDF，后端写入 PostgreSQL + pgvector。
3. 在同一文档上调用 RAG + LangGraph Agent 问答。
4. 展开 Debug Trace 查看工具调用、证据和推理状态。
5. 查看 PostgreSQL 中的 QA 历史记录。
6. 可选：调用 predictive-maintenance-mini 的健康预测接口。

## 2. 启动服务

### Docker Compose 启动后端栈

```bash
make env-init
# 编辑 .env，至少配置 DASHSCOPE_API_KEY、POSTGRES_USER、POSTGRES_PASSWORD、JWT_SECRET_KEY
make docker-up
```

确认 API 可访问：

```bash
curl -fsS http://127.0.0.1:8000/health
```

### 启动 Streamlit

```bash
source .venv/bin/activate
pip install -r ui/requirements-ui.txt
export API_BASE_URL=http://127.0.0.1:8000
export HEALTH_API_URL=http://127.0.0.1:8010
make ui
```

浏览器访问 `http://127.0.0.1:8501`。

## 3. 演示步骤

### 步骤 1：登录

1. 打开 Streamlit 页面，标题为 `Industrial Maintenance Agent Platform`。
2. 侧边栏确认后端 `/openapi.json` 可访问。
3. 在“用户登录”区域输入邮箱和密码。
4. 首次演示可点击“注册并登录”；已有账号点击“登录”。

说明：文档列表、上传、问答和历史记录都需要 JWT。

### 步骤 2：上传 PDF

1. 侧边栏“知识库构建”选择 `test.pdf` 或自备 PDF。
2. 点击“构建 / 更新向量库”。
3. 成功后会返回 `knowledge_base_id`、`chunks_count` 和文件名。
4. 文档会出现在文档列表中。

后端实际调用主路径：`POST /documents/upload`。旧路径 `/upload_pdf/` 仍保留为兼容入口。

### 步骤 3：RAG + LangGraph Agent 问答

1. 在“聊天”Tab 中确认当前文档状态。
2. 输入问题，例如：`这份文档主要讲什么？`
3. 等待回答返回。
4. 展开“Agent 推理步骤 / Debug Trace”。

Debug Trace 中重点查看：

- 工具轨迹：是否调用 `retrieve_chunks`、`list_headings`、`count_tables` 或 `check_machine_health`。
- 推理快照：`sub_queries`、`retrieval_round`、`decision`。
- 证据预览：RAG 检索到的 chunk 片段。
- 记忆快照：当前问题和最近 history。

### 步骤 4：历史记录

1. 切换到“历史记录”Tab。
2. 选择刚上传的文档。
3. 点击“刷新历史”。
4. 展示问题、回答、mode 和可展开的 debug 数据。

历史记录来自 PostgreSQL。RAG 检索所需 chunks 和 embeddings 也会持久化到 PostgreSQL + pgvector。

### 步骤 5：设备健康预测

如果已启动 `predictive-maintenance-mini`：

```bash
cd ../predictive-maintenance-mini
make docker-up
```

回到 Streamlit 的“设备健康预测”Tab：

1. 确认 `HEALTH_API_URL=http://127.0.0.1:8010`。
2. 点击“获取模型信息”。
3. 输入或保留特征值。
4. 点击“预测设备健康状态”。

该 Tab 是直接调用预测服务。Agent 工作流中的健康检查则通过 `check_machine_health` Tool 调用同一个 `/predict` 接口。

## 4. 可用问题

| 类型 | 示例问题 |
| --- | --- |
| 概述 | 这份文档主要讲什么？ |
| 细节 | 文档中如何定义关键概念？ |
| 结构 | 文档里有哪些章节标题？ |
| 表格迹象 | 文档中有多少处表格相关内容？ |
| 健康预测 | 请根据 temperature=75, pressure=1.2, vibration=0.6 判断设备风险 |

问题需要尽量贴合上传 PDF 的内容。健康预测类问题应提供明确传感器数值。

## 5. 常见问题

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 文档列表或上传返回 401 | 未登录或 token 失效 | 重新登录 |
| 后端连接失败 | API 未启动或端口错误 | 检查 `make docker-up` / `make run` 和 `API_BASE_URL` |
| 上传耗时较长 | PDF 解析和 embedding 需要时间 | 使用较小 PDF 或等待请求完成 |
| 问答返回证据不足 | 文档不包含相关内容或 top_k 太小 | 换问题、换文档或调整请求参数 |
| 健康预测连接失败 | predictive-maintenance-mini 未启动 | 启动 sibling repo 并确认 `8010` 可访问 |

## 6. 录屏提示

- 展示 JWT 登录、PDF 上传、RAG + LangGraph Agent 问答、Debug Trace 和历史记录即可。
- 不需要口头承诺固定效果提升比例。
- LoRA 只说明为独立实验仓库，当前未接入默认问答链路。
