# Streamlit UI 录屏演示指南

> 适用版本：rag-agent（含 PostgreSQL 混合持久化与工业预测联动）  
> 关联文档：[README.md](../README.md) · [delivery_checklist.md](delivery_checklist.md)

---

## 1. 演示目标

向观众展示以下能力（约 **8–12 分钟**）：

1. 通过浏览器上传 PDF，构建 **FAISS 向量库**并完成 Agent 问答  
2. 展开 **Debug Trace**，说明 Agent 工具调用与多步推理  
3. 进行 **多轮对话**，体现 `history` 记忆  
4. 在「历史记录」页查看 **PostgreSQL** 中持久化的 QA 日志  
5. （可选）模拟 **后端重启**，说明向量丢失但数据库记录仍在  

**务必强调：** 向量检索使用进程内 **FAISS**；PostgreSQL **仅**保存文档元信息（`documents`）与问答日志（`qa_logs`），**不存储向量**。

---

## 2. 录屏前准备

### 2.1 环境与文件

| 项 | 要求 |
|----|------|
| Python | 3.10+，已执行 `make install` |
| API Key | `.env` 中 `DASHSCOPE_API_KEY` 为真实值（`make env-check` 通过） |
| PostgreSQL | 已启动（见下方命令） |
| 演示 PDF | 项目根目录 `test.pdf`（或自备小体积 PDF） |
| 浏览器 | Chrome / Edge，窗口宽度 ≥ 1280px（Streamlit 为 `layout="wide"`） |
| 录屏 | 建议 1920×1080，同时录制浏览器与两个终端（或分镜剪辑） |

### 2.2 启动服务

**终端 A — PostgreSQL（若未用 Docker 全栈）：**

```bash
cd rag-agent
docker compose up postgres -d
```

**终端 B — FastAPI 后端：**

```bash
make env-check && make run
```

确认 `http://127.0.0.1:8000/docs` 可打开。

**终端 C — Streamlit UI：**

```bash
source .venv/bin/activate
pip install -r ui/requirements-ui.txt
streamlit run ui/streamlit_app.py
```

浏览器访问 `http://127.0.0.1:8501`。

> 若使用 `make docker-up`，终端 B 可改为 Docker 日志监控；Streamlit 仍在宿主机启动并指向 `http://127.0.0.1:8000`。

### 2.3 录屏设置建议

- 关闭无关通知；终端字体放大便于观众阅读  
- 侧边栏与主区域均需在画面中（知识库选择与聊天区）  
- 上传与首次问答可能耗时 **2–4 分钟**，可剪接或提前跑通一次「热身」  

---

## 3. 推荐演示脚本（按顺序操作）

### 步骤 1：介绍页面与后端连接（≈1 分钟）

1. 打开 Streamlit 首页，标题为 **「Agentic RAG 文档问答助手」**。  
2. 指向侧边栏 **「后端连接」**：应显示绿色 **「后端 /openapi.json 可访问」**。  
3. 口头说明：`API_BASE_URL` 默认 `http://127.0.0.1:8000`，UI 只调 HTTP API，不直连数据库或 FAISS。

**解说要点：** 后端负责 PDF 切块、FAISS 向量化与 LangGraph Agent；PostgreSQL 异步写入元数据与日志。

---

### 步骤 2：上传 PDF 构建向量库（≈2–4 分钟）

1. 侧边栏 **「知识库构建」** → 选择 `test.pdf`。  
2. 点击 **「构建 / 更新向量库」**，等待 spinner 结束。  
3. 展示成功提示与 **「当前知识库状态」**：  
   - `knowledge_base_id`  
   - `chunks_count`（如 83 块）  
   - 绿色 **「当前知识库已在后端内存中加载，可以问答」**  
4. 点击 **「刷新列表」**，侧边栏 **「可用知识库」** 出现 🟢 条目；caption 显示「后端内存中可用：1 个 · 数据库记录：1 条」。

**解说要点：** 上传同时写入 **FAISS（内存）** 与 **PostgreSQL documents 表**；二者职责不同。

---

### 步骤 3：单轮问答 + Debug Trace（≈2 分钟）

1. 切到主区 **「聊天」** 标签。  
2. 输入示例问题：**「这份文档主要讲什么？」**  
3. 等待回答出现后，展开 **「Agent 推理步骤 / Debug Trace」**。  
4. 依次简要展示四个子面板：  
   - **工具轨迹**：如 `retrieve_chunks`  
   - **推理快照**：`sub_queries`、`decision`、`retrieval_round`  
   - **记忆快照**：当前问题与 history 摘要  
   - **证据预览**：检索到的 chunk 片段  

