from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.routes_auth import get_current_user
from app.models.user import User


router = APIRouter(tags=["feedback"])


class FeedbackRequest(BaseModel):
    target_type: str = Field(default="answer", max_length=50)
    target_id: str | None = Field(default=None, max_length=128)
    rating: int | None = Field(default=None, ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FeedbackResponse(BaseModel):
    feedback_id: str
    status: str
    message: str


@router.post("/feedback", response_model=FeedbackResponse, summary="提交用户反馈")
async def submit_feedback(
    request: FeedbackRequest,
    current_user: User = Depends(get_current_user),
):
    return {
        "feedback_id": str(uuid4()),
        "status": "accepted",
        "message": "Feedback accepted for demo review workflow.",
    }
