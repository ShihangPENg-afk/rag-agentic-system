from __future__ import annotations

from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from app.agent.nodes import (
    agent_node,
    answer_node,
    evaluator_node,
    make_agent_tools,
    planner_node,
)
from app.agent.state import AgentState


def after_agent(state: AgentState) -> str:
    messages = state.get("messages", [])
    if not messages:
        return "evaluator"

    last_message = messages[-1]
    if isinstance(last_message, AIMessage) and getattr(last_message, "tool_calls", None):
        return "tools"

    return "evaluator"


def after_evaluator(state: AgentState) -> str:
    decision = state.get("decision", "")
    if decision == "need_more_retrieval":
        return "agent"
    if decision == "next_sub_query":
        return "agent"
    return "answer"


def build_agent_graph(
    knowledge_base_id: str,
    chat_history_pairs: list[tuple[str, str]] | None = None,
):
    tools = make_agent_tools(
        knowledge_base_id=knowledge_base_id,
        history_pairs=chat_history_pairs or [],
    )
    tool_node = ToolNode(tools)

    graph = StateGraph(AgentState)

    graph.add_node("planner", planner_node)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)
    graph.add_node("evaluator", evaluator_node)
    graph.add_node("answer", answer_node)

    graph.add_edge(START, "planner")
    graph.add_edge("planner", "agent")

    graph.add_conditional_edges("agent", after_agent, ["tools", "evaluator"])
    graph.add_edge("tools", "evaluator")
    graph.add_conditional_edges("evaluator", after_evaluator, ["agent", "answer"])
    graph.add_edge("answer", END)

    return graph.compile()