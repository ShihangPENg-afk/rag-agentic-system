from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.maintenance_agent import tools
from app.agents.maintenance_agent.state import MaintenanceAgentState


RETRIEVAL_MARKERS = (
    "手册",
    "说明书",
    "章节",
    "报警",
    "告警",
    "故障",
    "原因",
    "维修",
    "维护",
    "保养",
    "零件",
    "部件",
    "检查",
    "建议",
)

PREDICTION_MARKERS = (
    "风险",
    "预测",
    "健康",
    "传感器",
    "温度",
    "振动",
    "压力",
    "电流",
    "预警",
    "异常",
)


def _append_tool(state: MaintenanceAgentState, tool_name: str) -> list[str]:
    tools_used = list(state.get("tools_used", []))
    if tool_name not in tools_used:
        tools_used.append(tool_name)
    return tools_used


def _append_error(state: MaintenanceAgentState, error: str | None) -> list[str]:
    errors = list(state.get("errors", []))
    if error and error not in errors:
        errors.append(error)
    return errors


def _classify_intent(question: str) -> str:
    if any(marker in question for marker in ("风险", "预测", "健康", "传感器")):
        return "risk_prediction"
    if any(marker in question for marker in ("报警", "告警", "预警")):
        return "alarm_analysis"
    if any(marker in question for marker in ("手册", "说明书", "章节")):
        return "manual_lookup"
    if any(marker in question for marker in ("维护", "保养", "维修", "建议")):
        return "maintenance_advice"
    if any(marker in question for marker in ("故障", "异常", "原因")):
        return "fault_diagnosis"
    if any(marker in question for marker in ("零件", "部件", "检查")):
        return "part_inspection"
    return "general"


def _intake_node(state: MaintenanceAgentState) -> dict[str, Any]:
    question = str(state.get("user_input") or "").strip()
    intent = _classify_intent(question)
    need_retrieval = bool(state.get("knowledge_base_id")) and (
        intent != "general" or any(marker in question for marker in RETRIEVAL_MARKERS)
    )
    need_prediction = bool(state.get("sensor_data")) or any(
        marker in question for marker in PREDICTION_MARKERS
    )

    return {
        "user_input": question,
        "retrieve_query": question,
        "intent": intent,
        "need_retrieval": need_retrieval,
        "need_prediction": need_prediction,
        "risk_level": "unknown",
        "errors": [] if question else ["user_input 不能为空"],
        "tools_used": [],
    }


def _history_node(state: MaintenanceAgentState) -> dict[str, Any]:
    history = tools.list_history(
        user_id=state.get("user_id"),
        session_id=state.get("session_id"),
    )
    return {
        "history": history,
        "tools_used": _append_tool(state, "list_history"),
        "errors": _append_error(state, history.get("error")),
    }


def _retrieve_node(state: MaintenanceAgentState) -> dict[str, Any]:
    result = tools.retrieve_manual(
        query=state.get("retrieve_query") or state.get("user_input", ""),
        knowledge_base_id=state.get("knowledge_base_id"),
        user_id=state.get("user_id"),
        document_id=state.get("document_id"),
        collection_id=state.get("collection_id"),
        retriever_version=state.get("retriever_version", "v2"),
        top_k=state.get("top_k", 5),
        use_rerank=state.get("use_rerank", True),
    )
    return {
        "retrieved_chunks": result.get("chunks", []),
        "sources": result.get("sources", []),
        "confidence": float(result.get("confidence") or 0.0),
        "tools_used": _append_tool(state, "retrieve_manual"),
        "errors": _append_error(state, result.get("error")),
    }


def _health_node(state: MaintenanceAgentState) -> dict[str, Any]:
    result = tools.check_machine_health(
        machine_id=state.get("machine_id", ""),
        sensor_data=state.get("sensor_data") or {},
    )
    return {
        "health_result": result,
        "risk_level": result.get("risk_level", "unknown"),
        "risk_score": result.get("risk_score"),
        "tools_used": _append_tool(state, "check_machine_health"),
    }


