import math
from uuid import UUID

from sqlalchemy import func, select

from app.models import Chunk, ChunkEmbedding
from app.retrievers.retriever_v2_pgvector import retrieve_similar_chunks
from app.services.embedding_service import get_embedding_provider, get_embeddings


def _stub_pdf_chunks(monkeypatch, chunks: list[str]) -> None:
    assert get_embedding_provider().name == "fake"
    embeddings, dimension = get_embeddings(chunks)
    monkeypatch.setattr(
        "app.services.upload_service.build_chunks_and_embeddings_from_pdf",
        lambda _path: (chunks, embeddings, dimension),
    )
    monkeypatch.setattr("app.services.upload_service.build_faiss_index", lambda *a, **k: None)


def _patch_sqlite_vector_search(monkeypatch, db_session) -> None:
    def fake_search_similar_chunks(
        *,
        query_embedding,
        user_id,
        document_id=None,
        collection_id=None,
        limit=3,
        embedding_model=None,
    ):
        db_session.expire_all()
        stmt = (
            select(ChunkEmbedding, Chunk)
            .join(Chunk, Chunk.id == ChunkEmbedding.chunk_id)
            .where(ChunkEmbedding.user_id == UUID(str(user_id)))
            .where(Chunk.user_id == UUID(str(user_id)))
        )
        if document_id is not None:
            stmt = stmt.where(ChunkEmbedding.document_id == UUID(str(document_id)))
            stmt = stmt.where(Chunk.document_id == UUID(str(document_id)))
        if collection_id is not None:
            stmt = stmt.where(ChunkEmbedding.collection_id == UUID(str(collection_id)))
            stmt = stmt.where(Chunk.collection_id == UUID(str(collection_id)))

        results = []
        for embedding_row, chunk in db_session.execute(stmt).all():
            distance = math.sqrt(
                sum(
                    (float(query_value) - float(chunk_value)) ** 2
                    for query_value, chunk_value in zip(query_embedding, embedding_row.embedding)
                )
            )
            results.append(
                {
                    "chunk_id": str(chunk.id),
                    "document_id": str(chunk.document_id),
                    "collection_id": str(chunk.collection_id) if chunk.collection_id else None,
                    "score": 1.0 / (1.0 + distance),
                    "distance": distance,
                    "content": chunk.content,
                }
            )

        return sorted(results, key=lambda item: item["distance"])[:limit]

    monkeypatch.setattr(
        "app.retrievers.retriever_v2_pgvector.search_similar_chunks",
        fake_search_similar_chunks,
    )


