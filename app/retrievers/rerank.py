from __future__ import annotations

import re
import unicodedata
from collections import Counter
from copy import deepcopy
from typing import Any

from app.core.config import RERANK_PROVIDER


def _tokenize(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text or "").lower()
    segments = re.findall(r"[a-z0-9]+(?:'[a-z0-9]+)?|[\u4e00-\u9fff]+", normalized)
    tokens: list[str] = []
    for segment in segments:
        if re.fullmatch(r"[\u4e00-\u9fff]+", segment):
            tokens.extend(segment)
            if len(segment) > 1:
                tokens.extend(segment[i : i + 2] for i in range(len(segment) - 1))
        else:
            tokens.append(segment)
    return tokens


def _existing_score(candidate: dict[str, Any]) -> float:
    for key in ("rerank_score", "final_score", "score", "dense_score", "bm25_score"):
        value = candidate.get(key)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    return 0.0


class RerankerService:
    """
    Rerank retrieved chunks after first-stage retrieval.

    The default mock provider is deterministic and dependency-free, so tests and
    local development can exercise the rerank path before a real model is wired.
    """

    def __init__(self, provider: str | None = None):
        self.provider = (provider or RERANK_PROVIDER or "mock").strip().lower()

    def rerank(
        self,
        *,
        query: str,
        candidate_chunks: list[dict[str, Any]],
        top_k: int | None = None,
    ) -> list[dict[str, Any]]:
        if not candidate_chunks:
            return []

        if self.provider in {"none", "disabled", "off"}:
            return self._identity_rerank(candidate_chunks, top_k=top_k)
        if self.provider == "mock":
            return self._mock_rerank(query, candidate_chunks, top_k=top_k)

        raise ValueError(f"Unsupported RERANK_PROVIDER: {self.provider}")

    def _identity_rerank(
        self,
        candidate_chunks: list[dict[str, Any]],
        *,
        top_k: int | None,
    ) -> list[dict[str, Any]]:
        reranked = [deepcopy(item) for item in candidate_chunks]
        for rank, item in enumerate(reranked, 1):
            item["rerank_score"] = _existing_score(item)
            self._attach_metadata(item, rank=rank)
        return reranked[:top_k] if top_k is not None else reranked

    def _mock_rerank(
        self,
        query: str,
        candidate_chunks: list[dict[str, Any]],
        *,
        top_k: int | None,
    ) -> list[dict[str, Any]]:
        query_tokens = _tokenize(query)
        query_counter = Counter(query_tokens)
        query_terms = set(query_counter)
        normalized_query = unicodedata.normalize("NFKC", query or "").lower().strip()

        scored: list[tuple[float, float, int, dict[str, Any]]] = []
        for original_index, candidate in enumerate(candidate_chunks):
            item = deepcopy(candidate)
            content = str(item.get("content") or "")
            content_tokens = _tokenize(content)
            content_counter = Counter(content_tokens)
            content_terms = set(content_counter)

            if query_terms:
                overlap_terms = query_terms & content_terms
                coverage_score = len(overlap_terms) / len(query_terms)
                frequency_score = sum(
                    min(query_counter[token], content_counter[token])
                    for token in query_terms
                ) / max(sum(query_counter.values()), 1)
            else:
                coverage_score = 0.0
                frequency_score = 0.0

            phrase_bonus = 0.0
            if normalized_query and normalized_query in unicodedata.normalize("NFKC", content).lower():
                phrase_bonus = 0.25

            rerank_score = coverage_score + 0.5 * frequency_score + phrase_bonus
            item["rerank_score"] = float(rerank_score)
            scored.append((item["rerank_score"], _existing_score(item), -original_index, item))

        scored.sort(key=lambda value: (value[0], value[1], value[2]), reverse=True)
        reranked = [item for _rerank_score, _existing, _index, item in scored]
        for rank, item in enumerate(reranked, 1):
            self._attach_metadata(item, rank=rank)

        return reranked[:top_k] if top_k is not None else reranked

    def _attach_metadata(self, item: dict[str, Any], *, rank: int) -> None:
        source_metadata = item.setdefault("source_metadata", {})
        source_metadata["reranker"] = {
            "provider": self.provider,
            "rank": rank,
            "score": item.get("rerank_score", 0.0),
        }
