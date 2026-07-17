from fastapi import APIRouter

from app.services.kb_registry import count_knowledge_bases
from utils.utils import check_network

router = APIRouter()


@router.get("/health", summary="健康检查")
async def health_check():
    network_ok = check_network()
    return {
        "status": "healthy" if network_ok else "network_error",
        "network_connected": network_ok,
        "active_knowledge_bases": count_knowledge_bases(),
    }


@router.get("/", summary="API文档")
async def root():
    return {
        "message": "RAG PDF 智能问答系统 API",
        "docs_url": "/docs",
        "endpoints": {
            "upload_single": "POST /upload_pdf/ - 上传单个PDF",
            "upload_multiple": "POST /upload_pdfs/ - 批量上传多个PDF",
            "ask": "POST /ask/ - Agent 问答主入口",
            "ask_rag": "POST /ask_rag/ - 经典RAG回退入口",
            "list_kbs": "GET /knowledge_bases - 查看所有知识库",
            "list_documents": "GET /documents/ - 最近上传文档",
            "list_qa_logs": "GET /qa_logs/?knowledge_base_id=... - 历史问答",
            "delete_kb": "DELETE /knowledge_base/{id} - 删除指定知识库",
        },
    }
