from __future__ import annotations

from typing import List

import numpy as np

from app.core.config import (
    DISTANCE_THRESHOLD,
    FINAL_TOP_K,
    SCORE_THRESHOLD_PERCENT,
    TOP_K,
)
from app.services.embedding_service import get_embeddings
from app.vectordb.faiss_store import build_faiss_index

__all__ = ["build_faiss_index", "retrieve_relevant_chunks_faiss"]


def retrieve_relevant_chunks_faiss(index, chunks: List[str], enhanced_query: str):
    """
    Legacy FAISS retriever kept as v1 fallback.
    """
    if index is None or getattr(index, "ntotal", 0) == 0:
        return [], "⚠️ 知识库未初始化或为空，请先上传文档。"

    try:
        q_embeddings, _ = get_embeddings([enhanced_query])
        if not q_embeddings:
            return [], "⚠️ 问题向量化失败，请稍后重试"

        query_vector = np.array(q_embeddings, dtype=np.float32)

    except Exception as e:
        return [], f"⚠️ 向量化服务异常: {e}"

    try:
        distances, indices = index.search(query_vector, TOP_K)
        candidate_results = []

        for i, idx in enumerate(indices[0]):
            if idx < len(chunks):
                dist = distances[0][i]
                if dist < DISTANCE_THRESHOLD:
                    candidate_results.append((dist, chunks[idx]))

        if not candidate_results:
            for i, idx in enumerate(indices[0][:3]):
                if idx < len(chunks):
                    candidate_results.append((distances[0][i], chunks[idx]))

        if candidate_results:
            min_dist = candidate_results[0][0]
            threshold = min_dist + (1 - SCORE_THRESHOLD_PERCENT) * 10
            candidate_results = [
                (dist, text) for dist, text in candidate_results if dist <= threshold
            ]

        candidate_results.sort(key=lambda x: x[0])
        relevant_texts = [item[1] for item in candidate_results[:FINAL_TOP_K]]

        if not relevant_texts:
            return [], "📚 未在文档中找到相关信息，请尝试换个问题。"

        return relevant_texts, None

    except Exception as e:
        return [], f"⚠️ 检索服务异常: {e}"
