from __future__ import annotations

from typing import Annotated, Any, Literal

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class MaintenanceAgentState(TypedDict, total=False):
    """Shared state for the maintenance workflow."""

    messages: Annotated[list[AnyMessage], add_messages]

    user_id: str | None
    user_input: str
    machine_id: str
    session_id: str | None

    knowledge_base_id: str | None
    document_id: str | None
    collection_id: str | None
    retriever_version: Literal["v1", "v2"]
    top_k: int
    use_rerank: bool

    sensor_data: dict[str, Any]
    intent: str
    retrieve_query: str
    need_retrieval: bool
    need_prediction: bool

    retrieved_chunks: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    confidence: float
    health_result: dict[str, Any]
    risk_level: str
    risk_score: float | None

    maintenance_plan: list[str]
    draft_answer: str
    ticket: dict[str, Any] | None
    history: dict[str, Any]

    tools_used: list[str]
    errors: list[str]
    final_answer: str
    debug: dict[str, Any]
