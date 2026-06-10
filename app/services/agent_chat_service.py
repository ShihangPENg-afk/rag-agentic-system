from __future__ import annotations

from typing import Any, Dict, List, Tuple

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent.graph import build_agent_graph
from app.schemas.api_models import QuestionRequest
from app.services.kb_registry import get_all_ids, get_knowledge_base

MAX_HISTORY = 3
TOOL_OUTPUT_PREVIEW_LENGTH = 300
EVIDENCE_PREVIEW_LENGTH = 200


def _history_to_messages(request: QuestionRequest) -> list:
    """
    把 API history 转成 LangChain 消息列表：
    user -> HumanMessage
    assistant -> AIMessage
    """
    messages = []
    for turn in request.history:
        if turn.user:
            messages.append(HumanMessage(content=str(turn.user)))
        if turn.assistant:
            messages.append(AIMessage(content=str(turn.assistant)))
    return messages


def _build_memory_summary(history_pairs: List[Tuple[str, str]], max_turns: int = 3) -> str:
    """
    把最近几轮对话整理成简短文本，供 SystemMessage 注入。
    """
    if not history_pairs:
        return ""

    lines = ["最近对话历史摘要："]
    recent = history_pairs[-max_turns:]
    for i, (q, a) in enumerate(recent, 1):
        answer_preview = a if len(a) <= 120 else a[:120] + "..."
        lines.append(f"第{i}轮用户：{q}")
        lines.append(f"第{i}轮助手：{answer_preview}")
    return "\n".join(lines)


def build_agent_state_from_request(request: QuestionRequest) -> dict:
    """
    从 API 请求构造 AgentState 风格的输入状态。
    """
    history_pairs: List[Tuple[str, str]] = [
        (item.user, item.assistant) for item in request.history
    ]

    input_messages = _history_to_messages(request)
    input_messages.append(HumanMessage(content=request.question))

    return {
        "messages": input_messages,
        "knowledge_base_id": request.knowledge_base_id,
        "chat_history_pairs": history_pairs,
        "current_question": request.question,
        "retrieved_evidence": [],
        "memory_summary": _build_memory_summary(history_pairs),

        "sub_queries": [],
        "current_sub_query_index": 0,
        "need_multi_hop": False,
        "evidence_by_sub_query": {},
        "retrieval_round": 0,
        "max_retrieval_rounds": 3,
        "decision": "",
    }


def _extract_final_answer(messages: list) -> str:
    """
    尽量取“最后一条真正用于回答用户的 AIMessage”。
    优先取没有 tool_calls 的 AIMessage。
    """
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            tool_calls = getattr(msg, "tool_calls", None)
            if not tool_calls and msg.content:
                return str(msg.content)

    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            return str(msg.content)

    return "未找到最终回答。"


def _build_tool_trace(messages: list) -> List[Dict[str, Any]]:
    """
    从消息流中提取工具调用轨迹，便于 debug。
    """
    trace: List[Dict[str, Any]] = []
    pending_by_call_id: Dict[str, Dict[str, Any]] = {}

    for msg in messages:
        if isinstance(msg, AIMessage):
            tool_calls = getattr(msg, "tool_calls", None) or []
            for call in tool_calls:
                entry = {
                    "tool_name": call.get("name"),
                    "tool_input": call.get("args", {}),
                    "tool_output_preview": None,
                }
                trace.append(entry)

                call_id = call.get("id")
                if call_id:
                    pending_by_call_id[call_id] = entry

        elif isinstance(msg, ToolMessage):
            preview = str(msg.content)
            if len(preview) > TOOL_OUTPUT_PREVIEW_LENGTH:
                preview = preview[:TOOL_OUTPUT_PREVIEW_LENGTH] + "..."

            call_id = getattr(msg, "tool_call_id", None)
            if call_id and call_id in pending_by_call_id:
                pending_by_call_id[call_id]["tool_output_preview"] = preview
            else:
                trace.append(
                    {
                        "tool_name": getattr(msg, "name", "unknown_tool"),
                        "tool_input": None,
                        "tool_output_preview": preview,
                    }
                )

    return trace


def _extract_retrieved_evidence(messages: list) -> List[str]:
    """
    从 ToolMessage 中提取证据预览，供 debug 观察。
    """
    evidence = []
    for msg in messages:
        if isinstance(msg, ToolMessage):
            text = str(msg.content).strip()
            if not text:
                continue
            preview = text if len(text) <= EVIDENCE_PREVIEW_LENGTH else text[:EVIDENCE_PREVIEW_LENGTH] + "..."
            evidence.append(preview)
    return evidence[:5]


def chat_with_agent_state(request: QuestionRequest) -> dict:
    """
    Agent 问答主入口：
    1. 校验知识库
    2. 构造显式 memory state
    3. 调用 LangGraph
    4. 提取 answer / history / debug
    """
    rag_system = get_knowledge_base(request.knowledge_base_id)
    if rag_system is None:
        available_ids = get_all_ids()
        raise LookupError(
            f"知识库不存在: {request.knowledge_base_id}。可用知识库ID: {available_ids[:5]}..."
        )

    input_state = build_agent_state_from_request(request)

    graph = build_agent_graph(
        knowledge_base_id=request.knowledge_base_id,
        chat_history_pairs=input_state["chat_history_pairs"],
    )

    result = graph.invoke(input_state)

    final_messages = result["messages"]
    answer = _extract_final_answer(final_messages)

    updated_history: List[Tuple[str, str]] = input_state["chat_history_pairs"] + [
        (request.question, answer)
    ]
    updated_history = updated_history[-MAX_HISTORY:]

    debug_payload = None
    if request.debug:
        debug_payload = {
            "message_count": len(final_messages),
            "memory_snapshot": {
                "current_question": input_state["current_question"],
                "chat_history_pairs": input_state["chat_history_pairs"][-MAX_HISTORY:],
                "memory_summary": input_state["memory_summary"],
    },
    "retrieved_evidence_preview": _extract_retrieved_evidence(final_messages),
    "tool_trace": _build_tool_trace(final_messages),
    "reasoning_snapshot": {
        "sub_queries": result.get("sub_queries", []),
        "current_sub_query_index": result.get("current_sub_query_index", 0),
        "retrieval_round": result.get("retrieval_round", 0),
        "decision": result.get("decision", ""),
        "evidence_by_sub_query": result.get("evidence_by_sub_query", {}),
    },
}

    return {
        "answer": answer,
        "history": updated_history,
        "debug": debug_payload,
    }