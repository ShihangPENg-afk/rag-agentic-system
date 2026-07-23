from uuid import UUID

from sqlalchemy import func, select

from app.models import Chunk, ChunkEmbedding, Collection, Document
from app.services.embedding_service import get_embedding_model_name


def _create_vector_document(
    db_session,
    user_id: str,
    filename: str = "vector.pdf",
    content: str = "private vector chunk",
):
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
        chunks_count=1,
        status="ready",
    )
    db_session.add(document)
    db_session.flush()

    chunk = Chunk(
        document_id=document.id,
        collection_id=collection.id,
        user_id=user_uuid,
        chunk_index=0,
        content=content,
        content_hash="test-content-hash",
    )
    db_session.add(chunk)
    db_session.flush()

    embedding = ChunkEmbedding(
        chunk_id=chunk.id,
        document_id=document.id,
        collection_id=collection.id,
        user_id=user_uuid,
        embedding_model=get_embedding_model_name(),
        embedding_dimension=1536,
        embedding=[0.0] * 1536,
    )
    db_session.add(embedding)
    db_session.commit()
    db_session.refresh(collection)
    db_session.refresh(document)
    db_session.refresh(chunk)
    db_session.refresh(embedding)
    return collection, document, chunk, embedding


def test_unauthenticated_documents_fails(client):
    response = client.get("/documents/")

    assert response.status_code == 401