def _plan_node(state: MaintenanceAgentState) -> dict[str, Any]:
    result = tools.generate_maintenance_plan(
        user_input=state.get("user_input", ""),
        machine_id=state.get("machine_id", ""),
        retrieved_chunks=state.get("retrieved_chunks", []),
        health_result=state.get("health_result", {}),
        history=state.get("history", {}),
    )
    return {
        "maintenance_plan": result.get("plan", []),
        "draft_answer": result.get("answer", ""),
        "risk_level": result.get("risk_level", state.get("risk_level", "unknown")),
        "tools_used": _append_tool(state, "generate_maintenance_plan"),
    }


def _ticket_node(state: MaintenanceAgentState) -> dict[str, Any]:
    ticket = tools.create_ticket_mock(
        machine_id=state.get("machine_id", ""),
        user_input=state.get("user_input", ""),
        risk_level=state.get("risk_level", "unknown"),
        maintenance_plan=state.get("maintenance_plan", []),
        user_id=state.get("user_id"),
        session_id=state.get("session_id"),
    )
    return {
        "ticket": ticket,
        "tools_used": _append_tool(state, "create_ticket_mock"),
    }


def _finalize_node(state: MaintenanceAgentState) -> dict[str, Any]:
    answer = str(state.get("draft_answer") or "").strip()
    if not answer:
        answer = (
            f"已收到设备 {state.get('machine_id', '')} 的运维问题。"
            "当前基础维护 Agent 未调用真实 LLM，请补充知识库或传感器数据后继续分析。"
        )

    ticket = state.get("ticket")
    if ticket:
        answer += (
            f"\n\n已生成模拟工单：{ticket['ticket_id']}。"
            "该工单未调用外部系统，仅用于流程演示。"
        )

    debug = {
        "intent": state.get("intent"),
        "confidence": state.get("confidence", 0.0),
        "retrieved_chunk_count": len(state.get("retrieved_chunks", [])),
        "health_result": state.get("health_result", {}),
        "ticket": ticket,
        "errors": state.get("errors", []),
    }
    return {
        "final_answer": answer,
        "risk_level": state.get("risk_level", "unknown"),
        "tools_used": list(state.get("tools_used", [])),
        "sources": list(state.get("sources", [])),
        "confidence": float(state.get("confidence", 0.0) or 0.0),
        "debug": debug,
    }


def _after_history(state: MaintenanceAgentState) -> str:
    if state.get("need_retrieval"):
        return "retrieve_manual"
    if state.get("need_prediction"):
        return "check_machine_health"
    return "generate_maintenance_plan"


def _after_retrieval(state: MaintenanceAgentState) -> str:
    if state.get("need_prediction"):
        return "check_machine_health"
    return "generate_maintenance_plan"


def _after_plan(state: MaintenanceAgentState) -> str:
    if str(state.get("risk_level", "")).lower() in {"high", "critical"}:
        return "create_ticket_mock"
    return "finalize"


def build_maintenance_graph():
    graph = StateGraph(MaintenanceAgentState)
    graph.add_node("intake", _intake_node)
    graph.add_node("list_history", _history_node)
    graph.add_node("retrieve_manual", _retrieve_node)
    graph.add_node("check_machine_health", _health_node)
    graph.add_node("generate_maintenance_plan", _plan_node)
    graph.add_node("create_ticket_mock", _ticket_node)
    graph.add_node("finalize", _finalize_node)

    graph.add_edge(START, "intake")
    graph.add_edge("intake", "list_history")
    graph.add_conditional_edges(
        "list_history",
        _after_history,
        [
            "retrieve_manual",
            "check_machine_health",
            "generate_maintenance_plan",
        ],
    )
    graph.add_conditional_edges(
        "retrieve_manual",
        _after_retrieval,
        ["check_machine_health", "generate_maintenance_plan"],
    )
    graph.add_edge("check_machine_health", "generate_maintenance_plan")
    graph.add_conditional_edges(
        "generate_maintenance_plan",
        _after_plan,
        ["create_ticket_mock", "finalize"],
    )
    graph.add_edge("create_ticket_mock", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile()
