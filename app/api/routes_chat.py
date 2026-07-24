import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.routes_auth import get_current_user
from app.core.redis import increment_chat_rate_limit
from app.models.user import User
from app.repositories.qa_log_repository import record_qa_log
from app.schemas.api_models import AnswerResponse, QuestionRequest
from app.schemas.chat import ChatSessionListResponse, MessageListResponse
from app.services.agent_chat_service import chat_with_agent_state
from app.services.chat_service import (
    build_chat_state_from_request,
    chat_with_rag_state,
    list_user_chat_sessions,
    list_user_session_messages,
    persist_chat_exchange,
)
from app.services.document_service import validate_user_retrieval_filters
from utils.utils import check_network

logger = logging.getLogger(__name__)

router = APIRouter()

CHAT_RATE_LIMIT_PER_MINUTE = 20


def enforce_chat_rate_limit(
    current_user: User = Depends(get_current_user),
) -> User:
    try:
        count = increment_chat_rate_limit(
            current_user.id,
            limit=CHAT_RATE_LIMIT_PER_MINUTE,
            window_seconds=60,
        )
    except Exception as e:
        logger.warning("Redis 限流不可用，放行本次 chat 请求: %s", e)
        return current_user

    if count > CHAT_RATE_LIMIT_PER_MINUTE:
        raise HTTPException(
            status_code=429,
            detail="Too many chat requests. Please retry later.",
            headers={"Retry-After": "60"},
        )

    return current_user


@router.post("/ask/", response_model=AnswerResponse, summary="提问接口（Agent 默认入口）")
async def ask_question(
    request: QuestionRequest,
    current_user: User = Depends(enforce_chat_rate_limit),
):
    try:
        validate_user_retrieval_filters(
            user_id=current_user.id,
            document_id=request.document_id,
            collection_id=request.collection_id,
        )

        if not check_network():
            raise HTTPException(status_code=500, detail="网络连接异常，无法调用AI服务")

        result = chat_with_agent_state(request, user_id=current_user.id)
        session = persist_chat_exchange(
            user_id=current_user.id,
            question=request.question,
            answer=result["answer"],
            session_id=request.session_id,
        )

        record_qa_log(
            knowledge_base_id=request.knowledge_base_id,
            question=request.question,
            answer=result["answer"],
            mode="agent",
            debug=result.get("debug"),
        )

        return {
            "answer": result["answer"],
            "confidence": result.get("confidence"),
            "sources": result.get("sources", []),
            "knowledge_base_id": request.knowledge_base_id,
            "session_id": session["id"],
            "history": result["history"],
            "debug": result["debug"],
            "mode": "agent",
        }
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Agent 问答时出错: %s", str(e))
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")


@router.post("/ask_rag/", response_model=AnswerResponse, summary="经典 RAG 提问接口（回退模式）")
async def ask_question_rag(
    request: QuestionRequest,
    current_user: User = Depends(enforce_chat_rate_limit),
):
    try:
        validate_user_retrieval_filters(
            user_id=current_user.id,
            document_id=request.document_id,
            collection_id=request.collection_id,
        )

        if not check_network():
            raise HTTPException(status_code=500, detail="网络连接异常，无法调用AI服务")

        state = build_chat_state_from_request(request, user_id=current_user.id)
        rag_result = chat_with_rag_state(state)
        if len(rag_result) == 3:
            answer, updated_history, retrieval_metadata = rag_result
        else:
            answer, updated_history = rag_result
            retrieval_metadata = {"confidence": None, "sources": []}
        session = persist_chat_exchange(
            user_id=current_user.id,
            question=request.question,
            answer=answer,
            session_id=request.session_id,
        )

        return {
            "answer": answer,
            "confidence": retrieval_metadata.get("confidence"),
            "sources": retrieval_metadata.get("sources", []),
            "knowledge_base_id": state.knowledge_base_id,
            "session_id": session["id"],
            "history": updated_history,
            "debug": None,
            "mode": "rag",
        }
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("经典 RAG 问答时出错: %s", str(e))
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")


@router.get("/chat/sessions", response_model=ChatSessionListResponse, summary="获取当前用户会话列表")
async def get_chat_sessions(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
):
    sessions = list_user_chat_sessions(user_id=current_user.id, limit=limit)
    return {"total": len(sessions), "sessions": sessions}


@router.get(
    "/chat/sessions/{session_id}/messages",
    response_model=MessageListResponse,
    summary="获取当前用户指定会话消息",
)
async def get_chat_messages(
    session_id: UUID,
    limit: int = Query(default=200, ge=1, le=500),
    current_user: User = Depends(get_current_user),
):
    try:
        messages = list_user_session_messages(
            user_id=current_user.id,
            session_id=session_id,
            limit=limit,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {"session_id": session_id, "total": len(messages), "messages": messages}
