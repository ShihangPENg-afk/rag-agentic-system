from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from app.retrievers import retriever_v1_faiss, retriever_v2_hybrid, retriever_v2_pgvector
from app.retrievers.confidence import build_sources, calculate_confidence
from app.services.chat_service import list_user_chat_sessions, list_user_session_messages
from app.services.kb_registry import get_knowledge_base
from app.tools.machine_health_tool import (
    check_machine_health_tool as legacy_check_machine_health,
)


def _empty_retrieval_result(error: str | None = None) -> dict[str, Any]:
    return {
        "chunks": [],
        "sources": [],
        "confidence": 0.0,
        "error": error,
        "retriever_version": None,
    }


def _format_retrieval_result(
    results: list[dict[str, Any]],
    retriever_version: str,
) -> dict[str, Any]:
    return {
        "chunks": results,
        "sources": build_sources(results),
        "confidence": calculate_confidence(results),
        "error": None,
        "retriever_version": retriever_version,
    }


def _retrieve_from_memory(
    *,
    query: str,
    knowledge_base_id: str,
    collection_id: str | None,
    top_k: int,
) -> dict[str, Any]:
    """Fallback for the legacy in-memory FAISS knowledge base."""
    rag = get_knowledge_base(knowledge_base_id)
    if rag is None or rag.index is None:
        return _empty_retrieval_result("知识库不存在或尚未初始化")

    texts, error = retriever_v1_faiss.retrieve_relevant_chunks_faiss(
        rag.index,
        rag.chunks,
        query,
    )
    if error is not None:
        return _empty_retrieval_result(error)

    results = []
    for index, content in enumerate(texts[:top_k]):
        results.append(
            {
                "chunk_id": f"faiss-{index}",
                "document_id": str(knowledge_base_id),
                "collection_id": collection_id,
                "content": content,
                "score": 0.0,
                "final_score": 0.0,
                "source_metadata": {
                    "retriever": "faiss",
                    "chunk_index": index,
                    "retrieval_sources": {"faiss": {"rank": index + 1}},
                },
            }
        )

    if not results:
        return _empty_retrieval_result("未检索到相关手册内容")
    return _format_retrieval_result(results, "v1-faiss")


def retrieve_manual(
    *,
    query: str,
    knowledge_base_id: str | None = None,
    user_id: str | None = None,
    document_id: str | None = None,
    collection_id: str | None = None,
    retriever_version: str = "v2",
    top_k: int = 5,
    use_rerank: bool = True,
) -> dict[str, Any]:
    """Retrieve maintenance-manual chunks with the current RAG stack."""
    if not query.strip():
        return _empty_retrieval_result("检索问题不能为空")
    if not knowledge_base_id and not document_id:
        return _empty_retrieval_result("未提供 knowledge_base_id 或 document_id")

    effective_document_id = document_id or knowledge_base_id
    effective_top_k = max(1, min(int(top_k), 20))
    version = (retriever_version or "v2").lower()
    errors: list[str] = []

    if user_id:
        if version == "v2":
            results, error = retriever_v2_hybrid.retrieve_similar_chunks(
                query=query,
                user_id=user_id,
                document_id=effective_document_id,
                collection_id=collection_id,
                top_k=effective_top_k,
                use_rerank=use_rerank,
            )
        else:
            results, error = retriever_v2_pgvector.retrieve_similar_chunks(
                query=query,
                user_id=user_id,
                document_id=effective_document_id,
                collection_id=collection_id,
                limit=effective_top_k,
            )

        if error is None and results:
            return _format_retrieval_result(results, version)
        if error:
            errors.append(error)

        # Keep the existing v2 -> pgvector fallback behavior.
        if version == "v2":
            results, error = retriever_v2_pgvector.retrieve_similar_chunks(
                query=query,
                user_id=user_id,
                document_id=effective_document_id,
                collection_id=collection_id,
                limit=effective_top_k,
            )
            if error is None and results:
                return _format_retrieval_result(results, "v1-pgvector-fallback")
            if error:
                errors.append(error)

    if knowledge_base_id:
        fallback = _retrieve_from_memory(
            query=query,
            knowledge_base_id=knowledge_base_id,
            collection_id=collection_id,
            top_k=effective_top_k,
        )
        if fallback["chunks"]:
            return fallback
        if fallback.get("error"):
            errors.append(str(fallback["error"]))

    return _empty_retrieval_result("; ".join(errors) or "未检索到相关手册内容")


