from fastapi import APIRouter, Depends, Query

from app.api.routes_auth import get_current_user
from app.models.user import User
from app.repositories.qa_log_repository import list_qa_logs_by_knowledge_base
from app.schemas.api_models import QALogsListResponse
from app.schemas.document import DocumentListResponse
from app.services.document_service import ensure_user_document, list_user_documents

router = APIRouter()


@router.get("/documents/", response_model=DocumentListResponse, summary="获取当前用户最近上传的文档")
async def get_documents(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
):
    documents = list_user_documents(user_id=current_user.id, limit=limit)
    return {
        "total": len(documents),
        "documents": documents,
    }


@router.get("/qa_logs/", response_model=QALogsListResponse, summary="按知识库查询当前用户历史问答")
async def get_qa_logs(
    knowledge_base_id: str = Query(..., description="知识库 ID"),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
):
    ensure_user_document(document_id=knowledge_base_id, user_id=current_user.id)
    qa_logs = list_qa_logs_by_knowledge_base(knowledge_base_id, limit=limit)
    return {
        "knowledge_base_id": knowledge_base_id,
        "total": len(qa_logs),
        "qa_logs": qa_logs,
    }
