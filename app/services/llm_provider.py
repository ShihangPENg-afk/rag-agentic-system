from __future__ import annotations

import os
from typing import Any, Protocol

import requests
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.core.config import (
    API_KEY,
    DASHSCOPE_BASE_URL,
    LLM_PROVIDER,
    LOCAL_LLM_API_KEY,
    LOCAL_LLM_BASE_URL,
    LOCAL_LLM_MOCK,
    LOCAL_LLM_MODEL,
    MODEL_NAME,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
)

OLLAMA_TIMEOUT = 20


class LLMProviderError(RuntimeError):
    """Raised when a configured LLM provider cannot be used."""


class LLMProvider(Protocol):
    name: str

    def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float = 0.0,
    ) -> str:
        """Generate text from a prompt using the configured provider."""

    def create_chat_model(self, *, temperature: float = 0.0) -> Any:
        """Return a chat model object for Agent tool-calling paths."""


class DashScopeLLMProvider:
    name = "dashscope"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model_name: str,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.model_name = model_name

    def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float = 0.0,
    ) -> str:
        model = self.create_chat_model(temperature=temperature)
        messages: list[BaseMessage] = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))
        response = model.invoke(messages)
        return _message_content_to_text(response.content)

    def create_chat_model(self, *, temperature: float = 0.0) -> ChatOpenAI:
        if not self.api_key:
            raise LLMProviderError("DASHSCOPE_API_KEY is required for dashscope provider.")
        return ChatOpenAI(
            model=self.model_name,
            api_key=self.api_key,
            base_url=self.base_url,
            temperature=temperature,
        )