def _parse_health_payload(raw_output: str) -> dict[str, Any] | None:
    match = re.search(r"raw_response:\s*(\{.*\})\s*$", raw_output, flags=re.S)
    if not match:
        return None

    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None

    if not isinstance(payload, dict):
        return None
    return payload


def _mock_health_result(
    *,
    machine_id: str,
    sensor_data: dict[str, Any],
) -> dict[str, Any]:
    numeric_values = {
        str(key).lower(): float(value)
        for key, value in sensor_data.items()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    }

    temperature = next(
        (
            value
            for key, value in numeric_values.items()
            if key in {"temperature", "temp", "温度"}
        ),
        None,
    )
    vibration = next(
        (
            value
            for key, value in numeric_values.items()
            if key in {"vibration", "vibration_level", "振动"}
        ),
        None,
    )

    if not numeric_values:
        return {
            "machine_id": machine_id,
            "provider": "mock",
            "prediction": "unknown",
            "risk_level": "unknown",
            "risk_score": None,
            "recommendation": "未提供有效传感器数据，暂不能完成实时风险判断。",
            "probabilities": {"unknown": 1.0},
        }

    if (temperature is not None and temperature >= 80) or (
        vibration is not None and vibration >= 0.8
    ):
        risk_level = "high"
        risk_score = 0.85
        prediction = "abnormal"
        recommendation = "建议尽快通知值班工程师，检查异常温升、振动来源及相关安全联锁。"
    elif (temperature is not None and temperature >= 65) or (
        vibration is not None and vibration >= 0.5
    ):
        risk_level = "medium"
        risk_score = 0.55
        prediction = "warning"
        recommendation = "建议安排近期点检，复核报警记录并持续观察传感器趋势。"
    else:
        risk_level = "low"
        risk_score = 0.2
        prediction = "normal"
        recommendation = "当前未发现明显高风险信号，建议按维护手册执行例行检查。"

    return {
        "machine_id": machine_id,
        "provider": "mock",
        "prediction": prediction,
        "risk_level": risk_level,
        "risk_score": risk_score,
        "recommendation": recommendation,
        "probabilities": {
            "low": max(0.0, 1.0 - risk_score),
            risk_level: risk_score,
        },
    }


def check_machine_health(
    *,
    machine_id: str,
    sensor_data: dict[str, Any] | None = None,
    provider: str | None = None,
) -> dict[str, Any]:
    """Use the existing predictive-maintenance service or a deterministic mock."""
    normalized_sensor_data = sensor_data or {}
    configured_provider = (
        provider or os.getenv("MAINTENANCE_HEALTH_PROVIDER", "mock")
    ).strip().lower()

    if configured_provider not in {"mock", "fake"} and normalized_sensor_data:
        raw_output = legacy_check_machine_health(normalized_sensor_data)
        payload = _parse_health_payload(raw_output)
        if payload is not None:
            risk_level = str(payload.get("risk_level") or "unknown").lower()
            return {
                "machine_id": machine_id,
                "provider": configured_provider,
                "prediction": payload.get("prediction", "unknown"),
                "risk_level": risk_level,
                "risk_score": payload.get("risk_score"),
                "recommendation": payload.get("recommendation"),
                "probabilities": payload.get("probabilities") or {},
            }

    result = _mock_health_result(
        machine_id=machine_id,
        sensor_data=normalized_sensor_data,
    )
    if configured_provider not in {"mock", "fake"}:
        result["provider"] = "mock-fallback"
    return result


