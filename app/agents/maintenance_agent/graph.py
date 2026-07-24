from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.maintenance_agent import tools
from app.agents.maintenance_agent.state import MaintenanceAgentState


MANUAL_MARKERS = (
    "手册",
    "说明书",
    "章节",
    "报警",
    "告警",
    "故障",
    "维修",
    "维护",
    "保养",
    "零件",
    "部件",
    "检查",
)
HEALTH_MARKERS = ("状态", "风险", "预测", "健康", "传感器", "温度", "振动", "压力", "电流", "异常")
CONFIRM_TICKET_MARKERS = ("确认创建工单", "创建工单", "开工单", "建工单", "同意创建", "提交工单")
DECLINE_TICKET_MARKERS = ("不创建工单", "不要创建工单", "无需创建工单", "先不创建", "暂不创建")
HIGH_RISK_LEVELS = {"high", "critical"}


def _record_tools(state: MaintenanceAgentState, *names: str) -> list[str]:
    tools_used = list(state.get("tools_used", []))
    for name in names:
        if name and name not in tools_used:
            tools_used.append(name)
    return tools_used


def _record_error(state: MaintenanceAgentState, error: str | None) -> list[str]:
    errors = list(state.get("errors", []))
    if error and error not in errors:
        errors.append(error)
    return errors


def _classify_question(question: str) -> str:
    if any(marker in question for marker in ("风险", "预测", "健康", "传感器")):
        return "risk_prediction"
    if any(marker in question for marker in ("报警", "告警")):
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


def _ticket_confirmed(question: str, explicit_confirm: bool | None) -> bool:
    if explicit_confirm is True:
        return True
    if any(marker in question for marker in DECLINE_TICKET_MARKERS):
        return False
    return any(marker in question for marker in CONFIRM_TICKET_MARKERS)


def classify_intent(state: MaintenanceAgentState) -> dict[str, Any]:
    question = str(state.get("user_input") or "").strip()
    machine_id = str(state.get("machine_id") or "").strip()
    if state.get("user_id"):
        history = tools.list_history(
            user_id=state.get("user_id"),
            session_id=state.get("session_id"),
        )
    else:
        history = {}
    errors = _record_error(state, history.get("error")) if history else list(state.get("errors", []))
    if not question and "user_input 不能为空" not in errors:
        errors.append("user_input 不能为空")

    return {
        "user_input": question,
        "machine_id": machine_id,
        "intent": _classify_question(question),
        "retrieve_query": question,
        "need_retrieval": any(marker in question for marker in MANUAL_MARKERS),
        "need_prediction": bool(machine_id) or bool(state.get("sensor_data")) or any(marker in question for marker in HEALTH_MARKERS),
        "ticket_confirmed": _ticket_confirmed(question, state.get("confirm_create_ticket")),
        "risk_level": "unknown",
        "history": history,
        "errors": errors,
        "tools_used": _record_tools(state, "classify_intent", "list_history" if history else ""),
    }


def retrieve_manual_node(state: MaintenanceAgentState) -> dict[str, Any]:
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
        "errors": _record_error(state, result.get("error")),
        "tools_used": _record_tools(state, "retrieve_manual_node", "retrieve_manual"),
    }


def check_health_node(state: MaintenanceAgentState) -> dict[str, Any]:
    result = tools.check_machine_health(
        machine_id=state.get("machine_id", ""),
        sensor_data=state.get("sensor_data") or {},
    )
    return {
        "health_result": result,
        "risk_level": str(result.get("risk_level") or "unknown").lower(),
        "risk_score": result.get("risk_score"),
        "tools_used": _record_tools(state, "check_health_node", "check_machine_health"),
    }


def generate_plan_node(state: MaintenanceAgentState) -> dict[str, Any]:
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
        "tools_used": _record_tools(state, "generate_plan_node", "generate_maintenance_plan"),
    }


def require_confirmation_node(state: MaintenanceAgentState) -> dict[str, Any]:
    message = "检测到高风险。创建工单前需要用户确认；确认后请设置 confirm_create_ticket=true 或明确回复创建工单。"
    return {
        "confirmation_required": True,
        "confirmation_message": message,
        "tools_used": _record_tools(state, "require_confirmation_node"),
    }


def create_ticket_node(state: MaintenanceAgentState) -> dict[str, Any]:
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
        "confirmation_required": False,
        "tools_used": _record_tools(state, "create_ticket_node", "create_ticket_mock"),
    }


def final_response_node(state: MaintenanceAgentState) -> dict[str, Any]:
    answer = str(state.get("draft_answer") or "").strip()
    if state.get("confirmation_required") and not state.get("ticket"):
        answer = f"{answer}\n\n{state.get('confirmation_message')}".strip()
    if state.get("ticket"):
        answer = f"{answer}\n\n已生成模拟工单：{state['ticket']['ticket_id']}。"

    debug = {
        "intent": state.get("intent"),
        "need_retrieval": state.get("need_retrieval", False),
        "need_prediction": state.get("need_prediction", False),
        "ticket_confirmed": state.get("ticket_confirmed", False),
        "confidence": state.get("confidence", 0.0),
        "errors": state.get("errors", []),
    }
    return {
        "final_answer": answer or "当前未生成维护建议，请补充问题、设备或传感器信息。",
        "risk_level": state.get("risk_level", "unknown"),
        "tools_used": _record_tools(state, "final_response_node"),
        "sources": list(state.get("sources", [])),
        "confidence": float(state.get("confidence", 0.0) or 0.0),
        "debug": debug,
    }


def _after_classify(state: MaintenanceAgentState) -> str:
    if state.get("need_retrieval"):
        return "retrieve_manual_node"
    if state.get("need_prediction"):
        return "check_health_node"
    return "generate_plan_node"


def _after_retrieve(state: MaintenanceAgentState) -> str:
    if state.get("need_prediction"):
        return "check_health_node"
    return "generate_plan_node"


def _after_plan(state: MaintenanceAgentState) -> str:
    if str(state.get("risk_level", "")).lower() in HIGH_RISK_LEVELS:
        return "require_confirmation_node"
    return "final_response_node"


def _after_confirmation(state: MaintenanceAgentState) -> str:
    if state.get("ticket_confirmed"):
        return "create_ticket_node"
    return "final_response_node"


def build_maintenance_graph():
    graph = StateGraph(MaintenanceAgentState)
    graph.add_node("classify_intent", classify_intent)
    graph.add_node("retrieve_manual_node", retrieve_manual_node)
    graph.add_node("check_health_node", check_health_node)
    graph.add_node("generate_plan_node", generate_plan_node)
    graph.add_node("require_confirmation_node", require_confirmation_node)
    graph.add_node("create_ticket_node", create_ticket_node)
    graph.add_node("final_response_node", final_response_node)

    graph.add_edge(START, "classify_intent")
    graph.add_conditional_edges(
        "classify_intent",
        _after_classify,
        ["retrieve_manual_node", "check_health_node", "generate_plan_node"],
    )
    graph.add_conditional_edges(
        "retrieve_manual_node",
        _after_retrieve,
        ["check_health_node", "generate_plan_node"],
    )
    graph.add_edge("check_health_node", "generate_plan_node")
    graph.add_conditional_edges(
        "generate_plan_node",
        _after_plan,
        ["require_confirmation_node", "final_response_node"],
    )
    graph.add_conditional_edges(
        "require_confirmation_node",
        _after_confirmation,
        ["create_ticket_node", "final_response_node"],
    )
    graph.add_edge("create_ticket_node", "final_response_node")
    graph.add_edge("final_response_node", END)

    return graph.compile()
