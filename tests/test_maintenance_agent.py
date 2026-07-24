import logging

import pytest
import requests

from app.agents.maintenance_agent import tools as maintenance_tools
from app.services.agent_service import (
    confirm_maintenance_agent_action,
    invoke_maintenance_agent,
)


@pytest.fixture(autouse=True)
def default_mock_health_provider(monkeypatch):
    monkeypatch.setenv("MAINTENANCE_HEALTH_PROVIDER", "mock")


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


def test_check_machine_health_prefers_predictive_http(monkeypatch):
    monkeypatch.delenv("MAINTENANCE_HEALTH_PROVIDER", raising=False)
    monkeypatch.setattr(
        maintenance_tools,
        "HEALTH_API_URL",
        "http://predictive-maintenance-mini:8010",
    )
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "prediction": "defect",
                "risk_level": "high",
                "risk_score": 0.82,
                "trigger_reasons": ["vibration is elevated"],
                "recommended_actions": ["Inspect the machine."],
                "recommendation": "Immediate inspection recommended.",
                "probabilities": {"defect": 0.82, "normal": 0.18},
                "model_version": "RandomForestClassifier-baseline-rs42",
            }

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(maintenance_tools.requests, "post", fake_post)

    result = maintenance_tools.check_machine_health(
        machine_id="MACHINE-HTTP",
        sensor_data={
            "temperature": 73.5,
            "pressure": 5.2,
            "vibration": 2.1,
            "speed": 118.0,
            "humidity": 48.0,
        },
    )

    assert captured["url"] == "http://predictive-maintenance-mini:8010/predict"
    assert captured["json"]["features"]["temperature"] == 73.5
    assert captured["timeout"][0] <= 2.0
    assert captured["timeout"][1] <= 10.0
    assert result["provider"] == "predictive-maintenance-mini"
    assert result["prediction"] == "defect"
    assert result["risk_level"] == "high"
    assert result["trigger_reasons"] == ["vibration is elevated"]
    assert result["recommended_actions"] == ["Inspect the machine."]
    assert result["model_version"] == "RandomForestClassifier-baseline-rs42"


def test_check_machine_health_falls_back_when_predictive_service_unavailable(
    monkeypatch,
):
    monkeypatch.delenv("MAINTENANCE_HEALTH_PROVIDER", raising=False)

    def fake_post(*args, **kwargs):
        raise requests.Timeout("request timed out")

    monkeypatch.setattr(maintenance_tools.requests, "post", fake_post)

    result = maintenance_tools.check_machine_health(
        machine_id="MACHINE-FALLBACK",
        sensor_data={"temperature": 82, "vibration": 0.3},
    )

    assert result["provider"] == "mock-fallback"
    assert result["prediction"] == "abnormal"
    assert result["risk_level"] == "high"
    assert result["trigger_reasons"]
    assert result["recommended_actions"]
    assert "timed out" in result["fallback_reason"]


def test_check_machine_health_handles_invalid_sensor_payload_without_crashing(
    monkeypatch,
):
    monkeypatch.delenv("MAINTENANCE_HEALTH_PROVIDER", raising=False)

    result = maintenance_tools.check_machine_health(
        machine_id="MACHINE-BAD-PAYLOAD",
        sensor_data=["temperature", 82],  # type: ignore[arg-type]
    )

    assert result["provider"] == "mock-fallback"
    assert result["prediction"] == "unknown"
    assert result["risk_level"] == "unknown"
    assert result["trigger_reasons"]
    assert result["recommended_actions"]
    assert "sensor_data must be a dict" in result["fallback_reason"]


def test_maintenance_agent_service_runs_with_mock_health():
    result = invoke_maintenance_agent(
        user_input="设备温度偏高，请给出维护建议",
        machine_id="MACHINE-001",
        sensor_data={"temperature": 82, "vibration": 0.3},
    )

    assert result["risk_level"] == "high"
    assert result["trace_id"]
    assert result["confirmation_required"] is True
    assert result["decision"] == "pending"
    assert result["recommended_action"]
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
    assert result["trace_id"]
    assert result["confirmation_required"] is True
    assert result["ticket"] is None

    confirmed = confirm_maintenance_agent_action(
        trace_id=result["trace_id"],
        decision="confirmed",
    )

    assert confirmed["decision"] == "confirmed"
    assert confirmed["confirmation_required"] is False
    assert confirmed["ticket"]["status"] == "mock_created"
    assert "create_ticket_node" in confirmed["tools_used"]
    assert "create_ticket_mock" in confirmed["tools_used"]


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
    assert body["trace_id"]
    assert body["risk_level"] == "high"
    assert body["session_id"]
    assert body["confirmation_required"] is True
    assert body["decision"] == "pending"
    assert body["recommended_action"]
    assert body["ticket"] is None
    assert body["sources"] == []
    assert "list_history" in body["tools_used"]
    assert "check_machine_health" in body["tools_used"]
    assert "create_ticket_mock" not in body["tools_used"]


