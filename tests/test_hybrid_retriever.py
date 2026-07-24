from uuid import UUID

from app.models import Chunk, ChunkEmbedding, Collection, Document
from app.agent.nodes import make_agent_tools
from app.retrievers.retriever_v2_hybrid import retrieve_similar_chunks
from app.services.embedding_service import get_embedding_model_name, get_embeddings


def _create_hybrid_document(
    db_session,
    *,
    user_id: str,
    filename: str,
    chunks: list[str],
) -> tuple[Collection, Document, list[Chunk]]:
    user_uuid = UUID(user_id)
    collection = Collection(
        user_id=user_uuid,
        name=f"collection-{filename}",
        status="ready",
    )
    db_session.add(collection)
    db_session.flush()

    document = Document(
        user_id=user_uuid,
        collection_id=collection.id,
        filename=filename,
        content_type="application/pdf",
        chunks_count=len(chunks),
        status="ready",
    )
    db_session.add(document)
    db_session.flush()

    embeddings, dimension = get_embeddings(chunks)
    chunk_rows: list[Chunk] = []
    for index, (content, embedding) in enumerate(zip(chunks, embeddings)):
        chunk = Chunk(
            document_id=document.id,
            collection_id=collection.id,
            user_id=user_uuid,
            chunk_index=index,
            content=content,
            content_hash=f"hash-{filename}-{index}",
            char_start=index * 100,
            char_end=index * 100 + len(content),
            metadata_json={"source": filename, "page": index + 1},
        )
        db_session.add(chunk)
        db_session.flush()
        db_session.add(
            ChunkEmbedding(
                chunk_id=chunk.id,
                document_id=document.id,
                collection_id=collection.id,
                user_id=user_uuid,
                embedding_model=get_embedding_model_name(),
                embedding_dimension=dimension,
                embedding=embedding,
            )
        )
        chunk_rows.append(chunk)

    db_session.commit()
    db_session.refresh(collection)
    db_session.refresh(document)
    for chunk in chunk_rows:
        db_session.refresh(chunk)
    return collection, document, chunk_rows


def test_hybrid_retriever_fuses_dense_and_bm25_with_source_metadata(
    db_session,
    register_user,
):
    user = register_user("hybrid-owner@example.com")
    collection, document, chunks = _create_hybrid_document(
        db_session,
        user_id=user["id"],
        filename="hybrid.pdf",
        chunks=[
            "pump thermal bearing failure maintenance manual",
            "invoice billing payment finance terms",
            "general lubrication inspection schedule",
        ],
    )

    results, error = retrieve_similar_chunks(
        query="thermal pump failure",
        user_id=user["id"],
        document_id=document.id,
        collection_id=collection.id,
        top_k=1,
    )

    assert error is None
    assert len(results) == 1
    result = results[0]
    assert result["chunk_id"] == str(chunks[0].id)
    assert result["document_id"] == str(document.id)
    assert result["content"] == chunks[0].content
    assert result["dense_score"] > 0
    assert result["bm25_score"] > 0
    assert result["final_score"] > 0
    assert result["score"] == result["final_score"]

    source_metadata = result["source_metadata"]
    assert source_metadata["document_filename"] == "hybrid.pdf"
    assert source_metadata["collection_id"] == str(collection.id)
    assert source_metadata["collection_name"] == "collection-hybrid.pdf"
    assert source_metadata["chunk_index"] == 0
    assert source_metadata["chunk_metadata"] == {"source": "hybrid.pdf", "page": 1}
    assert set(source_metadata["retrieval_sources"]) == {"pgvector", "bm25"}


def test_hybrid_retriever_respects_document_and_collection_filters(
    db_session,
    register_user,
):
    user = register_user("hybrid-filter-owner@example.com")
    target_collection, target_document, _chunks = _create_hybrid_document(
        db_session,
        user_id=user["id"],
        filename="target.pdf",
        chunks=["shared keyword target chunk"],
    )
    other_collection, other_document, _other_chunks = _create_hybrid_document(
        db_session,
        user_id=user["id"],
        filename="other.pdf",
        chunks=["shared keyword other chunk"],
    )

    results, error = retrieve_similar_chunks(
        query="shared keyword",
        user_id=user["id"],
        document_id=target_document.id,
        collection_id=target_collection.id,
        top_k=5,
    )

    assert error is None
    assert results
    assert {item["document_id"] for item in results} == {str(target_document.id)}
    assert {item["collection_id"] for item in results} == {str(target_collection.id)}
    assert str(other_document.id) not in {item["document_id"] for item in results}
    assert str(other_collection.id) not in {item["collection_id"] for item in results}


def test_documents_retrieve_v2_returns_hybrid_metadata_and_honors_top_k(
    client,
    db_session,
    register_user,
    auth_headers,
):
    user = register_user("hybrid-api-owner@example.com")
    collection, document, _chunks = _create_hybrid_document(
        db_session,
        user_id=user["id"],
        filename="hybrid-api.pdf",
        chunks=[
            "alpha hybrid keyword chunk",
            "beta hybrid keyword chunk",
            "gamma unrelated material",
        ],
    )

    response = client.post(
        "/documents/retrieve",
        headers=auth_headers("hybrid-api-owner@example.com"),
        json={
            "query": "hybrid keyword",
            "document_id": str(document.id),
            "collection_id": str(collection.id),
            "retriever_version": "v2",
            "top_k": 2,
            "use_rerank": True,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 2
    for item in body["chunks"]:
        assert item["dense_score"] is not None
        assert item["bm25_score"] is not None
        assert item["final_score"] is not None
        assert item["rerank_score"] is not None
        assert item["source_metadata"]["document_filename"] == "hybrid-api.pdf"
        assert item["source_metadata"]["retrieval_sources"]
        assert item["source_metadata"]["reranker"]["provider"] == "mock"


def test_hybrid_retriever_can_rerank_candidates(
    db_session,
    register_user,
):
    user = register_user("hybrid-rerank-owner@example.com")
    collection, document, chunks = _create_hybrid_document(
        db_session,
        user_id=user["id"],
        filename="rerank.pdf",
        chunks=[
            "billing invoice payment",
            "pump thermal failure maintenance",
        ],
    )

    results, error = retrieve_similar_chunks(
        query="pump thermal failure",
        user_id=user["id"],
        document_id=document.id,
        collection_id=collection.id,
        top_k=1,
        use_rerank=True,
    )

    assert error is None
    assert len(results) == 1
    assert results[0]["chunk_id"] == str(chunks[1].id)
    assert results[0]["rerank_score"] > 0
    assert results[0]["source_metadata"]["reranker"]["provider"] == "mock"


def test_agent_retrieve_tool_passes_retriever_version_and_top_k(monkeypatch):
    captured = {}

    def fake_retrieve_chunks_tool(**kwargs):
        captured.update(kwargs)
        return "ok"

    monkeypatch.setattr("app.agent.nodes.retrieve_chunks_tool", fake_retrieve_chunks_tool)

    tools = make_agent_tools(
        knowledge_base_id="kb-id",
        user_id="user-id",
        collection_id="collection-id",
        retriever_version="v2",
        top_k=7,
        use_rerank=True,
        history_pairs=[],
    )

    assert tools[0].invoke({"query": "pump"}) == "ok"
    assert captured["retriever_version"] == "v2"
    assert captured["limit"] == 7
    assert captured["use_rerank"] is True
