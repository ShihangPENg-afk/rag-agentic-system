from __future__ import annotations

import json
import math
import re
import unicodedata
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import FINAL_TOP_K, FIXED_DIMENSION
from app.models.chunk import Chunk
from app.models.chunk_embedding import ChunkEmbedding
from app.models.collection import Collection
from app.models.document import Document
from app.retrievers.rerank import RerankerService
from app.retrievers.retriever_v2_pgvector import embed_query
from app.services.embedding_service import get_embedding_model_name

FusionMethod = Literal["rrf", "weighted"]

BM25_K1 = 1.5
BM25_B = 0.75
DEFAULT_DENSE_WEIGHT = 0.6
DEFAULT_BM25_WEIGHT = 0.4
DEFAULT_RRF_K = 60
DEFAULT_CANDIDATE_MIN = 20
DEFAULT_CANDIDATE_MULTIPLIER = 5


def _to_uuid(value: str | uuid.UUID | None) -> uuid.UUID | None:
    if value is None:
        return None
    return uuid.UUID(str(value))


def _score_from_distance(distance: float | None) -> float:
    if distance is None or math.isnan(float(distance)):
        return 0.0
    return 1.0 / (1.0 + max(float(distance), 0.0))


def _candidate_limit(top_k: int) -> int:
    return max(top_k * DEFAULT_CANDIDATE_MULTIPLIER, DEFAULT_CANDIDATE_MIN)


def _tokenize_for_bm25(text: str) -> list[str]:
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


def _source_metadata_from_row(row) -> dict[str, Any]:
    return {
        "document_filename": row.document_filename,
        "collection_id": str(row.collection_id) if row.collection_id else None,
        "collection_name": row.collection_name,
        "chunk_index": row.chunk_index,
        "char_start": row.char_start,
        "char_end": row.char_end,
        "chunk_metadata": row.chunk_metadata or {},
        "retrieval_sources": {},
    }


def _base_result_from_row(row) -> dict[str, Any]:
    return {
        "chunk_id": str(row.chunk_id),
        "document_id": str(row.document_id),
        "collection_id": str(row.collection_id) if row.collection_id else None,
        "content": row.content,
        "dense_score": 0.0,
        "bm25_score": 0.0,
        "final_score": 0.0,
        "score": 0.0,
        "source_metadata": _source_metadata_from_row(row),
    }


def _filtered_chunk_stmt(
    *,
    user_id: uuid.UUID,
    document_id: uuid.UUID | None = None,
    collection_id: uuid.UUID | None = None,
):
    stmt = (
        select(
            Chunk.id.label("chunk_id"),
            Chunk.document_id.label("document_id"),
            Chunk.collection_id.label("collection_id"),
            Chunk.content.label("content"),
            Chunk.chunk_index.label("chunk_index"),
            Chunk.char_start.label("char_start"),
            Chunk.char_end.label("char_end"),
            Chunk.metadata_json.label("chunk_metadata"),
            Document.filename.label("document_filename"),
            Collection.name.label("collection_name"),
        )
        .join(Document, Document.id == Chunk.document_id)
        .outerjoin(Collection, Collection.id == Chunk.collection_id)
        .where(Chunk.user_id == user_id, Document.user_id == user_id)
        .order_by(Chunk.chunk_index.asc())
    )

    if document_id is not None:
        stmt = stmt.where(Chunk.document_id == document_id)
    if collection_id is not None:
        stmt = stmt.where(Chunk.collection_id == collection_id)

    return stmt


def _coerce_vector(value: Any) -> list[float]:
    if isinstance(value, str):
        value = json.loads(value)
    return [float(item) for item in value]


