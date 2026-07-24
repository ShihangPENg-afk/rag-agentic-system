from __future__ import annotations

import pytest
import requests
from langchain_core.messages import AIMessage

from app.services import chat_service
from app.services.llm_provider import (
    DashScopeLLMProvider,
    LocalLLMProvider,
    get_llm_provider,
)


def test_get_llm_provider_selects_dashscope_without_hardcoded_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "dashscope")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-dashscope-key")
    monkeypatch.setenv("DASHSCOPE_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("MODEL_NAME", "qwen-test")

    provider = get_llm_provider()

    assert isinstance(provider, DashScopeLLMProvider)
    assert provider.api_key == "test-dashscope-key"
    assert provider.base_url == "https://example.test/v1"
    assert provider.model_name == "qwen-test"


def test_local_provider_without_model_returns_clear_error(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.delenv("LOCAL_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LOCAL_LLM_MODEL", raising=False)
    monkeypatch.setenv("LOCAL_LLM_MOCK", "false")

    provider = get_llm_provider()
    answer = provider.generate("hello")
    chat_model = provider.create_chat_model()
    response = chat_model.invoke([])

    assert isinstance(provider, LocalLLMProvider)
    assert "local LLM provider 未配置真实模型服务" in answer
    assert isinstance(response, AIMessage)
    assert "local LLM provider 未配置真实模型服务" in response.content


def test_local_provider_mock_response(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.delenv("LOCAL_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LOCAL_LLM_MODEL", raising=False)
    monkeypatch.setenv("LOCAL_LLM_MOCK", "true")

    provider = get_llm_provider()
    answer = provider.generate("hello")
    chat_model = provider.create_chat_model().bind_tools([])
    response = chat_model.invoke([])

    assert "[local-provider mock]" in answer
    assert isinstance(response, AIMessage)
    assert "[local-provider mock]" in response.content


def test_local_provider_calls_ollama_when_configured(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.delenv("LOCAL_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LOCAL_LLM_MODEL", raising=False)
    monkeypatch.setenv("LOCAL_LLM_MOCK", "false")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.test:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:7b")
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"response": "ollama generated answer"}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("app.services.llm_provider.requests.post", fake_post)

    provider = get_llm_provider()
    answer = provider.generate("hello", temperature=0.2)
    response = provider.create_chat_model().invoke([])

    assert captured["url"] == "http://ollama.test:11434/api/generate"
    assert captured["json"]["model"] == "qwen2.5:7b"
    assert captured["json"]["stream"] is False
    assert captured["json"]["options"]["temperature"] == 0
    assert captured["timeout"] == 20
    assert answer == "ollama generated answer"
    assert isinstance(response, AIMessage)
    assert response.content == "ollama generated answer"


def test_local_provider_returns_clear_error_when_ollama_unavailable(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.delenv("LOCAL_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LOCAL_LLM_MODEL", raising=False)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.test:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:7b")

    def fake_post(*args, **kwargs):
        raise requests.ConnectionError("connection refused")

    monkeypatch.setattr("app.services.llm_provider.requests.post", fake_post)

    provider = get_llm_provider()
    answer = provider.generate("hello")

    assert "Ollama 服务不可用" in answer
    assert "http://ollama.test:11434" in answer


def test_unsupported_llm_provider_raises_clear_error(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "unknown")

    with pytest.raises(ValueError, match="Unsupported LLM_PROVIDER"):
        get_llm_provider()


def test_generate_answer_uses_llm_provider_generate(monkeypatch):
    monkeypatch.setattr(
        chat_service,
        "generate_text",
        lambda prompt, **kwargs: "provider generated answer",
    )

    answer, history = chat_service.generate_answer(
        user_query="如何检查设备？",
        relevant_texts=["检查润滑和冷却状态。"],
        valid_turns=[],
    )

    assert answer == "provider generated answer"
    assert history[-1] == ("如何检查设备？", "provider generated answer")
