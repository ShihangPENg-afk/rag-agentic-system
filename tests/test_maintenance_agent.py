from app.services.agent_service import invoke_maintenance_agent


def _mock_retrieve_manual_result(document_id: str) -> dict:
    return {
        "chunks": [
            {
                "chunk_id": "chunk-manual-001",
                "document_id": document_id,
                "collection_id": None,
                "content": "报警后应先检查润滑、冷却和连接状态。",
                "score": 0.91,
                "final_score": 0.91,
                "source_metadata": {
                    "document_filename": "maintenance_manual.pdf",
                    "chunk_index": 3,
                },
            }
        ],
        "sources": [
            {
                "chunk_id": "chunk-manual-001",
                "document_id": document_id,
                "collection_id": None,
                "content": "报警后应先检查润滑、冷却和连接状态。",
                "score": 0.91,
                "final_score": 0.91,
                "source_metadata": {
                    "document_filename": "maintenance_manual.pdf",
                    "chunk_index": 3,
                },
            }
        ],
        "confidence": 0.91,
        "error": None,
        "retriever_version": "v2",
    }


def _mock_health_result(risk_level: str = "low", risk_score: float = 0.2) -> dict:
    return {
        "machine_id": "MACHINE-001",
        "provider": "mock-test",
        "prediction": "abnormal" if risk_level == "high" else "normal",
        "risk_level": risk_level,
        "risk_score": risk_score,
        "recommendation": "测试预测建议",
        "probabilities": {risk_level: risk_score},
    }


def test_maintenance_agent_service_runs_with_mock_health():
    result = invoke_maintenance_agent(
        user_input="设备温度偏高，请给出维护建议",
        machine_id="MACHINE-001",
        sensor_data={"temperature": 82, "vibration": 0.3},
    )

    assert result["risk_level"] == "high"
    assert result["confirmation_required"] is True
    assert result["ticket"] is None
    assert "retrieve_manual_node" in result["tools_used"]
    assert "check_machine_health" in result["tools_used"]
    assert "generate_maintenance_plan" in result["tools_used"]
    assert "require_confirmation_node" in result["tools_used"]
    assert "create_ticket_mock" not in result["tools_used"]
    assert result["sources"] == []
    assert result["final_answer"]


def test_maintenance_agent_creates_ticket_after_confirmation():
    result = invoke_maintenance_agent(
        user_input="确认创建工单，设备温度偏高，请给出维护建议",
        machine_id="MACHINE-001",
        sensor_data={"temperature": 82, "vibration": 0.3},
        confirm_create_ticket=True,
    )

    assert result["risk_level"] == "high"
    assert result["confirmation_required"] is False
    assert result["ticket"]["status"] == "mock_created"
    assert "create_ticket_node" in result["tools_used"]
    assert "create_ticket_mock" in result["tools_used"]


