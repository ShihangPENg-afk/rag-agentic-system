from __future__ import annotations

import hashlib
import os
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chunk import Chunk
from app.models.chunk_embedding import ChunkEmbedding
from app.models.collection import Collection
from app.models.document import Document
from app.services.embedding_service import get_embedding_model_name

DEFAULT_COLLECTION_NAME = "默认知识库"


def _to_uuid(value: str | uuid.UUID | None) -> uuid.UUID | None:
    if value is None:
        return None
    return uuid.UUID(str(value))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def file_sha256(path: str) -> str | None:
    if not path or not os.path.exists(path):
        return None

    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def get_or_create_collection(
    db: Session,
    user_id: str | uuid.UUID | None,
    collection_id: str | uuid.UUID | None = None,
    name: str = DEFAULT_COLLECTION_NAME,
) -> Collection:
    normalized_user_id = _to_uuid(user_id)

    if collection_id is not None:
        stmt = select(Collection).where(Collection.id == _to_uuid(collection_id))
        if normalized_user_id is None:
            stmt = stmt.where(Collection.user_id.is_(None))
        else:
            stmt = stmt.where(Collection.user_id == normalized_user_id)

        collection = db.execute(stmt).scalar_one_or_none()
        if collection is None:
            raise LookupError("Collection not found or not owned by current user")
        return collection

    stmt = select(Collection).where(Collection.name == name)
    if normalized_user_id is None:
        stmt = stmt.where(Collection.user_id.is_(None))
    else:
        stmt = stmt.where(Collection.user_id == normalized_user_id)

    collection = db.execute(stmt.order_by(Collection.created_at.asc())).scalars().first()
    if collection is not None:
        return collection

    collection = Collection(
        user_id=normalized_user_id,
        name=name,
        status="ready",
        metadata_json={"kind": "default"},
    )
    db.add(collection)
    db.flush()
    return collection


def persist_document_chunks_embeddings(
    db: Session,
    *,
    filename: str,
    content_type: str,
    chunks: list[str],
    embeddings: list[list[float]],
    user_id: str | uuid.UUID | None = None,
    collection_id: str | uuid.UUID | None = None,
    file_size: int | None = None,
    content_hash: str | None = None,
    embedding_model: str | None = None,
    embedding_dimension: int | None = None,
) -> dict[str, Any]:
    if len(chunks) != len(embeddings):
        raise ValueError("chunks 与 embeddings 数量不一致，无法持久化")

    normalized_user_id = _to_uuid(user_id)
    collection = get_or_create_collection(
        db,
        user_id=normalized_user_id,
        collection_id=collection_id,
    )
    embedding_model = embedding_model or get_embedding_model_name()
    dimension = embedding_dimension or (len(embeddings[0]) if embeddings else 0)

    document = Document(
        user_id=normalized_user_id,
        collection_id=collection.id,
        filename=filename,
        content_type=content_type,
        file_size=file_size,
        content_hash=content_hash,
        chunks_count=0,
        status="processing",
    )
    db.add(document)
    db.flush()

    chunk_rows: list[tuple[Chunk, list[float]]] = []
    for index, (content, embedding) in enumerate(zip(chunks, embeddings)):
        chunk = Chunk(
            document_id=document.id,
            collection_id=collection.id,
            user_id=normalized_user_id,
            chunk_index=index,
            content=content,
            content_hash=_sha256_text(content),
            metadata_json={"source": filename},
        )
        db.add(chunk)
        chunk_rows.append((chunk, [float(value) for value in embedding]))

    db.flush()

    for chunk, embedding in chunk_rows:
        db.add(
            ChunkEmbedding(
                chunk_id=chunk.id,
                document_id=document.id,
                collection_id=collection.id,
                user_id=normalized_user_id,
                embedding_model=embedding_model,
                embedding_dimension=dimension,
                embedding=embedding,
            )
        )

    document.chunks_count = len(chunk_rows)
    document.status = "ready"
    db.commit()
    db.refresh(document)
    db.refresh(collection)

    return {
        "document": document,
        "collection": collection,
        "chunks_count": len(chunk_rows),
    }


def list_chunks_for_document(
    *,
    document_id: str | uuid.UUID,
    user_id: str | uuid.UUID | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    from app.db.session import SessionLocal

    normalized_user_id = _to_uuid(user_id)
    if normalized_user_id is None:
        raise PermissionError("user_id is required for chunk listing")

    db = SessionLocal()
    try:
        stmt = select(Chunk).where(Chunk.document_id == _to_uuid(document_id))
        stmt = stmt.where(Chunk.user_id == normalized_user_id)
        stmt = stmt.order_by(Chunk.chunk_index.asc())
        if limit is not None and limit > 0:
            stmt = stmt.limit(limit)

        rows = db.execute(stmt).scalars().all()
        return [
            {
                "chunk_id": str(row.id),
                "document_id": str(row.document_id),
                "collection_id": str(row.collection_id) if row.collection_id else None,
                "user_id": str(row.user_id) if row.user_id else None,
                "chunk_index": row.chunk_index,
                "content": row.content,
            }
            for row in rows
        ]
    finally:
        db.close()