def _upload_pdf(client, headers, filename: str = "kb.pdf") -> dict:
    response = client.post(
        "/upload_pdf/",
        headers=headers,
        files={"file": (filename, b"%PDF-1.4\nfake test pdf", "application/pdf")},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _update_pdf(client, headers, document_id: str, filename: str = "updated.pdf") -> dict:
    response = client.put(
        f"/documents/{document_id}",
        headers=headers,
        files={"file": (filename, b"%PDF-1.4\nupdated test pdf", "application/pdf")},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_upload_document_generates_persisted_chunks(
    client,
    monkeypatch,
    register_user,
    auth_headers,
    db_session,
):
    user = register_user("kb-upload-owner@example.com")
    _stub_pdf_chunks(monkeypatch, ["alpha persisted chunk", "beta persisted chunk"])

    body = _upload_pdf(
        client,
        auth_headers("kb-upload-owner@example.com"),
        filename="upload-source.pdf",
    )
    document_id = UUID(body["knowledge_base_id"])

    db_session.expire_all()
    chunks = (
        db_session.execute(
            select(Chunk)
            .where(Chunk.document_id == document_id)
            .order_by(Chunk.chunk_index.asc())
        )
        .scalars()
        .all()
    )
    embeddings_count = db_session.scalar(
        select(func.count())
        .select_from(ChunkEmbedding)
        .where(ChunkEmbedding.document_id == document_id)
    )

    assert body["chunks_count"] == 2
    assert [chunk.content for chunk in chunks] == [
        "alpha persisted chunk",
        "beta persisted chunk",
    ]
    assert {str(chunk.user_id) for chunk in chunks} == {user["id"]}
    assert embeddings_count == 2


def test_retrieval_returns_related_persisted_chunk(
    client,
    monkeypatch,
    register_user,
    auth_headers,
    db_session,
):
    register_user("kb-retrieve-owner@example.com")
    _stub_pdf_chunks(monkeypatch, ["alpha retrieval chunk", "beta retrieval chunk"])
    _patch_sqlite_vector_search(monkeypatch, db_session)

    upload = _upload_pdf(client, auth_headers("kb-retrieve-owner@example.com"))

    response = client.post(
        "/documents/retrieve",
        headers=auth_headers("kb-retrieve-owner@example.com"),
        json={
            "query": "beta retrieval chunk",
            "document_id": upload["knowledge_base_id"],
            "collection_id": upload["collection_id"],
            "limit": 1,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    assert body["chunks"][0]["document_id"] == upload["knowledge_base_id"]
    assert body["chunks"][0]["content"] == "beta retrieval chunk"


def test_deleted_document_chunks_are_not_retrievable(
    client,
    monkeypatch,
    register_user,
    auth_headers,
    db_session,
):
    user = register_user("kb-delete-owner@example.com")
    _stub_pdf_chunks(monkeypatch, ["delete target chunk"])
    _patch_sqlite_vector_search(monkeypatch, db_session)
    headers = auth_headers("kb-delete-owner@example.com")
    upload = _upload_pdf(client, headers)

    delete_response = client.delete(f"/documents/{upload['knowledge_base_id']}", headers=headers)
    assert delete_response.status_code == 200, delete_response.text

    results, error = retrieve_similar_chunks(
        query="delete target chunk",
        user_id=user["id"],
        document_id=upload["knowledge_base_id"],
        collection_id=upload["collection_id"],
        limit=3,
    )

    assert results == []
    assert error.startswith("📚")
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(Chunk)
            .where(Chunk.document_id == UUID(upload["knowledge_base_id"]))
        )
        == 0
    )


def test_updated_document_does_not_return_old_chunk(
    client,
    monkeypatch,
    register_user,
    auth_headers,
    db_session,
):
    register_user("kb-update-owner@example.com")
    headers = auth_headers("kb-update-owner@example.com")
    _patch_sqlite_vector_search(monkeypatch, db_session)

    _stub_pdf_chunks(monkeypatch, ["old update chunk"])
    upload = _upload_pdf(client, headers, filename="old.pdf")

    _stub_pdf_chunks(monkeypatch, ["new update chunk"])
    update = _update_pdf(client, headers, upload["knowledge_base_id"], filename="new.pdf")

    response = client.post(
        "/documents/retrieve",
        headers=headers,
        json={
            "query": "old update chunk",
            "document_id": upload["knowledge_base_id"],
            "collection_id": upload["collection_id"],
            "limit": 3,
        },
    )

    assert response.status_code == 200, response.text
    contents = [item["content"] for item in response.json()["chunks"]]
    assert "old update chunk" not in contents
    assert update["chunks_count"] == 1

    db_session.expire_all()
    persisted_contents = [
        chunk.content
        for chunk in db_session.execute(
            select(Chunk).where(Chunk.document_id == UUID(upload["knowledge_base_id"]))
        )
        .scalars()
        .all()
    ]
    assert persisted_contents == ["new update chunk"]


def test_user_cannot_retrieve_another_users_document(
    client,
    monkeypatch,
    register_user,
    auth_headers,
):
    register_user("kb-private-owner@example.com")
    register_user("kb-private-viewer@example.com")
    _stub_pdf_chunks(monkeypatch, ["private owner chunk"])
    upload = _upload_pdf(client, auth_headers("kb-private-owner@example.com"))

    def fail_if_called(**kwargs):
        raise AssertionError("retrieval should stop at permission validation")

    monkeypatch.setattr(
        "app.retrievers.retriever_v2_pgvector.search_similar_chunks",
        fail_if_called,
    )

    response = client.post(
        "/documents/retrieve",
        headers=auth_headers("kb-private-viewer@example.com"),
        json={
            "query": "private owner chunk",
            "document_id": upload["knowledge_base_id"],
            "collection_id": upload["collection_id"],
            "limit": 1,
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Not enough permissions"