def generate_maintenance_plan(
    *,
    user_input: str,
    machine_id: str,
    retrieved_chunks: list[dict[str, Any]] | None = None,
    health_result: dict[str, Any] | None = None,
    history: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate a deterministic maintenance plan without requiring an LLM."""
    chunks = retrieved_chunks or []
    health = health_result or {}
    risk_level = str(health.get("risk_level") or "unknown").lower()
    plan: list[str]

    if risk_level in {"high", "critical"}:
        plan = [
            "通知值班工程师并确认设备当前是否需要降载或停机。",
            "按照维护手册检查报警相关部件、连接状态和安全联锁。",
            "记录当前传感器读数，完成复测后再决定维修或复机。",
        ]
    elif risk_level == "medium":
        plan = [
            "安排近期点检，重点复核报警涉及的部件和运行趋势。",
            "结合维护手册确认润滑、紧固、冷却和清洁状态。",
            "持续记录传感器变化，若风险升级再执行人工复核。",
        ]
    elif risk_level == "low":
        plan = [
            "按维护手册执行例行检查和清洁保养。",
            "记录本次检查结果，继续观察设备运行趋势。",
        ]
    else:
        plan = [
            "补充设备型号、报警码或传感器数据，以便完成更准确判断。",
            "先按照维护手册核对现象、部件状态和最近一次维护记录。",
        ]

    if not chunks:
        plan.append("当前未找到对应手册片段，执行具体操作前请由工程师确认。")

    recommendation = str(health.get("recommendation") or "").strip()
    evidence_note = (
        f"已找到 {len(chunks)} 个相关手册片段。"
        if chunks
        else "当前没有可引用的手册片段。"
    )
    history_note = (
        "已读取当前用户历史会话作为辅助上下文。"
        if history and (history.get("messages") or history.get("sessions"))
        else ""
    )

    lines = [
        f"设备 {machine_id} 的初步维护建议：",
        f"风险等级：{risk_level}",
        recommendation or "当前没有可用的实时预测建议。",
        evidence_note,
    ]
    if history_note:
        lines.append(history_note)
    lines.append("建议步骤：")
    lines.extend(f"{index}. {item}" for index, item in enumerate(plan, 1))

    return {
        "machine_id": machine_id,
        "risk_level": risk_level,
        "plan": plan,
        "answer": "\n".join(lines),
        "query": user_input,
    }


def create_ticket_mock(
    *,
    machine_id: str,
    user_input: str,
    risk_level: str,
    maintenance_plan: list[str],
    user_id: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Create a local mock ticket; no external system is called."""
    ticket_id = f"MOCK-TICKET-{uuid.uuid4().hex[:12].upper()}"
    return {
        "ticket_id": ticket_id,
        "status": "mock_created",
        "machine_id": machine_id,
        "risk_level": risk_level,
        "title": f"{machine_id} maintenance review",
        "description": user_input,
        "maintenance_plan": maintenance_plan,
        "user_id": str(user_id) if user_id else None,
        "session_id": str(session_id) if session_id else None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "external_call": False,
    }


def list_history(
    *,
    user_id: str | None,
    session_id: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Read the current user's chat sessions and optionally one session's messages."""
    if not user_id:
        return {
            "sessions": [],
            "messages": [],
            "maintenance_records": [],
            "error": "未提供当前用户 ID，无法读取历史记录",
        }

    try:
        sessions = list_user_chat_sessions(user_id=user_id, limit=limit)
        messages = []
        if session_id:
            messages = list_user_session_messages(
                user_id=user_id,
                session_id=session_id,
                limit=limit * 10,
            )
        return {
            "sessions": sessions,
            "messages": messages,
            "maintenance_records": [],
            "error": None,
        }
    except (LookupError, PermissionError, ValueError) as exc:
        return {
            "sessions": [],
            "messages": [],
            "maintenance_records": [],
            "error": str(exc),
        }


TOOL_REGISTRY = {
    "retrieve_manual": retrieve_manual,
    "check_machine_health": check_machine_health,
    "generate_maintenance_plan": generate_maintenance_plan,
    "create_ticket_mock": create_ticket_mock,
    "list_history": list_history,
}