**解说要点：** UI 默认 `debug=true`，便于演示 Agent 非单链路 RAG。

---

### 步骤 4：多轮追问（≈1–2 分钟）

1. 在同一知识库下继续提问，例如：  
   - 第一轮已在步骤 3 完成  
   - 第二轮：**「软件由哪三个要素构成？」** 或文档相关的追问  
2. 展示聊天区保留上一轮上下文；Debug 中 **记忆快照** 的 history 数量增加。

**解说要点：** 多轮由请求体 `history` 传递，服务端保留最近 3 轮；同时 `/ask/` 会将本轮 QA 写入 PostgreSQL。

---

### 步骤 5：历史问答（PostgreSQL）（≈2 分钟）

1. 切换到 **「历史记录」** 标签。  
2. 在下拉框选择刚使用的知识库；点击 **「刷新历史」**。  
3. 展示列表中的问答条目（含 `mode: agent`、时间戳）。  
4. 展开某条的 **Debug Trace**，说明与聊天页一致的数据来自 **`qa_logs` 表**。  
5. 阅读 caption：**「历史记录来自 PostgreSQL，不要求当前可问答」**。

**解说要点：** 即使后端重启导致 FAISS 清空，历史问答仍可在此查看（若数据库正常）。

---

### 步骤 6：（可选）重启后端，对比内存与数据库（≈2 分钟）

1. 在终端 B **停止并重新启动** `make run`（或 `docker compose restart rag-agent`）。  
2. Streamlit 侧边栏点击 **「刷新列表」**。  
3. 展示现象：  
   - **「可用知识库」** 为空或仅剩需重新上传的提示  
   - **「历史文档」** expander 中出现 ⚠️ 条目（仅有数据库记录）  
   - **「当前知识库状态」** 红色提示：向量索引未加载  
4. **「历史记录」** 标签仍可看到步骤 5 的 QA 日志。  
5. 重新上传同一 PDF，恢复 🟢 可问答状态（会生成**新的** `knowledge_base_id`）。

**解说要点：** 这是混合持久化的核心边界 — **FAISS 不持久化**，**PostgreSQL 不存向量**；要恢复检索必须重新上传。

---

### 步骤 7：调试说明页收尾（≈30 秒）

1. 打开 **「调试说明」** 标签。  
2. 快速展示 API 列表（`/documents/`、`/qa_logs/`、`/knowledge_bases` 等）。  
3. 结束语：完整 API 与 Docker 部署见 README；LoRA 微调**尚未接入 rag-agent**，生成仍走 DashScope `qwen-plus`。

---

## 4. 示例问题清单（可替换）

| 类型 | 示例问题 |
|------|----------|
| 概述 | 这份文档主要讲什么？ |
| 细节 | 软件工程的三要素是什么？ |
| 结构 | 文档里有哪些章节标题？（触发 `list_headings`） |
| 表格 | 文档中有多少处表格相关内容？（触发 `count_tables`） |

根据实际 PDF 内容调整，避免无法从文档回答的问题。

---

## 5. 常见问题（录屏时可提前说明）

| 现象 | 原因 | 处理 |
|------|------|------|
| 侧边栏后端红色不可访问 | API 未启动或端口错误 | 检查 `make run` 与 `API_BASE_URL` |
| 上传超时 | 向量化耗时长 | 等待或换小 PDF；超时上限 300s |
| 有历史记录但无法问答 | 后端重启后 FAISS 丢失 | 重新上传 PDF |
| 历史记录为空 | PostgreSQL 未启动或建表失败 | `docker compose up postgres -d`，查看 API 日志 |
| 与 LoRA 关系 | 本仓库未接入微调权重 | 问答仍用 DashScope 在线 API |

---

## 6. 验收自检（录屏前跑一遍）

```bash
# 后端健康
curl -fsS http://127.0.0.1:8000/health

# 文档元数据（PostgreSQL）
curl -fsS "http://127.0.0.1:8000/documents/?limit=5"

# 内存中可问答知识库（FAISS）
curl -fsS http://127.0.0.1:8000/knowledge_bases
```

UI 手动检查：上传 → 问答 → 历史记录有数据 → Debug 可展开。

---

## 7. 交付物说明

录屏完成后，建议文件名包含日期与场景，例如：

`rag-agent-ui-demo-2026-06-11.mp4`

可与 [delivery_checklist.md](delivery_checklist.md) 中 UI 与 PostgreSQL 验收项一并提交。
