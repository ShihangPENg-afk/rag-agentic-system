import os
from uuid import UUID

from app.db.session import SessionLocal
from app.repositories.vector_repository import (
    file_sha256,
    persist_document_chunks_embeddings,
    replace_document_chunks_embeddings,
)
from app.services.index_service import build_chunks_and_embeddings_from_pdf
from app.services.rag_service import RAGSystem
from app.services.kb_registry import register_knowledge_base
from app.vectordb.faiss_store import build_faiss_index


def create_knowledge_base_from_saved_pdf(
    temp_pdf_path: str,
    safe_filename: str,
    user_id: UUID | str | None = None,
    content_type: str = "application/pdf",
    collection_id: UUID | str | None = None,
) -> dict:
    """
    根据已保存到本地的 PDF 文件构建知识库，并持久化到 PostgreSQL + pgvector。
    """
    chunks, embeddings, dimension = build_chunks_and_embeddings_from_pdf(temp_pdf_path)
    if not chunks or not embeddings:
        raise ValueError("PDF处理失败，无法构建知识库")

    db = SessionLocal()
    try:
        persisted = persist_document_chunks_embeddings(
            db,
            filename=safe_filename,
            content_type=content_type,
            chunks=chunks,
            embeddings=embeddings,
            user_id=user_id,
            collection_id=collection_id,
            file_size=os.path.getsize(temp_pdf_path),
            content_hash=file_sha256(temp_pdf_path),
            embedding_dimension=dimension,
        )
    finally:
        db.close()

    document = persisted["document"]
    collection = persisted["collection"]
    knowledge_base_id = str(document.id)

    # 保留内存 FAISS 注册作为 v1 后备；重启后主路径会走 pgvector。
    index = build_faiss_index(embeddings, dimension)
    register_knowledge_base(
        knowledge_base_id,
        RAGSystem(index=index, chunks=chunks),
    )

    return {
        "knowledge_base_id": knowledge_base_id,
        "collection_id": str(collection.id),
        "status": "success",
        "message": f"知识库构建成功，包含 {len(chunks)} 个文本块",
        "chunks_count": len(chunks),
        "filename": safe_filename,
    }


def update_knowledge_base_from_saved_pdf(
    document_id: UUID | str,
    temp_pdf_path: str,
    safe_filename: str,
    user_id: UUID | str,
    content_type: str = "application/pdf",
) -> dict:
    """
    用新 PDF 内容替换已有文档的 chunks 和 embeddings。

    PDF 解析与 embedding 生成先于数据库事务执行；一旦失败，不会删除旧数据。
    """
    chunks, embeddings, dimension = build_chunks_and_embeddings_from_pdf(temp_pdf_path)
    if not chunks or not embeddings:
        raise ValueError("PDF处理失败，无法更新知识库")

    index = build_faiss_index(embeddings, dimension)

    db = SessionLocal()
    try:
        persisted = replace_document_chunks_embeddings(
            db,
            document_id=document_id,
            filename=safe_filename,
            content_type=content_type,
            chunks=chunks,
            embeddings=embeddings,
            user_id=user_id,
            file_size=os.path.getsize(temp_pdf_path),
            content_hash=file_sha256(temp_pdf_path),
            embedding_dimension=dimension,
        )
    finally:
        db.close()

    if persisted is None:
        raise LookupError("Document not found")

    document = persisted["document"]
    knowledge_base_id = str(document.id)
    register_knowledge_base(
        knowledge_base_id,
        RAGSystem(index=index, chunks=chunks),
    )

    return {
        "knowledge_base_id": knowledge_base_id,
        "collection_id": str(document.collection_id) if document.collection_id else None,
        "status": "success",
        "message": f"文档更新成功，包含 {len(chunks)} 个文本块",
        "chunks_count": len(chunks),
        "filename": safe_filename,
    }
