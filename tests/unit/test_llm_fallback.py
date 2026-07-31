"""Unit tests for :class:`FallbackLLMProvider`.

Verifies the fallback provider is only invoked when the primary fails —
never on a successful primary call — matching the "use only when
necessary" design goal.
"""

from __future__ import annotations

import pytest

from jarvis.core.types import ChatMessage
from jarvis.infrastructure.llm.fallback_provider import FallbackLLMProvider
from tests.fakes.fake_llm import FakeLLM

_MSGS = [ChatMessage(role="user", content="hello")]


@pytest.mark.asyncio
async def test_fallback_not_used_when_primary_succeeds() -> None:
    primary = FakeLLM("primary reply", name="primary")
    fallback = FakeLLM("fallback reply", name="fallback")
    provider = FallbackLLMProvider(primary, fallback)

    result = await provider.complete(_MSGS)

    assert result == "primary reply"
    assert len(primary.calls) == 1
    assert len(fallback.calls) == 0


@pytest.mark.asyncio
async def test_fallback_used_when_primary_fails() -> None:
    primary = FakeLLM(name="primary", fail=True)
    fallback = FakeLLM("fallback reply", name="fallback")
    provider = FallbackLLMProvider(primary, fallback)

    result = await provider.complete(_MSGS)

    assert result == "fallback reply"
    assert len(primary.calls) == 1
    assert len(fallback.calls) == 1


@pytest.mark.asyncio
async def test_fallback_stream_switches_on_failure() -> None:
    primary = FakeLLM(name="primary", fail=True)
    fallback = FakeLLM("fallback reply", name="fallback")
    provider = FallbackLLMProvider(primary, fallback)

    tokens = [t async for t in provider.stream(_MSGS)]

    assert "".join(tokens).strip() == "fallback reply"


@pytest.mark.asyncio
async def test_fallback_stream_uses_only_primary_when_healthy() -> None:
    primary = FakeLLM("primary reply", name="primary")
    fallback = FakeLLM("fallback reply", name="fallback")
    provider = FallbackLLMProvider(primary, fallback)

    tokens = [t async for t in provider.stream(_MSGS)]

    assert "".join(tokens).strip() == "primary reply"
    assert len(fallback.calls) == 0


@pytest.mark.asyncio
async def test_fallback_embed_switches_on_failure() -> None:
    primary = FakeLLM(name="primary", fail=True)
    fallback = FakeLLM(name="fallback")
    provider = FallbackLLMProvider(primary, fallback)

    result = await provider.embed(["hello"])

    assert result == [[0.0] * 4]


@pytest.mark.asyncio
async def test_fallback_health_reports_primary_only() -> None:
    primary = FakeLLM(name="primary")
    fallback = FakeLLM(name="fallback", fail=True)
    provider = FallbackLLMProvider(primary, fallback)

    status = await provider.health()

    assert status.name == "primary"
    assert status.healthy is True


@pytest.mark.asyncio
async def test_fallback_provider_name_matches_primary() -> None:
    primary = FakeLLM(name="ollama")
    fallback = FakeLLM(name="gemini")
    provider = FallbackLLMProvider(primary, fallback)

    assert provider.name == "ollama"
