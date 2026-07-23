from __future__ import annotations

import math
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import FINAL_TOP_K, FIXED_DIMENSION
from app.models.chunk import Chunk
from app.models.chunk_embedding import ChunkEmbedding
from app.repositories.vector_repository import list_chunks_for_document
from app.services.embedding_service import get_embedding_model_name, get_embeddings


def _to_uuid(value: str | uuid.UUID | None) -> uuid.UUID | None:
    if value is None:
        return None
    return uuid.UUID(str(value))


def _score_from_distance(distance: float | None) -> float:
    if distance is None or math.isnan(float(distance)):
        return 0.0
    return 1.0 / (1.0 + max(float(distance), 0.0))


def _row_to_result(row) -> dict[str, Any]:
    distance = float(row.distance)
    return {
        "chunk_id": str(row.chunk_id),
        "document_id": str(row.document_id),
        "collection_id": str(row.collection_id) if row.collection_id else None,
        "score": _score_from_distance(distance),
        "distance": distance,
        "content": row.content,
    }


def embed_query(query: str) -> tuple[list[float] | None, str | None]:
    embeddings, dimension = get_embeddings([query])
    if not embeddings:
        return None, "⚠️ 问题向量化失败，请稍后重试"
    if dimension != FIXED_DIMENSION or len(embeddings[0]) != FIXED_DIMENSION:
        return None, f"⚠️ 向量维度异常，期望 {FIXED_DIMENSION} 维"
    return [float(value) for value in embeddings[0]], None


def search_similar_chunks(
    *,
    query_embedding: list[float],
    user_id: str | uuid.UUID,
    document_id: str | uuid.UUID | None = None,
    collection_id: str | uuid.UUID | None = None,
    limit: int = FINAL_TOP_K,
    embedding_model: str | None = None,
) -> list[dict[str, Any]]:
    from app.db.session import SessionLocal

    normalized_user_id = _to_uuid(user_id)
    if normalized_user_id is None:
        raise PermissionError("user_id is required for pgvector retrieval")

    db = SessionLocal()
    try:
        bind = db.get_bind()
        if bind.dialect.name != "postgresql":
            raise RuntimeError("pgvector retrieval requires PostgreSQL")

        embedding_model = embedding_model or get_embedding_model_name()
        distance = ChunkEmbedding.embedding.l2_distance(query_embedding).label("distance")
        stmt = (
            select(
                Chunk.id.label("chunk_id"),
                Chunk.document_id.label("document_id"),
                Chunk.collection_id.label("collection_id"),
                Chunk.content.label("content"),
                distance,
            )
            .join(Chunk, Chunk.id == ChunkEmbedding.chunk_id)
            .where(
                ChunkEmbedding.embedding_model == embedding_model,
                ChunkEmbedding.user_id == normalized_user_id,
                Chunk.user_id == normalized_user_id,
            )
            .order_by(distance.asc())
            .limit(limit)
        )

        normalized_document_id = _to_uuid(document_id)
        if normalized_document_id is not None:
            stmt = stmt.where(
                ChunkEmbedding.document_id == normalized_document_id,
                Chunk.document_id == normalized_document_id,
            )

        normalized_collection_id = _to_uuid(collection_id)
        if normalized_collection_id is not None:
            stmt = stmt.where(
                ChunkEmbedding.collection_id == normalized_collection_id,
                Chunk.collection_id == normalized_collection_id,
            )

        rows = db.execute(stmt).all()
        return [_row_to_result(row) for row in rows]
    finally:
        db.close()


def retrieve_similar_chunks(
    *,
    query: str,
    user_id: str | uuid.UUID | None = None,
    document_id: str | uuid.UUID | None = None,
    collection_id: str | uuid.UUID | None = None,
    limit: int = FINAL_TOP_K,
) -> tuple[list[dict[str, Any]], str | None]:
    try:
        query_embedding, error = embed_query(query)
        if error is not None or query_embedding is None:
            return [], error

        results = search_similar_chunks(
            query_embedding=query_embedding,
            user_id=user_id,
            document_id=document_id,
            collection_id=collection_id,
            limit=limit,
        )
        if not results:
            return [], "📚 未在文档中找到相关信息，请尝试换个问题。"
        return results, None
    except ValueError:
        return [], "⚠️ 无效的文档或集合 ID"
    except PermissionError as e:
        return [], f"⚠️ pgvector 检索需要用户权限: {e}"
    except (RuntimeError, SQLAlchemyError) as e:
        return [], f"⚠️ pgvector 检索服务异常: {e}"


def retrieve_relevant_chunks_pgvector(
    *,
    knowledge_base_id: str,
    enhanced_query: str,
    user_id: str | uuid.UUID | None = None,
    collection_id: str | uuid.UUID | None = None,
    limit: int = FINAL_TOP_K,
) -> tuple[list[str], str | None, list[dict[str, Any]]]:
    results, error = retrieve_similar_chunks(
        query=enhanced_query,
        user_id=user_id,
        document_id=knowledge_base_id,
        collection_id=collection_id,
        limit=limit,
    )
    if error is not None:
        return [], error, []
    return [item["content"] for item in results], None, results


def list_persisted_chunks_for_document(
    *,
    knowledge_base_id: str,
    user_id: str | uuid.UUID | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    try:
        return list_chunks_for_document(
            document_id=knowledge_base_id,
            user_id=user_id,
            limit=limit,
        )
    except (PermissionError, ValueError, SQLAlchemyError):
        return []
