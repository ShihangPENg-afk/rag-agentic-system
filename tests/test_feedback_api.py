def test_feedback_requires_auth(client):
    response = client.post("/feedback", json={"rating": 5})

    assert response.status_code == 401


def test_feedback_accepts_authenticated_payload(client, register_user, auth_headers):
    register_user("feedback-user@example.com")

    response = client.post(
        "/feedback",
        headers=auth_headers("feedback-user@example.com"),
        json={
            "target_type": "answer",
            "target_id": "answer-001",
            "rating": 5,
            "comment": "useful",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["feedback_id"]
    assert body["status"] == "accepted"
    assert body["message"]
