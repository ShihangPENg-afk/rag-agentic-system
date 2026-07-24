from __future__ import annotations

import json
import uuid
from functools import lru_cache
from typing import Any, Iterator
from uuid import UUID

from langchain_core.messages import HumanMessage

from app.agents.maintenance_agent.graph import (
    HIGH_RISK_LEVELS,
    build_maintenance_graph,
    check_health_node,
    classify_intent,
    create_ticket_node,
    final_response_node,
    generate_plan_node,
    require_confirmation_node,
    retrieve_manual_node,
)
from app.services.agent_trace_service import AgentTraceRecorder, run_node_with_trace
from app.services.chat_service import persist_chat_exchange


_PENDING_CONFIRMATIONS: dict[str, dict[str, Any]] = {}
_CONFIRMATION_DECISIONS: dict[str, dict[str, Any]] = {}


@lru_cache(maxsize=1)
def get_maintenance_graph():
    return build_maintenance_graph()


def _build_initial_state(
    *,
    user_input: str,
    machine_id: str,
    session_id: UUID | str | None = None,
    user_id: UUID | str | None = None,
    knowledge_base_id: str | None = None,
    document_id: str | None = None,
    collection_id: str | None = None,
    retriever_version: str = "v2",
    top_k: int = 5,
    use_rerank: bool = True,
    sensor_data: dict[str, Any] | None = None,
    confirm_create_ticket: bool = False,
    trace_id: str | None = None,
    trace_recorder: AgentTraceRecorder | None = None,
) -> dict[str, Any]:
    return {
        "messages": [HumanMessage(content=user_input)],
        "trace_id": trace_id,
        "trace_recorder": trace_recorder,
        "user_id": str(user_id) if user_id is not None else None,
        "user_input": user_input,
        "machine_id": machine_id,
        "session_id": str(session_id) if session_id is not None else None,
        "knowledge_base_id": knowledge_base_id,
        "document_id": document_id,
        "collection_id": collection_id,
        "retriever_version": retriever_version,
        "top_k": top_k,
        "use_rerank": use_rerank,
        "sensor_data": sensor_data or {},
        "confirm_create_ticket": confirm_create_ticket,
    }


def _persist_stream_answer(
    *,
    user_id: UUID | str | None,
    session_id: UUID | str | None,
    user_input: str,
    final_answer: str,
) -> str | None:
    if user_id is None:
        return str(session_id) if session_id is not None else None

    session = persist_chat_exchange(
        user_id=UUID(str(user_id)),
        question=user_input,
        answer=final_answer,
        session_id=session_id,
    )
    return session["id"]


