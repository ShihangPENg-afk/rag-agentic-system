from uuid import UUID

from sqlalchemy import func, select

from app.models import Chunk, ChunkEmbedding, Collection, Document
from app.retrievers.retriever_v2_pgvector import retrieve_similar_chunks
from app.services.upload_service import create_knowledge_base_from_saved_pdf


def test_upload_service_persists_document_chunks_and_embeddings(
    tmp_path,
    monkeypatch,
    db_session,
    register_user,
):
    user = register_user("vector-owner@example.com")
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\nmock pdf")

    embedding = [0.01] * 1536
    monkeypatch.setattr(
        "app.services.upload_service.build_chunks_and_embeddings_from_pdf",
        lambda _path: (["first chunk", "second chunk"], [embedding, embedding], 1536),
    )
    monkeypatch.setattr("app.services.upload_service.build_faiss_index", lambda *a, **k: None)

    result = create_knowledge_base_from_saved_pdf(
        str(pdf_path),
        "sample.pdf",
        user_id=user["id"],
    )

    document_id = UUID(result["knowledge_base_id"])
    collection_id = UUID(result["collection_id"])

    document = db_session.get(Document, document_id)
    collection = db_session.get(Collection, collection_id)
    chunks_count = db_session.scalar(select(func.count()).select_from(Chunk))
    embeddings_count = db_session.scalar(select(func.count()).select_from(ChunkEmbedding))

    assert document is not None
    assert collection is not None
    assert document.user_id == UUID(user["id"])
    assert document.collection_id == collection_id
    assert document.chunks_count == 2
    assert document.status == "ready"
    assert chunks_count == 2
    assert embeddings_count == 2


def test_pgvector_retrieval_requires_user_id():
    results, error = retrieve_similar_chunks(
        query="private query",
        user_id=None,
    )

    assert results == []
    assert "用户权限" in error
