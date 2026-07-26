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
        "message": "Industrial Maintenance Agent Platform API",
        "docs_url": "/docs",
        "endpoints": {
            "auth_register": "POST /auth/register - 注册用户",
            "auth_login": "POST /auth/login - 获取 Bearer token",
            "upload_single": "POST /documents/upload - 上传单个 PDF 并构建知识库",
            "upload_legacy": "POST /upload_pdf/ - 兼容旧上传路径",
            "ask": "POST /ask 或 /chat - RAG + LangGraph Agent 问答入口",
            "ask_stream": "POST /ask/stream - 通用问答 SSE 流式接口",
            "agent_invoke": "POST /agent/invoke - 工业运维 Agent 调用",
            "agent_stream": "POST /agent/stream - 工业运维 Agent SSE 流式接口",
            "agent_confirm": "POST /agent/confirm - 高风险动作确认",
            "feedback": "POST /feedback - 用户反馈",
            "retrieve": "POST /documents/retrieve - 文档片段检索",
            "list_documents": "GET /documents/ - 当前用户文档列表",
            "list_qa_logs": "GET /qa_logs/?knowledge_base_id=... - 当前用户历史问答",
            "list_kbs": "GET /knowledge_bases - 查看当前进程知识库",
        },
    }
