from __future__ import annotations

import logging
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.routes_auth import get_current_user
from app.models.user import User
from app.services.agent_service import invoke_maintenance_agent
from app.services.document_service import validate_user_retrieval_filters

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])


class MaintenanceAgentRequest(BaseModel):
    user_input: str = Field(..., min_length=1)
    machine_id: str = Field(..., min_length=1)
    session_id: UUID | None = None

    knowledge_base_id: str | None = None
    document_id: str | None = None
    collection_id: str | None = None
    retriever_version: Literal["v1", "v2"] = "v2"
    top_k: int = Field(default=5, ge=1, le=20)
    use_rerank: bool = True
    sensor_data: dict[str, Any] = Field(default_factory=dict)
    confirm_create_ticket: bool = False


class MaintenanceAgentResponse(BaseModel):
    final_answer: str
    risk_level: str
    tools_used: list[str] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list)

    session_id: UUID | None = None
    confidence: float = 0.0
    maintenance_plan: list[str] = Field(default_factory=list)
    ticket: dict[str, Any] | None = None
    confirmation_required: bool = False
    debug: dict[str, Any] = Field(default_factory=dict)


@router.post(
    "/invoke",
    response_model=MaintenanceAgentResponse,
    summary="调用工业设备运维 Agent",
)
async def invoke_agent(
    request: MaintenanceAgentRequest,
    current_user: User = Depends(get_current_user),
):
    try:
        validate_user_retrieval_filters(
            user_id=current_user.id,
            document_id=request.document_id or request.knowledge_base_id,
            collection_id=request.collection_id,
        )
        result = invoke_maintenance_agent(
            user_input=request.user_input,
            machine_id=request.machine_id,
            session_id=request.session_id,
            user_id=current_user.id,
            knowledge_base_id=request.knowledge_base_id,
            document_id=request.document_id,
            collection_id=request.collection_id,
            retriever_version=request.retriever_version,
            top_k=request.top_k,
            use_rerank=request.use_rerank,
            sensor_data=request.sensor_data,
            confirm_create_ticket=request.confirm_create_ticket,
        )
        return result
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Maintenance agent invoke failed: %s", exc)
        raise HTTPException(status_code=500, detail="运维 Agent 调用失败") from exc