def test_agent_invoke_emits_trace_logs(
    client,
    caplog,
    monkeypatch,
    register_user,
    auth_headers,
    create_document,
):
    user = register_user("agent-trace@example.com")
    document = create_document(user["id"])

    monkeypatch.setattr(
        "app.agents.maintenance_agent.tools.retrieve_manual",
        lambda **kwargs: _mock_retrieve_manual_result(str(document.id)),
    )
    monkeypatch.setattr(
        "app.agents.maintenance_agent.tools.check_machine_health",
        lambda **kwargs: _mock_health_result("medium", 0.55),
    )

    caplog.set_level(logging.INFO, logger="agent_traces")

    response = client.post(
        "/agent/invoke",
        headers=auth_headers("agent-trace@example.com"),
        json={
            "user_input": "请查询维护手册并检查设备状态",
            "machine_id": "MACHINE-TRACE",
            "knowledge_base_id": str(document.id),
            "sensor_data": {"temperature": 70},
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    trace_id = body["trace_id"]
    trace_logs = [record.message for record in caplog.records if "agent_traces" in record.name]

    assert trace_id
    assert any(trace_id in message for message in trace_logs)
    assert any('"node_name": "classify_intent"' in message for message in trace_logs)
    assert any('"tool_name": "retrieve_manual"' in message for message in trace_logs)


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
    assert body["decision"] == "none"
    assert body["recommended_action"]
    assert body["sources"][0]["chunk_id"] == "chunk-manual-001"
    assert body["sources"][0]["source_metadata"]["document_filename"] == "maintenance_manual.pdf"
    assert "retrieve_manual_node" in body["tools_used"]
    assert "retrieve_manual" in body["tools_used"]
    assert "final_response_node" in body["tools_used"]
    assert body["trace_id"]


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
    assert body["trace_id"]
    assert body["recommended_action"]
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
    assert body["trace_id"]
    assert body["decision"] == "pending"
    assert body["recommended_action"]
    assert "require_confirmation_node" in body["tools_used"]
    assert "create_ticket_node" not in body["tools_used"]
    assert "create_ticket_mock" not in body["tools_used"]


def test_agent_confirm_endpoint_creates_mock_ticket(
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
    assert body["trace_id"]
    assert body["confirmation_required"] is True
    assert body["ticket"] is None

    confirm_response = client.post(
        "/agent/confirm",
        headers=auth_headers("agent-ticket@example.com"),
        json={"trace_id": body["trace_id"], "decision": "confirmed"},
    )

    assert confirm_response.status_code == 200, confirm_response.text
    confirmed = confirm_response.json()
    assert confirmed["decision"] == "confirmed"
    assert confirmed["confirmation_required"] is False
    assert confirmed["ticket"]["status"] == "mock_created"
    assert confirmed["ticket"]["external_call"] is False
    assert "create_ticket_node" in confirmed["tools_used"]
    assert "create_ticket_mock" in confirmed["tools_used"]


def test_agent_confirm_endpoint_records_declined_decision(
    client,
    monkeypatch,
    register_user,
    auth_headers,
):
    register_user("agent-decline@example.com")
    monkeypatch.setattr(
        "app.agents.maintenance_agent.tools.check_machine_health",
        lambda **kwargs: _mock_health_result("high", 0.91),
    )

    response = client.post(
        "/agent/invoke",
        headers=auth_headers("agent-decline@example.com"),
        json={
            "user_input": "设备温度异常，请判断风险",
            "machine_id": "MACHINE-DECLINE",
            "sensor_data": {"temperature": 90},
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["confirmation_required"] is True

    decline_response = client.post(
        "/agent/confirm",
        headers=auth_headers("agent-decline@example.com"),
        json={"trace_id": body["trace_id"], "decision": "declined"},
    )

    assert decline_response.status_code == 200, decline_response.text
    declined = decline_response.json()
    assert declined["decision"] == "declined"
    assert declined["confirmation_required"] is False
    assert declined["ticket"] is None
    assert "decision=declined" in declined["final_answer"]


def test_agent_stream_endpoint_returns_sse_events(
    client,
    monkeypatch,
    register_user,
    auth_headers,
    create_document,
):
    user = register_user("agent-stream@example.com")
    document = create_document(user["id"])

    monkeypatch.setattr(
        "app.agents.maintenance_agent.tools.retrieve_manual",
        lambda **kwargs: _mock_retrieve_manual_result(str(document.id)),
    )
    monkeypatch.setattr(
        "app.agents.maintenance_agent.tools.check_machine_health",
        lambda **kwargs: _mock_health_result("high", 0.93),
    )

    with client.stream(
        "POST",
        "/agent/stream",
        headers=auth_headers("agent-stream@example.com"),
        json={
            "user_input": "确认创建工单，请查询手册并检查设备风险",
            "machine_id": "MACHINE-005",
            "knowledge_base_id": str(document.id),
            "sensor_data": {"temperature": 91},
            "confirm_create_ticket": True,
        },
    ) as response:
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("text/event-stream")
        stream_text = "".join(response.iter_text())

    assert "event: intent_classified" in stream_text
    assert "event: tool_started" in stream_text
    assert "event: tool_finished" in stream_text
    assert "event: risk_checked" in stream_text
    assert "event: final_answer" in stream_text
    assert '"trace_id"' in stream_text
    assert '"confirmation_required": true' in stream_text
    assert '"recommended_action"' in stream_text
    assert "retrieve_manual_node" in stream_text
    assert "check_health_node" in stream_text
    assert "chunk-manual-001" in stream_text
    assert "mock_created" not in stream_text
