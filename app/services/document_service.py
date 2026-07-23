from uuid import UUID

from fastapi import HTTPException, status

from app.repositories.document_repository import (
    delete_document_by_id_and_user,
    get_collection_by_id,
    get_collection_by_id_and_user,
    get_document_by_id,
    get_document_by_id_and_user,
    list_recent_documents_by_user,
)
from app.services.kb_registry import delete_knowledge_base


def list_user_documents(user_id: UUID, limit: int = 50) -> list[dict]:
    return list_recent_documents_by_user(user_id=user_id, limit=limit)


def ensure_user_document(document_id: str | UUID, user_id: UUID) -> dict:
    existing = get_document_by_id(document_id=document_id)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    document = get_document_by_id_and_user(document_id=document_id, user_id=user_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )
    return document


def ensure_user_collection(collection_id: str | UUID, user_id: UUID) -> dict:
    existing = get_collection_by_id(collection_id=collection_id)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection not found",
        )

    collection = get_collection_by_id_and_user(
        collection_id=collection_id,
        user_id=user_id,
    )
    if collection is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )
    return collection


def validate_user_retrieval_filters(
    *,
    user_id: UUID,
    document_id: str | UUID | None = None,
    collection_id: str | UUID | None = None,
) -> None:
    document = None
    if document_id is not None:
        document = ensure_user_document(document_id=document_id, user_id=user_id)

    if collection_id is not None:
        ensure_user_collection(collection_id=collection_id, user_id=user_id)

    if document is not None and collection_id is not None:
        if str(document.get("collection_id")) != str(collection_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found in collection",
            )


def delete_user_document(document_id: str | UUID, user_id: UUID) -> dict:
    document = ensure_user_document(document_id=document_id, user_id=user_id)
    result = delete_document_by_id_and_user(document_id=document_id, user_id=user_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    delete_knowledge_base(str(document["id"]))
    return {
        "document_id": str(document["id"]),
        "deleted": True,
        "chunks_deleted": result["chunks_deleted"],
        "embeddings_deleted": result["embeddings_deleted"],
    }
