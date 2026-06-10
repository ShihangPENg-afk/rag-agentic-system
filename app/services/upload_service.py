import uuid

from rag import RAGSystem
from app.services.kb_registry import register_knowledge_base


def create_knowledge_base_from_saved_pdf(temp_pdf_path: str, safe_filename: str) -> dict:
    """
    根据已保存到本地的 PDF 文件构建知识库，并注册到内存中。
    """
    rag_system = RAGSystem()
    success = rag_system.init_from_pdf(temp_pdf_path)

    if not success:
        raise ValueError("PDF处理失败，无法构建知识库")

    knowledge_base_id = str(uuid.uuid4())
    register_knowledge_base(knowledge_base_id, rag_system)

    return {
        "knowledge_base_id": knowledge_base_id,
        "status": "success",
        "message": f"知识库构建成功，包含 {len(rag_system.chunks)} 个文本块",
        "chunks_count": len(rag_system.chunks),
        "filename": safe_filename,
    }