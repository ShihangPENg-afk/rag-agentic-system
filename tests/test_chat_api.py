def test_unauthenticated_chat_sessions_fails(client):
    response = client.get("/chat/sessions")

    assert response.status_code == 401


def test_authenticated_chat_sessions_success(
    client,
    register_user,
    auth_headers,
    create_chat_session,
):
    user = register_user("chat-owner@example.com")
    create_chat_session(user["id"], title="Owned session")

    response = client.get(
        "/chat/sessions",
        headers=auth_headers("chat-owner@example.com"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["sessions"][0]["title"] == "Owned session"
    assert body["sessions"][0]["user_id"] == user["id"]


def test_ask_rag_success_with_mocked_llm(
    client,
    monkeypatch,
    register_user,
    auth_headers,
    create_document,
):
    user = register_user("rag-user@example.com")
    document = create_document(user["id"])

    monkeypatch.setattr("app.api.routes_chat.increment_chat_rate_limit", lambda *a, **k: 1)
    monkeypatch.setattr("app.api.routes_chat.check_network", lambda: True)
    monkeypatch.setattr(
        "app.api.routes_chat.chat_with_rag_state",
        lambda state: ("mocked RAG answer", [(state.user_query, "mocked RAG answer")]),
    )

    response = client.post(
        "/ask_rag/",
        headers=auth_headers("rag-user@example.com"),
        json={
            "question": "What is in the document?",
            "knowledge_base_id": str(document.id),
            "history": [],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "mocked RAG answer"
    assert "confidence" in body
    assert "sources" in body
    assert body["knowledge_base_id"] == str(document.id)
    assert body["session_id"]
    assert body["mode"] == "rag"


def test_ask_rag_passes_retriever_version_and_top_k(
    client,
    monkeypatch,
    register_user,
    auth_headers,
    create_document,
):
    user = register_user("rag-hybrid-user@example.com")
    document = create_document(user["id"])
    captured = {}

    monkeypatch.setattr("app.api.routes_chat.increment_chat_rate_limit", lambda *a, **k: 1)
    monkeypatch.setattr("app.api.routes_chat.check_network", lambda: True)

    def fake_chat_with_rag_state(state):
        captured["retriever_version"] = state.retriever_version
        captured["top_k"] = state.top_k
        captured["use_rerank"] = state.use_rerank
        return "mocked hybrid RAG answer", [(state.user_query, "mocked hybrid RAG answer")]

    monkeypatch.setattr(
        "app.api.routes_chat.chat_with_rag_state",
        fake_chat_with_rag_state,
    )

    response = client.post(
        "/ask_rag/",
        headers=auth_headers("rag-hybrid-user@example.com"),
        json={
            "question": "What is in the document?",
            "knowledge_base_id": str(document.id),
            "retriever_version": "v2",
            "top_k": 7,
            "use_rerank": True,
            "history": [],
        },
    )

    assert response.status_code == 200
    assert captured == {"retriever_version": "v2", "top_k": 7, "use_rerank": True}


def test_user_cannot_access_another_users_chat_messages(
    client,
    register_user,
    auth_headers,
    create_chat_session,
    create_message,
):
    owner = register_user("chat-owner@example.com")
    register_user("chat-viewer@example.com")
    session = create_chat_session(owner["id"], title="Private session")
    create_message(session.id, role="user", content="private question")
    create_message(session.id, role="assistant", content="private answer")

    response = client.get(
        f"/chat/sessions/{session.id}/messages",
        headers=auth_headers("chat-viewer@example.com"),
    )

    assert response.status_code == 403
    assert "会话不属于当前用户" in response.json()["detail"]
