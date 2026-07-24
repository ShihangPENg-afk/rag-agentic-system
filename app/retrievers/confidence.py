from __future__ import annotations

from typing import Any

from app.core.config import RAG_MIN_CONFIDENCE

LOW_CONFIDENCE_ANSWER = "资料中未找到可靠依据"


def retrieval_score(result: dict[str, Any]) -> float:
    for key in ("rerank_score", "final_score", "score", "dense_score", "bm25_score"):
        value = result.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def calculate_confidence(results: list[dict[str, Any]]) -> float:
    if not results:
        return 0.0
    return max(retrieval_score(item) for item in results)


def is_low_confidence(confidence: float, threshold: float | None = None) -> bool:
    min_confidence = RAG_MIN_CONFIDENCE if threshold is None else float(threshold)
    return min_confidence > 0 and confidence < min_confidence


def build_sources(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for item in results:
        source = {
            "chunk_id": item.get("chunk_id"),
            "document_id": item.get("document_id"),
            "collection_id": item.get("collection_id"),
            "content": item.get("content"),
            "score": retrieval_score(item),
            "dense_score": item.get("dense_score"),
            "bm25_score": item.get("bm25_score"),
            "final_score": item.get("final_score"),
            "rerank_score": item.get("rerank_score"),
            "source_metadata": item.get("source_metadata") or {},
        }
        sources.append(source)
    return sources
