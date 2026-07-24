from __future__ import annotations

from functools import lru_cache
from typing import Any
from uuid import UUID

from langchain_core.messages import HumanMessage

from app.agents.maintenance_agent.graph import build_maintenance_graph
from app.services.chat_service import persist_chat_exchange


@lru_cache(maxsize=1)
def get_maintenance_graph():
    return build_maintenance_graph()


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
) -> dict[str, Any]:
    """Invoke the maintenance graph and persist the chat exchange when possible."""
    state = {
        "messages": [HumanMessage(content=user_input)],
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
    }

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

    return {
        "final_answer": final_answer,
        "risk_level": result.get("risk_level", "unknown"),
        "tools_used": result.get("tools_used", []),
        "sources": result.get("sources", []),
        "session_id": persisted_session_id,
        "confidence": result.get("confidence", 0.0),
        "maintenance_plan": result.get("maintenance_plan", []),
        "ticket": result.get("ticket"),
        "debug": result.get("debug", {}),
    }