def test_authenticated_documents_success(
    client,
    register_user,
    auth_headers,
    create_document,
):
    owner = register_user("document-owner@example.com")
    other = register_user("other-document-owner@example.com")
    owned_document = create_document(owner["id"], filename="owned.pdf")
    create_document(other["id"], filename="other.pdf")

    response = client.get(
        "/documents/",
        headers=auth_headers("document-owner@example.com"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["documents"][0]["id"] == str(owned_document.id)
    assert body["documents"][0]["filename"] == "owned.pdf"
    assert body["documents"][0]["user_id"] == owner["id"]


def test_user_can_access_own_qa_logs(
    client,
    register_user,
    auth_headers,
    create_document,
    create_qa_log,
):
    owner = register_user("qa-owner@example.com")
    document = create_document(owner["id"])
    create_qa_log(document.id, question="private question", answer="private answer")

    response = client.get(
        f"/qa_logs/?knowledge_base_id={document.id}",
        headers=auth_headers("qa-owner@example.com"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["knowledge_base_id"] == str(document.id)
    assert body["total"] == 1
    assert body["qa_logs"][0]["question"] == "private question"


def test_user_cannot_access_another_users_qa_logs(
    client,
    register_user,
    auth_headers,
    create_document,
    create_qa_log,
):
    owner = register_user("qa-private-owner@example.com")
    register_user("qa-intruder@example.com")
    document = create_document(owner["id"])
    create_qa_log(document.id)

    response = client.get(
        f"/qa_logs/?knowledge_base_id={document.id}",
        headers=auth_headers("qa-intruder@example.com"),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Not enough permissions"


def test_delete_document_removes_chunks_and_embeddings(
    client,
    register_user,
    auth_headers,
    db_session,
):
    owner = register_user("delete-owner@example.com")
    _collection, document, _chunk, _embedding = _create_vector_document(
        db_session,
        user_id=owner["id"],
        filename="delete-me.pdf",
    )
    document_id = document.id

    response = client.delete(
        f"/documents/{document_id}",
        headers=auth_headers("delete-owner@example.com"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["document_id"] == str(document_id)
    assert body["deleted"] is True
    assert body["chunks_deleted"] == 1
    assert body["embeddings_deleted"] == 1

    db_session.expire_all()
    assert db_session.get(Document, document_id) is None
    assert (
        db_session.scalar(
            select(func.count()).select_from(Chunk).where(Chunk.document_id == document_id)
        )
        == 0
    )
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(ChunkEmbedding)
            .where(ChunkEmbedding.document_id == document_id)
        )
        == 0
    )


def test_user_cannot_delete_another_users_document(
    client,
    register_user,
    auth_headers,
    db_session,
):
    owner = register_user("delete-private-owner@example.com")
    register_user("delete-intruder@example.com")
    _collection, document, _chunk, _embedding = _create_vector_document(
        db_session,
        user_id=owner["id"],
        filename="private-delete.pdf",
    )

    response = client.delete(
        f"/documents/{document.id}",
        headers=auth_headers("delete-intruder@example.com"),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Not enough permissions"
    assert db_session.get(Document, document.id) is not None


def test_update_document_replaces_chunks_embeddings_and_updates_metadata(
    client,
    monkeypatch,
    register_user,
    auth_headers,
    db_session,
):
    owner = register_user("update-owner@example.com")
    collection, document, old_chunk, old_embedding = _create_vector_document(
        db_session,
        user_id=owner["id"],
        filename="old.pdf",
        content="old private chunk",
    )
    document_id = document.id
    old_chunk_id = old_chunk.id
    old_embedding_id = old_embedding.id
    old_updated_at = document.updated_at
    new_embedding = [0.02] * 1536

    monkeypatch.setattr(
        "app.services.upload_service.build_chunks_and_embeddings_from_pdf",
        lambda _path: (["new first chunk", "new second chunk"], [new_embedding, new_embedding], 1536),
    )
    monkeypatch.setattr("app.services.upload_service.build_faiss_index", lambda *a, **k: None)

    response = client.put(
        f"/documents/{document_id}",
        headers=auth_headers("update-owner@example.com"),
        files={"file": ("updated.pdf", b"%PDF-1.4\nupdated pdf", "application/pdf")},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["knowledge_base_id"] == str(document_id)
    assert body["collection_id"] == str(collection.id)
    assert body["filename"] == "updated.pdf"
    assert body["chunks_count"] == 2

    db_session.expire_all()
    updated_document = db_session.get(Document, document_id)
    assert updated_document is not None
    assert updated_document.filename == "updated.pdf"
    assert updated_document.chunks_count == 2
    assert updated_document.updated_at != old_updated_at
    assert db_session.get(Chunk, old_chunk_id) is None
    assert db_session.get(ChunkEmbedding, old_embedding_id) is None

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
        select(func.count()).select_from(ChunkEmbedding).where(
            ChunkEmbedding.document_id == document_id
        )
    )
    assert [chunk.content for chunk in chunks] == ["new first chunk", "new second chunk"]
    assert embeddings_count == 2


def test_update_document_embedding_failure_keeps_existing_chunks_and_embeddings(
    client,
    monkeypatch,
    register_user,
    auth_headers,
    db_session,
):
    owner = register_user("update-failure-owner@example.com")
    _collection, document, old_chunk, old_embedding = _create_vector_document(
        db_session,
        user_id=owner["id"],
        filename="stable.pdf",
        content="stable old chunk",
    )
    document_id = document.id
    old_chunk_id = old_chunk.id
    old_embedding_id = old_embedding.id
    old_updated_at = document.updated_at

    def fail_embedding(_path):
        raise ValueError("embedding failed")

    monkeypatch.setattr(
        "app.services.upload_service.build_chunks_and_embeddings_from_pdf",
        fail_embedding,
    )
    monkeypatch.setattr(
        "app.services.upload_service.build_faiss_index",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("FAISS should not be built")),
    )

    response = client.put(
        f"/documents/{document_id}",
        headers=auth_headers("update-failure-owner@example.com"),
        files={"file": ("failed.pdf", b"%PDF-1.4\nfailed pdf", "application/pdf")},
    )

    assert response.status_code == 400
    assert "embedding failed" in response.json()["detail"]

    db_session.expire_all()
    document_after_failure = db_session.get(Document, document_id)
    assert document_after_failure is not None
    assert document_after_failure.filename == "stable.pdf"
    assert document_after_failure.chunks_count == 1
    assert document_after_failure.updated_at == old_updated_at
    assert db_session.get(Chunk, old_chunk_id) is not None
    assert db_session.get(ChunkEmbedding, old_embedding_id) is not None


def test_user_cannot_update_another_users_document(
    client,
    monkeypatch,
    register_user,
    auth_headers,
    db_session,
):
    owner = register_user("update-private-owner@example.com")
    register_user("update-intruder@example.com")
    _collection, document, _old_chunk, _old_embedding = _create_vector_document(
        db_session,
        user_id=owner["id"],
        filename="private-update.pdf",
    )

    def fail_if_called(_path):
        raise AssertionError("document rebuild should not run for unauthorized update")

    monkeypatch.setattr(
        "app.services.upload_service.build_chunks_and_embeddings_from_pdf",
        fail_if_called,
    )

    response = client.put(
        f"/documents/{document.id}",
        headers=auth_headers("update-intruder@example.com"),
        files={"file": ("intruder.pdf", b"%PDF-1.4\nintruder pdf", "application/pdf")},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Not enough permissions"
    assert db_session.get(Document, document.id) is not None


def test_retrieve_chunks_passes_user_document_and_collection_filters(
    client,
    monkeypatch,
    register_user,
    auth_headers,
    db_session,
):
    owner = register_user("retrieve-owner@example.com")
    collection, document, chunk, _embedding = _create_vector_document(
        db_session,
        user_id=owner["id"],
        filename="retrieve.pdf",
        content="retrievable private chunk",
    )
    captured = {}

    def fake_retrieve_similar_chunks(**kwargs):
        captured.update(kwargs)
        return (
            [
                {
                    "chunk_id": str(chunk.id),
                    "document_id": str(document.id),
                    "collection_id": str(collection.id),
                    "score": 0.98,
                    "content": chunk.content,
                }
            ],
            None,
        )

    monkeypatch.setattr(
        "app.api.routes_documents.retrieve_similar_chunks",
        fake_retrieve_similar_chunks,
    )

    response = client.post(
        "/documents/retrieve",
        headers=auth_headers("retrieve-owner@example.com"),
        json={
            "query": "private chunk",
            "document_id": str(document.id),
            "collection_id": str(collection.id),
            "limit": 5,
        },
    )

    assert response.status_code == 200
    assert str(captured["user_id"]) == owner["id"]
    assert str(captured["document_id"]) == str(document.id)
    assert str(captured["collection_id"]) == str(collection.id)
    assert captured["limit"] == 5
    body = response.json()
    assert body["total"] == 1
    assert body["chunks"][0]["chunk_id"] == str(chunk.id)
    assert body["chunks"][0]["document_id"] == str(document.id)
    assert body["chunks"][0]["score"] == 0.98
    assert body["chunks"][0]["content"] == chunk.content


def test_user_cannot_retrieve_another_users_document(
    client,
    monkeypatch,
    register_user,
    auth_headers,
    db_session,
):
    owner = register_user("retrieve-private-owner@example.com")
    register_user("retrieve-intruder@example.com")
    _collection, document, _chunk, _embedding = _create_vector_document(
        db_session,
        user_id=owner["id"],
        filename="private-retrieve.pdf",
    )

    def fail_if_called(**kwargs):
        raise AssertionError("retriever should not be called for unauthorized document")

    monkeypatch.setattr(
        "app.api.routes_documents.retrieve_similar_chunks",
        fail_if_called,
    )

    response = client.post(
        "/documents/retrieve",
        headers=auth_headers("retrieve-intruder@example.com"),
        json={
            "query": "private chunk",
            "document_id": str(document.id),
            "limit": 3,
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Not enough permissions"
