"""Unit tests for :class:`GeminiLLMProvider`.

These stay network-free: they exercise the pure translation helpers
(message → Gemini payload, SSE chunk → token, error-body extraction) and
the "missing API key" guard, rather than hitting the real API.
"""

from __future__ import annotations

import pytest

from jarvis.core.config.settings import GeminiSettings
from jarvis.core.exceptions import LLMProviderError
from jarvis.core.types import ChatMessage
from jarvis.infrastructure.llm.gemini_provider import (
    GeminiLLMProvider,
    _to_gemini_payload,
)


def test_to_gemini_payload_maps_roles_and_splits_system() -> None:
    messages = [
        ChatMessage(role="system", content="Be concise."),
        ChatMessage(role="user", content="Hi"),
        ChatMessage(role="assistant", content="Hello!"),
        ChatMessage(role="user", content="How are you?"),
    ]

    system, contents = _to_gemini_payload(messages)

    assert system == {"parts": [{"text": "Be concise."}]}
    assert contents == [
        {"role": "user", "parts": [{"text": "Hi"}]},
        {"role": "model", "parts": [{"text": "Hello!"}]},
        {"role": "user", "parts": [{"text": "How are you?"}]},
    ]


def test_to_gemini_payload_concatenates_multiple_system_messages() -> None:
    messages = [
        ChatMessage(role="system", content="First rule."),
        ChatMessage(role="system", content="Second rule."),
        ChatMessage(role="user", content="Hi"),
    ]

    system, contents = _to_gemini_payload(messages)

    assert system is not None
    assert "First rule." in system["parts"][0]["text"]
    assert "Second rule." in system["parts"][0]["text"]
    assert len(contents) == 1


def test_to_gemini_payload_with_no_system_message() -> None:
    messages = [ChatMessage(role="user", content="Hi")]

    system, contents = _to_gemini_payload(messages)

    assert system is None
    assert contents == [{"role": "user", "parts": [{"text": "Hi"}]}]


def test_extract_token_reads_candidate_text() -> None:
    line = '{"candidates": [{"content": {"parts": [{"text": "Hello"}]}}]}'

    assert GeminiLLMProvider._extract_token(line) == "Hello"


def test_extract_token_joins_multiple_parts() -> None:
    line = '{"candidates": [{"content": {"parts": ' '[{"text": "Hello, "}, {"text": "world!"}]}}]}'

    assert GeminiLLMProvider._extract_token(line) == "Hello, world!"


def test_extract_token_returns_empty_on_malformed_json() -> None:
    assert GeminiLLMProvider._extract_token("not json") == ""


def test_extract_token_returns_empty_when_no_candidates() -> None:
    assert GeminiLLMProvider._extract_token('{"candidates": []}') == ""


def test_extract_error_bytes_reads_error_message() -> None:
    body = b'{"error": {"message": "API key not valid", "code": 400}}'

    assert "API key not valid" in GeminiLLMProvider._extract_error_bytes(body)


def test_extract_error_bytes_handles_list_wrapped_errors() -> None:
    body = b'[{"error": {"message": "quota exceeded"}}]'

    assert "quota exceeded" in GeminiLLMProvider._extract_error_bytes(body)


def test_extract_error_bytes_falls_back_to_raw_text_on_bad_json() -> None:
    body = b"not json at all"

    assert GeminiLLMProvider._extract_error_bytes(body) == "not json at all"


@pytest.mark.asyncio
async def test_stream_raises_when_api_key_missing() -> None:
    settings = GeminiSettings(enabled=True, api_key="")
    provider = GeminiLLMProvider(settings)

    with pytest.raises(LLMProviderError, match="API_KEY is empty"):
        async for _ in provider.stream([ChatMessage(role="user", content="hi")]):
            pass


@pytest.mark.asyncio
async def test_health_reports_disabled_when_not_enabled() -> None:
    settings = GeminiSettings(enabled=False)
    provider = GeminiLLMProvider(settings)

    status = await provider.health()

    assert status.enabled is False
    assert status.healthy is False


@pytest.mark.asyncio
async def test_health_reports_unhealthy_when_key_missing() -> None:
    settings = GeminiSettings(enabled=True, api_key="")
    provider = GeminiLLMProvider(settings)

    status = await provider.health()

    assert status.enabled is True
    assert status.healthy is False
    assert "API_KEY is empty" in status.detail