def _sse(event: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


def _merge_state(state: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    state.update(update)
    return state


def _trace_context(trace_id: str | None = None) -> AgentTraceRecorder:
    return AgentTraceRecorder(trace_id=trace_id or uuid.uuid4().hex)


def _store_pending_confirmation(
    *,
    trace_id: str,
    user_id: UUID | str | None,
    session_id: UUID | str | None,
    user_input: str,
    machine_id: str,
    result: dict[str, Any],
) -> None:
    if not result.get("confirmation_required") or result.get("ticket"):
        return

    _PENDING_CONFIRMATIONS[trace_id] = {
        "trace_id": trace_id,
        "user_id": str(user_id) if user_id is not None else None,
        "session_id": str(session_id) if session_id is not None else None,
        "user_input": user_input,
        "machine_id": machine_id,
        "risk_level": result.get("risk_level", "unknown"),
        "risk_score": result.get("risk_score"),
        "maintenance_plan": result.get("maintenance_plan", []),
        "recommended_action": result.get("recommended_action", ""),
        "sources": result.get("sources", []),
        "tools_used": result.get("tools_used", []),
        "final_answer": result.get("final_answer", ""),
        "decision": "pending",
    }


def _get_pending_confirmation(
    *,
    trace_id: str,
    user_id: UUID | str | None,
) -> dict[str, Any]:
    entry = _PENDING_CONFIRMATIONS.get(trace_id)
    if entry is None:
        raise LookupError("待确认记录不存在或已处理")

    entry_user_id = entry.get("user_id")
    if entry_user_id is not None and user_id is not None and entry_user_id != str(user_id):
        raise PermissionError("待确认记录不属于当前用户")
    return entry


def _record_confirmation_decision(
    *,
    trace_id: str,
    decision: str,
    ticket: dict[str, Any] | None = None,
) -> None:
    recorder = _trace_context(trace_id)
    recorder.record(
        node_name="agent_confirm",
        tool_name="human_confirmation",
        input_summary={"trace_id": trace_id},
        output_summary={
            "decision": decision,
            "ticket_id": ticket.get("ticket_id") if ticket else None,
        },
        latency_ms=0,
        error=None,
    )


def invoke_maintenance_agent(
    *,
    user_input: str,
    machine_id: str,
    session_id: UUID | str | None = None,
    user_id: UUID | str | None = None,
    knowledge_base_id: str | None = None,
    document_id: str | None = None,
    collection_id: str | None = None,
    retriever_version: str = "v2",
    top_k: int = 5,
    use_rerank: bool = True,
    sensor_data: dict[str, Any] | None = None,
    confirm_create_ticket: bool = False,
) -> dict[str, Any]:
    """Invoke the maintenance graph and persist the chat exchange when possible."""
    trace_recorder = _trace_context()
    state = _build_initial_state(
        user_input=user_input,
        machine_id=machine_id,
        session_id=session_id,
        user_id=user_id,
        knowledge_base_id=knowledge_base_id,
        document_id=document_id,
        collection_id=collection_id,
        retriever_version=retriever_version,
        top_k=top_k,
        use_rerank=use_rerank,
        sensor_data=sensor_data,
        confirm_create_ticket=confirm_create_ticket,
        trace_id=trace_recorder.trace_id,
        trace_recorder=trace_recorder,
    )

    result = get_maintenance_graph().invoke(state)
    final_answer = result.get("final_answer", "未生成维护回答")

    persisted_session_id = str(session_id) if session_id is not None else None
    if user_id is not None:
        session = persist_chat_exchange(
            user_id=UUID(str(user_id)),
            question=user_input,
            answer=final_answer,
            session_id=session_id,
        )
        persisted_session_id = session["id"]

    _store_pending_confirmation(
        trace_id=trace_recorder.trace_id,
        user_id=user_id,
        session_id=persisted_session_id,
        user_input=user_input,
        machine_id=machine_id,
        result=result,
    )

    return {
        "final_answer": final_answer,
        "risk_level": result.get("risk_level", "unknown"),
        "tools_used": result.get("tools_used", []),
        "sources": result.get("sources", []),
        "session_id": persisted_session_id,
        "confidence": result.get("confidence", 0.0),
        "maintenance_plan": result.get("maintenance_plan", []),
        "ticket": result.get("ticket"),
        "confirmation_required": result.get("confirmation_required", False),
        "recommended_action": result.get("recommended_action", ""),
        "decision": result.get("decision", "none"),
        "trace_id": trace_recorder.trace_id,
        "debug": {
            **result.get("debug", {}),
            "trace_id": trace_recorder.trace_id,
            "trace_event_count": len(trace_recorder.events),
        },
    }


def confirm_maintenance_agent_action(
    *,
    trace_id: str,
    decision: str,
    user_id: UUID | str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Confirm or decline a pending high-risk maintenance action."""
    normalized_decision = (decision or "").strip().lower()
    if normalized_decision in {"confirm", "confirmed", "approve", "approved"}:
        normalized_decision = "confirmed"
    elif normalized_decision in {"decline", "declined", "reject", "rejected"}:
        normalized_decision = "declined"
    else:
        raise ValueError("decision must be confirmed or declined")

    entry = _get_pending_confirmation(trace_id=trace_id, user_id=user_id)
    recorder = _trace_context(trace_id)
    ticket: dict[str, Any] | None = None

    if normalized_decision == "confirmed":
        state = {
            "trace_id": trace_id,
            "trace_recorder": recorder,
            "user_id": entry.get("user_id"),
            "session_id": entry.get("session_id"),
            "user_input": entry.get("user_input", ""),
            "machine_id": entry.get("machine_id", ""),
            "risk_level": entry.get("risk_level", "unknown"),
            "maintenance_plan": entry.get("maintenance_plan", []),
            "recommended_action": entry.get("recommended_action", ""),
            "ticket_confirmed": True,
            "from_confirm_endpoint": True,
            "tools_used": list(entry.get("tools_used", [])),
        }
        _merge_state(
            state,
            run_node_with_trace(
                state,
                node_name="create_ticket_node",
                tool_name="create_ticket_mock",
                node_fn=create_ticket_node,
            ),
        )
        ticket = state.get("ticket")
        final_answer = (
            f"已确认创建模拟工单：{ticket['ticket_id']}。"
            f"推荐操作：{entry.get('recommended_action', '')}"
        )
    else:
        final_answer = (
            "已记录 decision=declined，本次不会创建工单。"
            f"推荐操作：{entry.get('recommended_action', '')}"
        )

    _record_confirmation_decision(
        trace_id=trace_id,
        decision=normalized_decision,
        ticket=ticket,
    )

    completed = {
        **entry,
        "decision": normalized_decision,
        "ticket": ticket,
        "notes": notes,
    }
    _CONFIRMATION_DECISIONS[trace_id] = completed
    _PENDING_CONFIRMATIONS.pop(trace_id, None)

    persisted_session_id = entry.get("session_id")
    if user_id is not None and persisted_session_id:
        persist_chat_exchange(
            user_id=UUID(str(user_id)),
            question="确认创建工单" if normalized_decision == "confirmed" else "拒绝创建工单",
            answer=final_answer,
            session_id=persisted_session_id,
        )

    tools_used = list(entry.get("tools_used", []))
    if normalized_decision == "confirmed":
        for tool_name in ("create_ticket_node", "create_ticket_mock"):
            if tool_name not in tools_used:
                tools_used.append(tool_name)
    if "human_confirmation" not in tools_used:
        tools_used.append("human_confirmation")

    return {
        "trace_id": trace_id,
        "decision": normalized_decision,
        "confirmation_required": False,
        "recommended_action": entry.get("recommended_action", ""),
        "risk_level": entry.get("risk_level", "unknown"),
        "ticket": ticket,
        "tools_used": tools_used,
        "sources": entry.get("sources", []),
        "session_id": persisted_session_id,
        "final_answer": final_answer,
    }


def stream_maintenance_agent_events(
    *,
    user_input: str,
    machine_id: str,
    session_id: UUID | str | None = None,
    user_id: UUID | str | None = None,
    knowledge_base_id: str | None = None,
    document_id: str | None = None,
    collection_id: str | None = None,
    retriever_version: str = "v2",
    top_k: int = 5,
    use_rerank: bool = True,
    sensor_data: dict[str, Any] | None = None,
    confirm_create_ticket: bool = False,
) -> Iterator[str]:
    """Yield SSE events for the maintenance agent workflow."""
    trace_recorder = _trace_context()
    state = _build_initial_state(
        user_input=user_input,
        machine_id=machine_id,
        session_id=session_id,
        user_id=user_id,
        knowledge_base_id=knowledge_base_id,
        document_id=document_id,
        collection_id=collection_id,
        retriever_version=retriever_version,
        top_k=top_k,
        use_rerank=use_rerank,
        sensor_data=sensor_data,
        confirm_create_ticket=confirm_create_ticket,
        trace_id=trace_recorder.trace_id,
        trace_recorder=trace_recorder,
    )

    try:
        yield _sse(
            "tool_started",
            {"trace_id": trace_recorder.trace_id, "node": "classify_intent", "tool": "classify_intent"},
        )
        _merge_state(
            state,
            run_node_with_trace(
                state,
                node_name="classify_intent",
                tool_name="classify_intent",
                node_fn=classify_intent,
            ),
        )
        yield _sse(
            "intent_classified",
            {
                "trace_id": trace_recorder.trace_id,
                "intent": state.get("intent"),
                "need_retrieval": state.get("need_retrieval", False),
                "need_prediction": state.get("need_prediction", False),
                "ticket_confirmed": state.get("ticket_confirmed", False),
                "tools_used": state.get("tools_used", []),
            },
        )
        yield _sse(
            "tool_finished",
            {"trace_id": trace_recorder.trace_id, "node": "classify_intent", "tool": "classify_intent"},
        )

        if state.get("need_retrieval"):
            yield _sse(
                "tool_started",
                {"trace_id": trace_recorder.trace_id, "node": "retrieve_manual_node", "tool": "retrieve_manual"},
            )
            _merge_state(
                state,
                run_node_with_trace(
                    state,
                    node_name="retrieve_manual_node",
                    tool_name="retrieve_manual",
                    node_fn=retrieve_manual_node,
                ),
            )
            yield _sse(
                "tool_finished",
                {
                    "trace_id": trace_recorder.trace_id,
                    "node": "retrieve_manual_node",
                    "tool": "retrieve_manual",
                    "source_count": len(state.get("sources", [])),
                    "confidence": state.get("confidence", 0.0),
                },
            )

        if state.get("need_prediction"):
            yield _sse(
                "tool_started",
                {"trace_id": trace_recorder.trace_id, "node": "check_health_node", "tool": "check_machine_health"},
            )
            _merge_state(
                state,
                run_node_with_trace(
                    state,
                    node_name="check_health_node",
                    tool_name="check_machine_health",
                    node_fn=check_health_node,
                ),
            )
            yield _sse(
                "risk_checked",
                {
                    "trace_id": trace_recorder.trace_id,
                    "risk_level": state.get("risk_level", "unknown"),
                    "risk_score": state.get("risk_score"),
                    "health_result": state.get("health_result", {}),
                },
            )
            yield _sse(
                "tool_finished",
                {"trace_id": trace_recorder.trace_id, "node": "check_health_node", "tool": "check_machine_health"},
            )

        yield _sse(
            "tool_started",
            {"trace_id": trace_recorder.trace_id, "node": "generate_plan_node", "tool": "generate_maintenance_plan"},
        )
        _merge_state(
            state,
            run_node_with_trace(
                state,
                node_name="generate_plan_node",
                tool_name="generate_maintenance_plan",
                node_fn=generate_plan_node,
            ),
        )
        yield _sse(
            "tool_finished",
            {
                "trace_id": trace_recorder.trace_id,
                "node": "generate_plan_node",
                "tool": "generate_maintenance_plan",
                "plan_count": len(state.get("maintenance_plan", [])),
            },
        )

        if str(state.get("risk_level", "")).lower() in HIGH_RISK_LEVELS:
            yield _sse(
                "tool_started",
                {"trace_id": trace_recorder.trace_id, "node": "require_confirmation_node", "tool": "human_confirmation"},
            )
            _merge_state(
                state,
                run_node_with_trace(
                    state,
                    node_name="require_confirmation_node",
                    tool_name="human_confirmation",
                    node_fn=require_confirmation_node,
                ),
            )
            yield _sse(
                "tool_finished",
                {
                    "trace_id": trace_recorder.trace_id,
                    "node": "require_confirmation_node",
                    "confirmation_required": state.get("confirmation_required", False),
                },
            )

            if state.get("ticket_confirmed"):
                yield _sse(
                    "tool_started",
                    {"trace_id": trace_recorder.trace_id, "node": "create_ticket_node", "tool": "create_ticket_mock"},
                )
                _merge_state(
                    state,
                    run_node_with_trace(
                        state,
                        node_name="create_ticket_node",
                        tool_name="create_ticket_mock",
                        node_fn=create_ticket_node,
                    ),
                )
                yield _sse(
                    "tool_finished",
                    {
                        "trace_id": trace_recorder.trace_id,
                        "node": "create_ticket_node",
                        "tool": "create_ticket_mock",
                        "ticket": state.get("ticket"),
                    },
                )

        _merge_state(state, final_response_node(state))
        persisted_session_id = _persist_stream_answer(
            user_id=user_id,
            session_id=session_id,
            user_input=user_input,
            final_answer=state.get("final_answer", ""),
        )
        _store_pending_confirmation(
            trace_id=trace_recorder.trace_id,
            user_id=user_id,
            session_id=persisted_session_id,
            user_input=user_input,
            machine_id=machine_id,
            result=state,
        )
        yield _sse(
            "final_answer",
            {
                "trace_id": trace_recorder.trace_id,
                "final_answer": state.get("final_answer", ""),
                "risk_level": state.get("risk_level", "unknown"),
                "tools_used": state.get("tools_used", []),
                "sources": state.get("sources", []),
                "session_id": persisted_session_id,
                "confirmation_required": state.get("confirmation_required", False),
                "recommended_action": state.get("recommended_action", ""),
                "decision": state.get("decision", "none"),
                "ticket": state.get("ticket"),
            },
        )
    except Exception as exc:
        yield _sse("error", {"trace_id": trace_recorder.trace_id, "message": str(exc)})
