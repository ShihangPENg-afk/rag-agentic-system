# 项目总览（简历 / 面试版）

> 更新日期：2026-06-10 · 交付状态：rag-agent Day 6 核心交付已完成

围绕 **PDF 技术手册知识处理**，我完成了两个**相关但完全解耦**的独立项目：**rag-agent** 负责可检索、可推理的问答服务；**llm-finetune-manual** 负责领域微调数据与 LoRA 训练验证。二者共享业务场景，但代码、依赖与部署互不引用；**LoRA 微调模型尚未接入 rag-agent**，问答生成仍调用 DashScope 在线 API（`qwen-plus`）。

## rag-agent（Agentic RAG）

基于 **FastAPI + LangGraph + FAISS + DashScope**（`qwen-plus` 生成、TextEmbedding 向量化），实现 PDF 上传 → 切块向量化 → Agent 问答全流程：

- **主路径** `POST /ask/`：planner 拆子问题 → agent 调用 `retrieve_chunks` / `list_headings` / `count_tables` → evaluator 决定是否继续检索 → 生成答案；支持请求级 Memory（最近 3 轮 `history`）与 `debug` 工具轨迹。
- **对照基线** `POST /ask_rag/`：经典 RAG 单链路（检索 → Prompt → 生成），用于与 Agent 结果对照。
- **工程化**：Docker Compose 一键部署；4 步 Smoke Test（`make smoke`，2026-06-10 Docker 环境 4/4 通过）；Makefile 统一 `run / docker-up / smoke / eval-ragas`。
- **质量基线**：RAGAS 在 `test.pdf`（83 块）上评估 **3/10** 条样本（`metrics=all`），faithfulness **0.8750**、answer_relevancy **0.8858**（DashScope 在线 API，阶段性基线，非全量评估）。
- **已知边界**：知识库为进程内存（重启需重新上传 PDF）；无持久化存储、无 CI/CD、无生产级鉴权。

## llm-finetune-manual（LoRA 微调）

跑通 PDF → Alpaca 数据集（**132** 条）→ LLaMA-Factory LoRA 微调 → 权重保存全流程：以 Qwen2-7B-Instruct 为基座，在本地 CPU 抽样 **50** 条、1 epoch 完成流程验证，产出 adapter 权重。定位为**管线可复现验证**，非可用领域模型；before/after 评测与 GPU 全量训练尚未完成。

## 面试可强调

Agent 编排与工具化 RAG、经典 RAG 对照设计、Docker 可复现交付、RAGAS 质量基线、LoRA 数据与训练链路，以及对**已完成演示**与**未生产化边界**的清晰把控。
