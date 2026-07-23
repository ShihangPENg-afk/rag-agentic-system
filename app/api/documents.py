from fastapi import APIRouter, Depends, Query

from app.api.routes_auth import get_current_user
from app.models.user import User
from app.repositories.document_repository import list_recent_documents
from app.repositories.qa_log_repository import list_qa_logs_by_knowledge_base
from app.schemas.api_models import DocumentsListResponse, QALogsListResponse

router = APIRouter()


@router.get("/documents/", response_model=DocumentsListResponse, summary="获取最近上传的文档")
async def get_documents(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
):
    documents = list_recent_documents(limit=limit)
    return {
        "total": len(documents),
        "documents": documents,
    }


@router.get("/qa_logs/", response_model=QALogsListResponse, summary="按知识库查询历史问答")
async def get_qa_logs(
    knowledge_base_id: str = Query(..., description="知识库 ID"),
    limit: int = Query(default=100, ge=1, le=500),
):
    qa_logs = list_qa_logs_by_knowledge_base(knowledge_base_id, limit=limit)
    return {
        "knowledge_base_id": knowledge_base_id,
        "total": len(qa_logs),
        "qa_logs": qa_logs,
    }