def _search_dense_chunks(
    *,
    query_embedding: list[float],
    user_id: uuid.UUID,
    document_id: uuid.UUID | None = None,
    collection_id: uuid.UUID | None = None,
    limit: int = DEFAULT_CANDIDATE_MIN,
    embedding_model: str | None = None,
) -> list[dict[str, Any]]:
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        embedding_model = embedding_model or get_embedding_model_name()
        bind = db.get_bind()

        if bind.dialect.name == "postgresql":
            distance = ChunkEmbedding.embedding.l2_distance(query_embedding).label("distance")
            stmt = (
                select(
                    Chunk.id.label("chunk_id"),
                    Chunk.document_id.label("document_id"),
                    Chunk.collection_id.label("collection_id"),
                    Chunk.content.label("content"),
                    Chunk.chunk_index.label("chunk_index"),
                    Chunk.char_start.label("char_start"),
                    Chunk.char_end.label("char_end"),
                    Chunk.metadata_json.label("chunk_metadata"),
                    Document.filename.label("document_filename"),
                    Collection.name.label("collection_name"),
                    ChunkEmbedding.embedding_model.label("embedding_model"),
                    ChunkEmbedding.embedding_dimension.label("embedding_dimension"),
                    distance,
                )
                .join(Chunk, Chunk.id == ChunkEmbedding.chunk_id)
                .join(Document, Document.id == Chunk.document_id)
                .outerjoin(Collection, Collection.id == Chunk.collection_id)
                .where(
                    ChunkEmbedding.embedding_model == embedding_model,
                    ChunkEmbedding.embedding_dimension == FIXED_DIMENSION,
                    ChunkEmbedding.user_id == user_id,
                    Chunk.user_id == user_id,
                    Document.user_id == user_id,
                )
                .order_by(distance.asc())
                .limit(limit)
            )

            if document_id is not None:
                stmt = stmt.where(
                    ChunkEmbedding.document_id == document_id,
                    Chunk.document_id == document_id,
                )
            if collection_id is not None:
                stmt = stmt.where(
                    ChunkEmbedding.collection_id == collection_id,
                    Chunk.collection_id == collection_id,
                )

            rows = db.execute(stmt).all()
            results: list[dict[str, Any]] = []
            for rank, row in enumerate(rows, 1):
                distance_value = float(row.distance)
                item = _base_result_from_row(row)
                item["distance"] = distance_value
                item["dense_score"] = _score_from_distance(distance_value)
                item["source_metadata"]["embedding_model"] = row.embedding_model
                item["source_metadata"]["embedding_dimension"] = row.embedding_dimension
                item["source_metadata"]["retrieval_sources"]["pgvector"] = {
                    "rank": rank,
                    "score": item["dense_score"],
                    "distance": distance_value,
                }
                results.append(item)
            return results

        stmt = (
            select(
                Chunk.id.label("chunk_id"),
                Chunk.document_id.label("document_id"),
                Chunk.collection_id.label("collection_id"),
                Chunk.content.label("content"),
                Chunk.chunk_index.label("chunk_index"),
                Chunk.char_start.label("char_start"),
                Chunk.char_end.label("char_end"),
                Chunk.metadata_json.label("chunk_metadata"),
                Document.filename.label("document_filename"),
                Collection.name.label("collection_name"),
                ChunkEmbedding.embedding_model.label("embedding_model"),
                ChunkEmbedding.embedding_dimension.label("embedding_dimension"),
                ChunkEmbedding.embedding.label("embedding"),
            )
            .join(Chunk, Chunk.id == ChunkEmbedding.chunk_id)
            .join(Document, Document.id == Chunk.document_id)
            .outerjoin(Collection, Collection.id == Chunk.collection_id)
            .where(
                ChunkEmbedding.embedding_model == embedding_model,
                ChunkEmbedding.embedding_dimension == FIXED_DIMENSION,
                ChunkEmbedding.user_id == user_id,
                Chunk.user_id == user_id,
                Document.user_id == user_id,
            )
        )

        if document_id is not None:
            stmt = stmt.where(
                ChunkEmbedding.document_id == document_id,
                Chunk.document_id == document_id,
            )
        if collection_id is not None:
            stmt = stmt.where(
                ChunkEmbedding.collection_id == collection_id,
                Chunk.collection_id == collection_id,
            )

        results = []
        for row in db.execute(stmt).all():
            vector = _coerce_vector(row.embedding)
            if len(vector) != len(query_embedding):
                continue
            distance_value = math.sqrt(
                sum(
                    (float(query_value) - float(chunk_value)) ** 2
                    for query_value, chunk_value in zip(query_embedding, vector)
                )
            )
            item = _base_result_from_row(row)
            item["distance"] = distance_value
            item["dense_score"] = _score_from_distance(distance_value)
            item["source_metadata"]["embedding_model"] = row.embedding_model
            item["source_metadata"]["embedding_dimension"] = row.embedding_dimension
            results.append(item)

        results.sort(key=lambda item: item["distance"])
        for rank, item in enumerate(results[:limit], 1):
            item["source_metadata"]["retrieval_sources"]["pgvector"] = {
                "rank": rank,
                "score": item["dense_score"],
                "distance": item["distance"],
            }
        return results[:limit]
    finally:
        db.close()


