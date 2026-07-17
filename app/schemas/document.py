from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class DocumentRead(BaseModel):
    id: UUID
    knowledge_base_id: UUID
    user_id: UUID | None = None
    filename: str
    content_type: str
    chunks_count: int
    status: str
    created_at: datetime
    updated_at: datetime


class DocumentListResponse(BaseModel):
    total: int
    documents: list[DocumentRead]
