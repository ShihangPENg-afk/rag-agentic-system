# Agentic RAG Architecture

## 1. 项目目标

本项目将传统的“上传 PDF → 向量检索 → 回答”流程，升级为一个带有 **记忆（Memory）**、**工具调用（Tools）**、**多步推理（Multi-step Reasoning）** 的 Agentic RAG 系统。

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

适用场景：

- 简单事实问答
- 与 Agent 结果做对照
- 排查 Agent 行为问题

---

## 3. Agent 链路

默认问答入口 `/ask/` 走 LangGraph Agent：

```text
planner -> agent -> tools -> evaluator -> answer