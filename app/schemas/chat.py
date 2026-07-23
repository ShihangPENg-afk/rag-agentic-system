from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ChatSessionRead(BaseModel):
    id: UUID
    user_id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


class MessageRead(BaseModel):
    id: UUID
    session_id: UUID
    role: str
    content: str
    created_at: datetime


class ChatSessionCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)


class ChatSessionListResponse(BaseModel):
    total: int
    sessions: list[ChatSessionRead]


class MessageListResponse(BaseModel):
    session_id: UUID
    total: int
    messages: list[MessageRead]
