import logging
import os
import shutil
import tempfile
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from app.api.upload import (
    COPY_CHUNK_BYTES,
    MAX_PDF_BYTES,
    _assert_pdf_magic_and_nonempty,
    _validate_pdf_upload_filename,
)
from app.api.routes_auth import get_current_user
from app.models.user import User
from app.repositories.qa_log_repository import list_qa_logs_by_knowledge_base
from app.retrievers.retriever_v2_hybrid import (
    retrieve_similar_chunks as retrieve_hybrid_chunks,
)
from app.retrievers.retriever_v2_pgvector import retrieve_similar_chunks
from app.schemas.api_models import (
    QALogsListResponse,
    RetrievalRequest,
    RetrievalResponse,
    SingleUploadResponse,
)
from app.schemas.document import DocumentListResponse
from app.services.document_service import (
    delete_user_document,
    ensure_user_document,
    list_user_documents,
    validate_user_retrieval_filters,
)
from app.services.upload_service import update_knowledge_base_from_saved_pdf

logger = logging.getLogger(__name__)
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


@router.post("/documents/retrieve", response_model=RetrievalResponse, summary="检索当前用户文档片段")
async def retrieve_document_chunks(
    request: RetrievalRequest,
    current_user: User = Depends(get_current_user),
):
    validate_user_retrieval_filters(
        user_id=current_user.id,
        document_id=request.document_id,
        collection_id=request.collection_id,
    )
    if request.retriever_version == "v2":
        results, error = retrieve_hybrid_chunks(
            query=request.query,
            user_id=current_user.id,
            document_id=request.document_id,
            collection_id=request.collection_id,
            top_k=request.limit,
            use_rerank=request.use_rerank,
        )
    else:
        results, error = retrieve_similar_chunks(
            query=request.query,
            user_id=current_user.id,
            document_id=request.document_id,
            collection_id=request.collection_id,
            limit=request.limit,
        )
    if error is not None:
        if error.startswith("📚"):
            return {"total": 0, "chunks": []}
        raise HTTPException(status_code=500, detail=error)

    return {"total": len(results), "chunks": results}


@router.delete("/documents/{document_id}", summary="删除当前用户文档")
async def delete_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
):
    return delete_user_document(document_id=document_id, user_id=current_user.id)


@router.put("/documents/{document_id}", response_model=SingleUploadResponse, summary="替换当前用户文档内容")
async def update_document(
    document_id: UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    temp_dir: str | None = None

    try:
        ensure_user_document(document_id=document_id, user_id=current_user.id)
        safe_filename = _validate_pdf_upload_filename(file.filename)

        temp_dir = tempfile.mkdtemp()
        temp_pdf_path = os.path.join(temp_dir, f"{document_id.hex}.pdf")

        total_written = 0
        with open(temp_pdf_path, "wb") as buffer:
            while True:
                chunk = await file.read(COPY_CHUNK_BYTES)
                if not chunk:
                    break

                total_written += len(chunk)
                if total_written > MAX_PDF_BYTES:
                    raise HTTPException(status_code=413, detail="PDF 文件超过允许的大小上限")

                buffer.write(chunk)

        _assert_pdf_magic_and_nonempty(temp_pdf_path)

        return update_knowledge_base_from_saved_pdf(
            document_id=document_id,
            temp_pdf_path=temp_pdf_path,
            safe_filename=safe_filename,
            user_id=current_user.id,
            content_type=file.content_type or "application/pdf",
        )
    except HTTPException:
        raise
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except OSError as e:
        logger.exception("保存或读取更新 PDF 时发生系统错误: %s", e)
        raise HTTPException(status_code=500, detail="保存或读取上传文件失败，请稍后重试")
    except ValueError as e:
        logger.warning("更新 PDF 参数或数据无效: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("更新 PDF 时发生未预期错误")
        raise HTTPException(
            status_code=500,
            detail="服务器处理更新请求时发生错误，请稍后重试",
        ) from e
    finally:
        if temp_dir and os.path.isdir(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        await file.close()


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