def test_agent_invoke_endpoint_returns_required_fields(
    client,
    register_user,
    auth_headers,
):
    register_user("maintenance-agent@example.com")

    response = client.post(
        "/agent/invoke",
        headers=auth_headers("maintenance-agent@example.com"),
        json={
            "user_input": "设备振动升高，帮我判断风险并给维护建议",
            "machine_id": "PUMP-009",
            "sensor_data": {"temperature": 58, "vibration": 0.9},
            "confirm_create_ticket": True,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["final_answer"]
    assert body["risk_level"] == "high"
    assert body["session_id"]
    assert body["confirmation_required"] is False
    assert body["ticket"]["status"] == "mock_created"
    assert body["sources"] == []
    assert "list_history" in body["tools_used"]
    assert "check_machine_health" in body["tools_used"]
    assert "create_ticket_mock" in body["tools_used"]


def test_agent_invoke_manual_question_uses_retrieval_and_returns_sources(
    client,
    monkeypatch,
    register_user,
    auth_headers,
    create_document,
):
    user = register_user("agent-manual@example.com")
    document = create_document(user["id"])

    monkeypatch.setattr(
        "app.agents.maintenance_agent.tools.retrieve_manual",
        lambda **kwargs: _mock_retrieve_manual_result(str(document.id)),
    )
    monkeypatch.setattr(
        "app.agents.maintenance_agent.tools.check_machine_health",
        lambda **kwargs: _mock_health_result("low", 0.2),
    )

    response = client.post(
        "/agent/invoke",
        headers=auth_headers("agent-manual@example.com"),
        json={
            "user_input": "请查询维护手册里报警后的检查建议",
            "machine_id": "MACHINE-001",
            "knowledge_base_id": str(document.id),
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["risk_level"] == "low"
    assert body["confirmation_required"] is False
    assert body["sources"][0]["chunk_id"] == "chunk-manual-001"
    assert body["sources"][0]["source_metadata"]["document_filename"] == "maintenance_manual.pdf"
    assert "retrieve_manual_node" in body["tools_used"]
    assert "retrieve_manual" in body["tools_used"]
    assert "final_response_node" in body["tools_used"]


def test_agent_invoke_health_check_uses_mocked_prediction(
    client,
    monkeypatch,
    register_user,
    auth_headers,
):
    register_user("agent-health@example.com")
    called = {"health": False}

    def fake_check_machine_health(**kwargs):
        called["health"] = True
        assert kwargs["machine_id"] == "MACHINE-002"
        return _mock_health_result("medium", 0.55)

    monkeypatch.setattr(
        "app.agents.maintenance_agent.tools.check_machine_health",
        fake_check_machine_health,
    )

    response = client.post(
        "/agent/invoke",
        headers=auth_headers("agent-health@example.com"),
        json={
            "user_input": "请检查设备当前健康状态",
            "machine_id": "MACHINE-002",
            "sensor_data": {"temperature": 70, "vibration": 0.4},
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert called["health"] is True
    assert body["risk_level"] == "medium"
    assert body["ticket"] is None
    assert "check_health_node" in body["tools_used"]
    assert "check_machine_health" in body["tools_used"]


def test_agent_invoke_high_risk_requires_confirmation(
    client,
    monkeypatch,
    register_user,
    auth_headers,
):
    register_user("agent-high-risk@example.com")
    monkeypatch.setattr(
        "app.agents.maintenance_agent.tools.check_machine_health",
        lambda **kwargs: _mock_health_result("high", 0.9),
    )

    response = client.post(
        "/agent/invoke",
        headers=auth_headers("agent-high-risk@example.com"),
        json={
            "user_input": "设备温度异常，请判断风险",
            "machine_id": "MACHINE-003",
            "sensor_data": {"temperature": 88},
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["risk_level"] == "high"
    assert body["confirmation_required"] is True
    assert body["ticket"] is None
    assert "require_confirmation_node" in body["tools_used"]
    assert "create_ticket_node" not in body["tools_used"]
    assert "create_ticket_mock" not in body["tools_used"]


def test_agent_invoke_confirmation_creates_mock_ticket(
    client,
    monkeypatch,
    register_user,
    auth_headers,
):
    register_user("agent-ticket@example.com")
    monkeypatch.setattr(
        "app.agents.maintenance_agent.tools.check_machine_health",
        lambda **kwargs: _mock_health_result("high", 0.92),
    )

    response = client.post(
        "/agent/invoke",
        headers=auth_headers("agent-ticket@example.com"),
        json={
            "user_input": "确认创建工单，设备振动异常",
            "machine_id": "MACHINE-004",
            "sensor_data": {"vibration": 0.95},
            "confirm_create_ticket": True,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["risk_level"] == "high"
    assert body["confirmation_required"] is False
    assert body["ticket"]["status"] == "mock_created"
    assert body["ticket"]["external_call"] is False
    assert "create_ticket_node" in body["tools_used"]
    assert "create_ticket_mock" in body["tools_used"]