class LocalLLMProvider:
    name = "local"

    def __init__(
        self,
        *,
        base_url: str,
        model_name: str,
        api_key: str,
        ollama_base_url: str,
        ollama_model: str,
        mock_enabled: bool = False,
    ) -> None:
        self.base_url = base_url
        self.model_name = model_name
        self.api_key = api_key
        self.ollama_base_url = ollama_base_url
        self.ollama_model = ollama_model
        self.mock_enabled = mock_enabled

    def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float = 0.0,
    ) -> str:
        if self._has_real_model_config():
            model = self.create_chat_model(temperature=temperature)
            messages: list[BaseMessage] = []
            if system_prompt:
                messages.append(SystemMessage(content=system_prompt))
            messages.append(HumanMessage(content=prompt))
            response = model.invoke(messages)
            return _message_content_to_text(response.content)

        if self._has_ollama_config():
            return self._generate_with_ollama(
                prompt,
                system_prompt=system_prompt,
                temperature=temperature,
            )

        if self.mock_enabled:
            return (
                "[local-provider mock] 本地 LLM 尚未配置真实模型服务；"
                "这是用于离线流程验证的占位回复。"
            )
        return (
            "❌ local LLM provider 未配置真实模型服务。请设置 "
            "LOCAL_LLM_BASE_URL 和 LOCAL_LLM_MODEL，或设置 OLLAMA_BASE_URL 和 "
            "OLLAMA_MODEL 调用 Ollama；也可以设置 LOCAL_LLM_MOCK=true 启用占位回复。"
        )

    def create_chat_model(self, *, temperature: float = 0.0) -> Any:
        if self._has_real_model_config():
            return ChatOpenAI(
                model=self.model_name,
                api_key=self.api_key or "not-needed",
                base_url=self.base_url,
                temperature=temperature,
            )
        if self._has_ollama_config():
            return _OllamaPlaceholderChatModel(
                provider=self,
                temperature=temperature,
            )
        return _LocalPlaceholderChatModel(mock_enabled=self.mock_enabled)

    def _has_real_model_config(self) -> bool:
        return bool(self.base_url and self.model_name)

    def _has_ollama_config(self) -> bool:
        return bool(self.ollama_base_url and self.ollama_model)

    def _generate_with_ollama(
        self,
        prompt: str,
        *,
        system_prompt: str | None,
        temperature: float,
    ) -> str:
        url = f"{self.ollama_base_url.rstrip('/')}/api/generate"
        payload: dict[str, Any] = {
            "model": self.ollama_model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if system_prompt:
            payload["system"] = system_prompt

        try:
            response = requests.post(url, json=payload, timeout=OLLAMA_TIMEOUT)
            response.raise_for_status()
            data = response.json()
        except requests.ConnectionError:
            return (
                f"❌ Ollama 服务不可用：无法连接 {self.ollama_base_url}。"
                "请确认 Ollama 已启动，并且 OLLAMA_BASE_URL 配置正确。"
            )
        except requests.Timeout:
            return (
                f"❌ Ollama 服务请求超时：{url}。"
                "请确认本地模型已加载，或调小请求规模后重试。"
            )
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            detail = exc.response.text if exc.response is not None else str(exc)
            return f"❌ Ollama 调用失败（HTTP {status}）：{detail}"
        except ValueError:
            return "❌ Ollama 返回了非 JSON 响应，无法解析生成结果。"
        except requests.RequestException as exc:
            return f"❌ Ollama 调用失败：{exc}"

        if not isinstance(data, dict):
            return "❌ Ollama 返回格式异常：响应不是 JSON object。"
        if data.get("error"):
            return f"❌ Ollama 返回错误：{data['error']}"

        text = data.get("response")
        if isinstance(text, str):
            return text
        return "❌ Ollama 返回格式异常：缺少 response 字段。"


class _LocalPlaceholderChatModel:
    def __init__(self, *, mock_enabled: bool) -> None:
        self.mock_enabled = mock_enabled

    def bind_tools(self, tools: list[Any]) -> "_LocalPlaceholderChatModel":
        return self

    def invoke(self, messages: list[BaseMessage], *args: Any, **kwargs: Any) -> AIMessage:
        if self.mock_enabled:
            content = (
                "[local-provider mock] 本地 LLM 尚未配置真实模型服务；"
                "当前返回占位回复，未执行真实模型推理。"
            )
        else:
            content = (
                "❌ local LLM provider 未配置真实模型服务。请设置 "
                "LOCAL_LLM_BASE_URL 和 LOCAL_LLM_MODEL，或设置 LOCAL_LLM_MOCK=true "
                "启用占位回复。"
            )
        return AIMessage(content=content)


class _OllamaPlaceholderChatModel:
    def __init__(self, *, provider: LocalLLMProvider, temperature: float) -> None:
        self.provider = provider
        self.temperature = temperature

    def bind_tools(self, tools: list[Any]) -> "_OllamaPlaceholderChatModel":
        return self

    def invoke(self, messages: list[BaseMessage], *args: Any, **kwargs: Any) -> AIMessage:
        prompt = _messages_to_prompt(messages)
        content = self.provider.generate(prompt, temperature=self.temperature)
        return AIMessage(content=content)


def get_llm_provider() -> LLMProvider:
    provider = os.getenv("LLM_PROVIDER", LLM_PROVIDER).strip().lower()
    if provider == "dashscope":
        return DashScopeLLMProvider(
            api_key=os.getenv("DASHSCOPE_API_KEY", API_KEY).strip(),
            base_url=os.getenv("DASHSCOPE_BASE_URL", DASHSCOPE_BASE_URL).strip(),
            model_name=os.getenv("MODEL_NAME", MODEL_NAME).strip(),
        )
    if provider == "local":
        return LocalLLMProvider(
            base_url=os.getenv("LOCAL_LLM_BASE_URL", LOCAL_LLM_BASE_URL).strip(),
            model_name=os.getenv("LOCAL_LLM_MODEL", LOCAL_LLM_MODEL).strip(),
            api_key=os.getenv("LOCAL_LLM_API_KEY", LOCAL_LLM_API_KEY).strip(),
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", OLLAMA_BASE_URL).strip(),
            ollama_model=os.getenv("OLLAMA_MODEL", OLLAMA_MODEL).strip(),
            mock_enabled=_env_bool(os.getenv("LOCAL_LLM_MOCK", LOCAL_LLM_MOCK)),
        )
    raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")


def generate(
    prompt: str,
    *,
    system_prompt: str | None = None,
    temperature: float = 0.0,
) -> str:
    return get_llm_provider().generate(
        prompt,
        system_prompt=system_prompt,
        temperature=temperature,
    )


def create_chat_model(*, temperature: float = 0.0) -> Any:
    return get_llm_provider().create_chat_model(temperature=temperature)


def _env_bool(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _message_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content)


def _messages_to_prompt(messages: list[BaseMessage]) -> str:
    lines: list[str] = []
    for message in messages:
        role = message.type
        content = _message_content_to_text(message.content)
        lines.append(f"{role}: {content}")
    return "\n".join(lines)