def _search_bm25_chunks(
    *,
    query: str,
    user_id: uuid.UUID,
    document_id: uuid.UUID | None = None,
    collection_id: uuid.UUID | None = None,
    limit: int = DEFAULT_CANDIDATE_MIN,
) -> list[dict[str, Any]]:
    from app.db.session import SessionLocal

    query_tokens = _tokenize_for_bm25(query)
    if not query_tokens:
        return []

    db = SessionLocal()
    try:
        rows = db.execute(
            _filtered_chunk_stmt(
                user_id=user_id,
                document_id=document_id,
                collection_id=collection_id,
            )
        ).all()
    finally:
        db.close()

    if not rows:
        return []

    tokenized_docs = [_tokenize_for_bm25(row.content) for row in rows]
    avg_doc_len = sum(len(tokens) for tokens in tokenized_docs) / max(len(tokenized_docs), 1)
    doc_freq: Counter[str] = Counter()
    for tokens in tokenized_docs:
        doc_freq.update(set(tokens))

    scored: list[tuple[float, Any]] = []
    total_docs = len(tokenized_docs)
    for row, tokens in zip(rows, tokenized_docs):
        if not tokens:
            continue

        term_freq = Counter(tokens)
        doc_len = len(tokens)
        score = 0.0
        for token in query_tokens:
            freq = term_freq.get(token, 0)
            if freq == 0:
                continue

            idf = math.log(1 + (total_docs - doc_freq[token] + 0.5) / (doc_freq[token] + 0.5))
            denominator = freq + BM25_K1 * (1 - BM25_B + BM25_B * doc_len / max(avg_doc_len, 1))
            score += idf * (freq * (BM25_K1 + 1)) / denominator

        if score > 0:
            scored.append((score, row))

    scored.sort(key=lambda item: item[0], reverse=True)
    results: list[dict[str, Any]] = []
    for rank, (score, row) in enumerate(scored[:limit], 1):
        item = _base_result_from_row(row)
        item["bm25_score"] = float(score)
        item["source_metadata"]["retrieval_sources"]["bm25"] = {
            "rank": rank,
            "score": item["bm25_score"],
        }
        results.append(item)

    return results


def _dense_pipeline(
    *,
    query: str,
    user_id: uuid.UUID,
    document_id: uuid.UUID | None,
    collection_id: uuid.UUID | None,
    limit: int,
) -> tuple[list[dict[str, Any]], str | None]:
    query_embedding, error = embed_query(query)
    if error is not None or query_embedding is None:
        return [], error

    return (
        _search_dense_chunks(
            query_embedding=query_embedding,
            user_id=user_id,
            document_id=document_id,
            collection_id=collection_id,
            limit=limit,
        ),
        None,
    )


def _normalize_score_map(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}

    min_score = min(scores.values())
    max_score = max(scores.values())
    if math.isclose(max_score, min_score):
        return {chunk_id: 1.0 if max_score > 0 else 0.0 for chunk_id in scores}

    return {
        chunk_id: (score - min_score) / (max_score - min_score)
        for chunk_id, score in scores.items()
    }


def _merge_results(
    *,
    dense_results: list[dict[str, Any]],
    bm25_results: list[dict[str, Any]],
    fusion: FusionMethod,
    top_k: int,
    dense_weight: float,
    bm25_weight: float,
    rrf_k: int,
    warnings: list[str] | None = None,
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}

    def ensure_item(item: dict[str, Any]) -> dict[str, Any]:
        chunk_id = item["chunk_id"]
        if chunk_id not in merged:
            merged[chunk_id] = deepcopy(item)
            merged[chunk_id]["source_metadata"] = deepcopy(item.get("source_metadata") or {})
            merged[chunk_id]["source_metadata"].setdefault("retrieval_sources", {})
        return merged[chunk_id]

    dense_rank_by_id: dict[str, int] = {}
    bm25_rank_by_id: dict[str, int] = {}

    for rank, item in enumerate(dense_results, 1):
        chunk_id = item["chunk_id"]
        dense_rank_by_id[chunk_id] = rank
        target = ensure_item(item)
        target["dense_score"] = float(item.get("dense_score") or 0.0)
        target["source_metadata"]["retrieval_sources"]["pgvector"] = {
            "rank": rank,
            "score": target["dense_score"],
            "distance": item.get("distance"),
        }

    for rank, item in enumerate(bm25_results, 1):
        chunk_id = item["chunk_id"]
        bm25_rank_by_id[chunk_id] = rank
        target = ensure_item(item)
        target["bm25_score"] = float(item.get("bm25_score") or 0.0)
        target["source_metadata"]["retrieval_sources"]["bm25"] = {
            "rank": rank,
            "score": target["bm25_score"],
        }

    dense_norm = _normalize_score_map(
        {item["chunk_id"]: float(item.get("dense_score") or 0.0) for item in dense_results}
    )
    bm25_norm = _normalize_score_map(
        {item["chunk_id"]: float(item.get("bm25_score") or 0.0) for item in bm25_results}
    )

    for chunk_id, item in merged.items():
        if fusion == "weighted":
            final_score = (
                dense_weight * dense_norm.get(chunk_id, 0.0)
                + bm25_weight * bm25_norm.get(chunk_id, 0.0)
            )
        else:
            final_score = 0.0
            dense_rank = dense_rank_by_id.get(chunk_id)
            bm25_rank = bm25_rank_by_id.get(chunk_id)
            if dense_rank is not None:
                final_score += dense_weight / (rrf_k + dense_rank)
            if bm25_rank is not None:
                final_score += bm25_weight / (rrf_k + bm25_rank)

        item["final_score"] = float(final_score)
        item["score"] = item["final_score"]
        item["source_metadata"]["fusion_method"] = fusion
        item["source_metadata"]["dense_weight"] = dense_weight
        item["source_metadata"]["bm25_weight"] = bm25_weight
        if warnings:
            item["source_metadata"]["retrieval_warnings"] = warnings

    fused = list(merged.values())
    fused.sort(
        key=lambda item: (
            item["final_score"],
            item.get("dense_score", 0.0),
            item.get("bm25_score", 0.0),
        ),
        reverse=True,
    )
    return fused[:top_k]


