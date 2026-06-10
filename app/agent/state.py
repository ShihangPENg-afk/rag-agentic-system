"""
LangGraph Agent 状态模型。

与 app/schemas/chat_state.py（Pydantic、面向单次 RAG 流水线）不同，
本模块为 StateGraph 提供 TypedDict 状态，其中 messages 通过 add_messages 做增量合并。

使用 total=False：图中各节点可按需读写字段，未传入的键不会触发「缺少必填键」类错误，
便于分阶段填充 Memory 相关上下文（历史、摘要、检索证据等）以及多跳推理中间状态。
"""
from __future__ import annotations

from typing import Annotated

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class AgentState(TypedDict, total=False):
    """
    RAG Agent 在 StateGraph 中的共享状态。

    字段说明（Memory）：
    - messages:
        LangGraph/LangChain 的消息流（用户、AI、工具消息）。
        使用 add_messages 做增量合并。
    - knowledge_base_id:
        当前会话绑定的知识库 ID。
    - chat_history_pairs:
        显式保存 API 层传入的历史轮次，格式为 [(user, assistant), ...]
    - current_question:
        当前用户问题，便于节点逻辑明确访问，而不是总从 messages 反推。
    - retrieved_evidence:
        当前轮检索到的证据片段（可做 debug 或后续 evaluator 使用）。
    - memory_summary:
        对最近几轮历史的摘要文本，用于 SystemMessage 注入。

    字段说明（多步推理）：
    - sub_queries:
        将复杂问题拆解后的子查询列表，供多跳检索逐条执行。
    - current_sub_query_index:
        当前正在处理的子查询在 sub_queries 中的下标（从 0 起）。
    - need_multi_hop:
        规划节点判定：是否需要进入多跳检索/推理分支。
    - evidence_by_sub_query:
        按子查询文本聚合的检索证据，键为子查询、值为该子查询对应的 chunk 列表。
    - retrieval_round:
        已完成的检索轮次计数，用于循环控制与日志。
    - max_retrieval_rounds:
        允许的最大检索轮次上限，防止无限循环。
    - decision:
        路由/规划节点的决策标签（如 continue_retrieve、synthesize、end 等），供 conditional_edges 使用。
    """

    # LangGraph 对话轨迹：用户/助手/工具消息；节点返回局部列表时由 add_messages 追加合并
    messages: Annotated[list[AnyMessage], add_messages]
    # 当前会话绑定的知识库 ID，供 retrieve_chunks_tool 等检索与文档工具使用
    knowledge_base_id: str
    # 结构化多轮历史：(用户问题, 助手回答) 列表，供 Memory 节点拼 prompt 或做摘要输入
    chat_history_pairs: list[tuple[str, str]]
    # 本轮待回答的用户问题（可与 messages 中最后一条 human 对齐，便于 Memory/RAG 节点单独读取）
    current_question: str
    # 本轮 RAG 检索到的证据片段（chunk 文本），供生成节点引用或写入 Memory
    retrieved_evidence: list[str]
    # 长对话压缩后的记忆摘要，供 agent 在上下文窗口有限时携带更早轮次的信息
    memory_summary: str

    # 规划节点拆解出的子查询列表，多跳时按序逐条检索
    sub_queries: list[str]
    # 当前执行到 sub_queries 的第几条（0-based），驱动「下一子查询」推进
    current_sub_query_index: int
    # 是否启用多跳路径：True 时走子查询循环，False 时可用单次检索
    need_multi_hop: bool
    # 每个子查询对应的检索证据池；键为子查询原文，值为该查询下命中的 chunk 文本列表
    evidence_by_sub_query: dict[str, list[str]]
    # 当前已执行的检索轮数（含多轮子查询轮次），与 max_retrieval_rounds 配合做终止判断
    retrieval_round: int
    # 检索循环上限，超过后应停止继续 retrieve 并进入综合/回答节点
    max_retrieval_rounds: int
    # 规划或路由节点的离散决策，供 conditional_edges 映射到下一节点名
    decision: str
