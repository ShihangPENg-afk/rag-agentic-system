def test_register_user_success(client, user_password):
    response = client.post(
        "/auth/register",
        json={"email": "new-user@example.com", "password": user_password},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "new-user@example.com"
    assert body["is_active"] is True
    assert body["id"]
    assert body["created_at"]
    assert "password" not in body
    assert "hashed_password" not in body


def test_register_duplicate_email_fails(client, user_password):
    payload = {"email": "duplicate@example.com", "password": user_password}

    first_response = client.post("/auth/register", json=payload)
    second_response = client.post("/auth/register", json=payload)

    assert first_response.status_code == 200
    assert second_response.status_code == 409
    assert second_response.json()["detail"] == "Email already registered"


def test_login_success_returns_token(client, register_user, user_password):
    register_user("login@example.com")

    response = client.post(
        "/auth/login",
        json={"email": "login@example.com", "password": user_password},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str)
    assert body["access_token"]
