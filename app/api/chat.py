import logging

from fastapi import APIRouter, HTTPException

from app.repositories.qa_log_repository import record_qa_log
from app.schemas.api_models import AnswerResponse, QuestionRequest
from app.services.agent_chat_service import chat_with_agent_state
from app.services.chat_service import build_chat_state_from_request, chat_with_rag_state
from utils.utils import check_network

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/ask/", response_model=AnswerResponse, summary="提问接口（Agent 默认入口）")
async def ask_question(request: QuestionRequest):
    try:
        if not check_network():
            raise HTTPException(status_code=500, detail="网络连接异常，无法调用AI服务")

        result = chat_with_agent_state(request)

        record_qa_log(
            knowledge_base_id=request.knowledge_base_id,
            question=request.question,
            answer=result["answer"],
            mode="agent",
            debug=result.get("debug"),
        )

        return {
            "answer": result["answer"],
            "knowledge_base_id": request.knowledge_base_id,
            "history": result["history"],
            "debug": result["debug"],
            "mode": "agent",
        }
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Agent 问答时出错: %s", str(e))
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")


@router.post("/ask_rag/", response_model=AnswerResponse, summary="经典 RAG 提问接口（回退模式）")
async def ask_question_rag(request: QuestionRequest):
    try:
        if not check_network():
            raise HTTPException(status_code=500, detail="网络连接异常，无法调用AI服务")

        state = build_chat_state_from_request(request)
        answer, updated_history = chat_with_rag_state(state)

        return {
            "answer": answer,
            "knowledge_base_id": state.knowledge_base_id,
            "history": updated_history,
            "debug": None,
            "mode": "rag",
        }
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("经典 RAG 问答时出错: %s", str(e))
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")
