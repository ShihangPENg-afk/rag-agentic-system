from app.services.agent_service import invoke_maintenance_agent


def test_maintenance_agent_service_runs_with_mock_health():
    result = invoke_maintenance_agent(
        user_input="设备温度偏高，请给出维护建议",
        machine_id="MACHINE-001",
        sensor_data={"temperature": 82, "vibration": 0.3},
    )

    assert result["risk_level"] == "high"
    assert "check_machine_health" in result["tools_used"]
    assert "generate_maintenance_plan" in result["tools_used"]
    assert "create_ticket_mock" in result["tools_used"]
    assert result["sources"] == []
    assert result["final_answer"]


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
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["final_answer"]
    assert body["risk_level"] == "high"
    assert body["session_id"]
    assert body["sources"] == []
    assert "list_history" in body["tools_used"]
    assert "check_machine_health" in body["tools_used"]
    assert "create_ticket_mock" in body["tools_used"]