def retrieve_similar_chunks(
    *,
    query: str,
    user_id: str | uuid.UUID | None = None,
    document_id: str | uuid.UUID | None = None,
    collection_id: str | uuid.UUID | None = None,
    top_k: int = FINAL_TOP_K,
    limit: int | None = None,
    fusion: FusionMethod = "rrf",
    dense_weight: float = DEFAULT_DENSE_WEIGHT,
    bm25_weight: float = DEFAULT_BM25_WEIGHT,
    rrf_k: int = DEFAULT_RRF_K,
    use_rerank: bool = False,
) -> tuple[list[dict[str, Any]], str | None]:
    try:
        normalized_user_id = _to_uuid(user_id)
        if normalized_user_id is None:
            raise PermissionError("user_id is required for hybrid retrieval")

        normalized_document_id = _to_uuid(document_id)
        normalized_collection_id = _to_uuid(collection_id)
        effective_top_k = max(1, int(limit if limit is not None else top_k))
        candidate_limit = _candidate_limit(effective_top_k)

        dense_results: list[dict[str, Any]] = []
        bm25_results: list[dict[str, Any]] = []
        warnings: list[str] = []

        with ThreadPoolExecutor(max_workers=2) as executor:
            dense_future = executor.submit(
                _dense_pipeline,
                query=query,
                user_id=normalized_user_id,
                document_id=normalized_document_id,
                collection_id=normalized_collection_id,
                limit=candidate_limit,
            )
            bm25_future = executor.submit(
                _search_bm25_chunks,
                query=query,
                user_id=normalized_user_id,
                document_id=normalized_document_id,
                collection_id=normalized_collection_id,
                limit=candidate_limit,
            )

            try:
                dense_results, dense_error = dense_future.result()
            except Exception as e:
                dense_results = []
                dense_error = str(e)
            if dense_error:
                warnings.append(f"pgvector: {dense_error}")

            try:
                bm25_results = bm25_future.result()
            except Exception as e:
                bm25_results = []
                warnings.append(f"bm25: {e}")

        if not dense_results and not bm25_results and warnings:
            return [], f"⚠️ hybrid 检索服务异常: {'; '.join(warnings)}"

        merge_top_k = candidate_limit if use_rerank else effective_top_k
        results = _merge_results(
            dense_results=dense_results,
            bm25_results=bm25_results,
            fusion=fusion,
            top_k=merge_top_k,
            dense_weight=dense_weight,
            bm25_weight=bm25_weight,
            rrf_k=rrf_k,
            warnings=warnings,
        )

        if not results:
            return [], "📚 未在文档中找到相关信息，请尝试换个问题。"

        if use_rerank:
            try:
                results = RerankerService().rerank(
                    query=query,
                    candidate_chunks=results,
                    top_k=effective_top_k,
                )
            except Exception as e:
                warnings.append(f"rerank: {e}")
                for item in results:
                    item.setdefault("source_metadata", {})["retrieval_warnings"] = warnings
                results = results[:effective_top_k]

        return results, None
    except ValueError:
        return [], "⚠️ 无效的文档或集合 ID"
    except PermissionError as e:
        return [], f"⚠️ hybrid 检索需要用户权限: {e}"
    except (RuntimeError, SQLAlchemyError) as e:
        return [], f"⚠️ hybrid 检索服务异常: {e}"


def retrieve_relevant_chunks_hybrid(
    *,
    knowledge_base_id: str,
    enhanced_query: str,
    user_id: str | uuid.UUID | None = None,
    collection_id: str | uuid.UUID | None = None,
    top_k: int = FINAL_TOP_K,
    limit: int | None = None,
    use_rerank: bool = False,
) -> tuple[list[str], str | None, list[dict[str, Any]]]:
    results, error = retrieve_similar_chunks(
        query=enhanced_query,
        user_id=user_id,
        document_id=knowledge_base_id,
        collection_id=collection_id,
        top_k=top_k,
        limit=limit,
        use_rerank=use_rerank,
    )
    if error is not None:
        return [], error, []
    return [item["content"] for item in results], None, results
