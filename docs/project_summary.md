# 项目总览

> 更新日期：2026-06-15 · 关联文档：[README.md](../README.md) · [architecture.md](architecture.md) · [industrial_demo_guide.md](industrial_demo_guide.md)

围绕 **PDF 知识处理** 与 **工业设备健康预测**，维护三个**相关但解耦**的独立 GitHub 仓库（见下表）。代码、依赖与部署互不引用；**LoRA 权重尚未接入 rag-agentic-system**，问答生成仍调用 DashScope 在线 API（`qwen-plus`）。

| 仓库 | GitHub |
|------|--------|
| rag-agentic-system | https://github.com/ShihangPENg-afk/rag-agentic-system |
| predictive-maintenance-mini | https://github.com/ShihangPENg-afk/predictive-maintenance-mini |
| llm-finetune-for-manufacturing | https://github.com/ShihangPENg-afk/llm-finetune-for-manufacturing |

## 演示视频

| 平台 | 内容 |
|------|------|
| **百度网盘** | 文件 `rag-demo.mp4` · [链接](https://pan.baidu.com/s/1G3FDGbw7h37hDuddjUFpRg) · 提取码 `iqcq` |
| **文字版 Demo** | 见 [ui_demo_guide.md](ui_demo_guide.md) 与 [industrial_demo_guide.md](industrial_demo_guide.md) |

涵盖 PDF 上传问答、Debug Trace、PostgreSQL 历史记录、设备健康预测 Tab 及 Agent 调用 `check_machine_health`。

---

## rag-agentic-system（Agentic RAG + Agent 工具集成）

基于 **FastAPI + LangGraph + FAISS + PostgreSQL + Streamlit + DashScope**，实现 PDF 上传 → 切块向量化 → Agent 问答，并通过 HTTP 联动工业预测服务：

| 能力方向 | 实现要点 |
|----------|----------|
| **RAG / Agent** | `POST /ask/`：planner → agent ⇄ tools → evaluator → answer；工具含 `retrieve_chunks`、`list_headings`、`count_tables`、**`check_machine_health`** |
| **对照基线** | `POST /ask_rag/`：经典 RAG 单链路，用于与 Agent 对照 |
| **Web 前端** | Streamlit UI：PDF 构建、多轮聊天、Debug Trace 四面板、「设备健康预测」Tab |
| **结构化日志** | PostgreSQL `documents` / `qa_logs`（含 debug JSONB）；向量检索仍为进程内 FAISS |
| **DevOps** | Docker Compose（API + PostgreSQL）；`make smoke`（4/4）；`make stack-up` / `stack-verify` 双服务栈（8000 + 8010） |
| **RAG 评估** | RAGAS 基线（`test.pdf`，3/10 样本）：faithfulness **0.8750**、answer_relevancy **0.8858** |

**工业联动：** `check_machine_health` → `app/tools/machine_health_tool.py` → `POST {HEALTH_API_URL}/predict`（默认 `http://127.0.0.1:8010`）。`debug.tool_trace` 可观测工具名、输入与输出预览；与 PDF 问答链路解耦、并存。

**已知边界：** FAISS 向量不持久化（重启需重新上传 PDF）；无 CI/CD、无生产级鉴权；LoRA 未接入。

---

## predictive-maintenance-mini（工业预测）

独立工业制造质量分类 Demo：EDA → RandomForest 训练 → MLflow → FastAPI → Docker。

| 阶段 | 产出 |
|------|------|
| EDA | `scripts/eda.py` → `docs/eda_summary.md` |
| 训练 | `artifacts/model.pkl`、`metrics.json`、`schema.json` |
| 推理 API | `:8010` — `/health`、`/model-info`、`POST /predict`（含 `prediction`、`risk_level`、`recommendation`） |
| 容器化 | `make docker-up` / `make docker-verify` |

**定位：** 传统 ML baseline，演示「能训练、能服务化、能 Docker 化」，**非生产级模型**。rag-agentic-system 通过 HTTP 调用，不内嵌训练或模型文件。

---

## llm-finetune-for-manufacturing（LoRA 微调）

跑通 PDF → Alpaca 数据集（**132** 条）→ LLaMA-Factory LoRA 微调 → 权重保存全流程：以 Qwen2-7B-Instruct 为基座，在本地 CPU 抽样 **50** 条、1 epoch 完成流程验证，产出 adapter 权重。定位为**管线可复现验证**，非可用领域模型；before/after 评测与 GPU 全量训练尚未完成。

---

## 三仓库关系

```
rag-agentic-system (:8000)          predictive-maintenance-mini (:8010)
  PDF / Agent / PG  ──HTTP──►  传感器 ML 推理
  Streamlit (:8501) ──直连──►  设备健康 Tab

llm-finetune-for-manufacturing        （独立实验，尚未接入 rag-agentic-system）
  PDF → LoRA adapter
```

---

## 核心产出

- **代码：** `rag-agentic-system`、`predictive-maintenance-mini` 双仓库可独立运行与 Docker 部署
- **文档：** [README.md](../README.md)、[ui_demo_guide.md](ui_demo_guide.md)、[industrial_demo_guide.md](industrial_demo_guide.md)、[delivery_checklist.md](delivery_checklist.md)
- **演示：** 百度网盘 `rag-demo.mp4`（见上表）
- **验收：** `make smoke`（RAG 主链路）、`make stack-verify`（双服务联动）
