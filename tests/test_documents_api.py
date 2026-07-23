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
