from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class DocumentRead(BaseModel):
    id: UUID
    knowledge_base_id: UUID
    user_id: UUID | None = None
    collection_id: UUID | None = None
    filename: str
    content_type: str
    file_size: int | None = None
    content_hash: str | None = None
    chunks_count: int
    status: str
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class DocumentListResponse(BaseModel):
    total: int
    documents: list[DocumentRead]
