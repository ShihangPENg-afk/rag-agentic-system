from uuid import UUID

from fastapi import HTTPException, status

from app.repositories.document_repository import (
    get_document_by_id_and_user,
    list_recent_documents_by_user,
)


def list_user_documents(user_id: UUID, limit: int = 50) -> list[dict]:
    return list_recent_documents_by_user(user_id=user_id, limit=limit)


def ensure_user_document(document_id: str | UUID, user_id: UUID) -> dict:
    document = get_document_by_id_and_user(document_id=document_id, user_id=user_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    return document
