"""Tests for `ConversationController`'s conversation routing (Milestone
10, Conversational Orchestration Routing -- see
`docs/ORCHESTRATION_ROUTING_LOGIC_CONTRACT.md`).

Chat (`_chat_page.prompt.submitted`) and Voice
(`_voice_controller.transcribed`) both wire to the exact same
`ConversationController.send()` slot (confirmed in `ui/main_window.py`
by the Phase 0 audit) -- so exercising `send()` here covers both real
entry points at once; there is no behavioral difference between them
at this layer. `ChatService`/`AgentOrchestrator` are faked (the LLM
boundary this test is not exercising); `ConversationService` is real,
backed by real temp-file SQLite, matching this project's own
persistence-test convention -- no mocked repository.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from jarvis.core.interfaces.agent import AgentRequest, AgentResponse

pytest.importorskip("PySide6")


def _settings(tmp_path: Path, monkeypatch, *, conversation_routing: str = "legacy"):
    from jarvis.core.config.settings import AgentSettings, Settings

    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JARVIS_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'jarvis.db'}")
    return Settings(
        data_dir=tmp_path, agent=AgentSettings(conversation_routing=conversation_routing)
    )


@pytest.fixture
async def conversation_service(tmp_path: Path, monkeypatch):
    from jarvis.core.config import settings as settings_mod

    settings_mod.load_settings.cache_clear()  # type: ignore[attr-defined]
    settings = _settings(tmp_path, monkeypatch)
    from jarvis.infrastructure.database.sqlite_client import SQLiteDatabase
    from jarvis.services.conversation_service import ConversationService

    db = SQLiteDatabase(settings.db)
    await db.initialize()
    try:
        yield ConversationService(database=db)
    finally:
        await db.dispose()


class _FakeChatService:
    """Records every call; streams one scripted token list per prompt."""

    def __init__(self, tokens: list[str] | None = None) -> None:
        self.tokens = tokens if tokens is not None else ["Hello", " there."]
        self.calls: list[tuple[str, str]] = []

    async def stream(self, conversation_id: str, prompt: str) -> AsyncIterator[str]:
        self.calls.append((conversation_id, prompt))
        for tok in self.tokens:
            yield tok


class _FakeOrchestrator:
    """Structurally satisfies `IAgentOrchestrator` -- records every
    `AgentRequest`, streams one scripted token list per request."""

    def __init__(self, tokens: list[str] | None = None) -> None:
        self.tokens = tokens if tokens is not None else ["Orchestrated", " reply."]
        self.requests: list[AgentRequest] = []

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def invoke(self, request: AgentRequest) -> AgentResponse:
        self.requests.append(request)
        text = "".join(self.tokens)
        return AgentResponse(text=text, thread_id=request.thread_id or "t", steps=0)

    async def stream(self, request: AgentRequest) -> AsyncIterator[str]:
        self.requests.append(request)
        for tok in self.tokens:
            yield tok


def _make_controller(chat, conversation_service, settings, orchestrator=None):
    from jarvis.features.conversation.controller import ConversationController

    return ConversationController(
        chat_service=chat,
        conversation_service=conversation_service,
        settings=settings,
        agent_orchestrator=orchestrator,
        parent=None,
    )


async def _send_and_wait(controller, prompt: str) -> None:
    """Drives the public `send()` slot (the real Chat/Voice entry
    point) to completion -- `send()` stores its own scheduled task on
    `self._task`, which is what this awaits, rather than reaching past
    `send()` into the private async helpers directly."""
    controller.send(prompt)
    assert controller._task is not None
    await controller._task


# --- chat path (legacy, default) -----------------------------------------------


@pytest.mark.asyncio
async def test_legacy_mode_routes_through_chat_service(qapp, tmp_path, monkeypatch) -> None:
    settings = _settings(tmp_path, monkeypatch, conversation_routing="legacy")
    from jarvis.infrastructure.database.sqlite_client import SQLiteDatabase
    from jarvis.services.conversation_service import ConversationService

    db = SQLiteDatabase(settings.db)
    await db.initialize()
    conv_service = ConversationService(database=db)

    chat = _FakeChatService(tokens=["Paris", " is", " the", " capital."])
    orchestrator = _FakeOrchestrator()
    controller = _make_controller(chat, conv_service, settings, orchestrator)

    received_tokens: list[str] = []
    controller.token.connect(received_tokens.append)

    await _send_and_wait(controller, "What is the capital of France?")

    assert chat.calls, "legacy mode must call ChatService"
    assert not orchestrator.requests, "legacy mode must never reach AgentOrchestrator"
    assert "".join(received_tokens) == "Paris is the capital."

    await db.dispose()


@pytest.mark.asyncio
async def test_legacy_mode_is_the_default(
    qapp, conversation_service, tmp_path, monkeypatch
) -> None:
    """Rollback flag: constructing with no explicit routing mode at all
    preserves pre-M10-routing behaviour byte-for-byte."""
    from jarvis.core.config.settings import Settings

    settings = Settings(data_dir=tmp_path)
    assert settings.agent.conversation_routing == "legacy"

    chat = _FakeChatService()
    controller = _make_controller(chat, conversation_service, settings, orchestrator=None)

    await _send_and_wait(controller, "hello")

    assert chat.calls


# --- orchestrator path -----------------------------------------------------------


@pytest.mark.asyncio
async def test_orchestrator_mode_routes_through_agent_orchestrator(
    qapp, conversation_service, tmp_path, monkeypatch
) -> None:
    settings = _settings(tmp_path, monkeypatch, conversation_routing="orchestrator")
    chat = _FakeChatService()
    orchestrator = _FakeOrchestrator(tokens=["Orchestrated", " answer."])
    controller = _make_controller(chat, conversation_service, settings, orchestrator)

    received_tokens: list[str] = []
    controller.token.connect(received_tokens.append)

    await _send_and_wait(controller, "what's the weather?")

    assert orchestrator.requests, "orchestrator mode must call AgentOrchestrator"
    assert not chat.calls, "orchestrator mode must never reach ChatService directly"
    assert "".join(received_tokens) == "Orchestrated answer."
    assert orchestrator.requests[0].prompt == "what's the weather?"


@pytest.mark.asyncio
async def test_orchestrator_mode_persists_messages_like_the_legacy_path(
    qapp, conversation_service, tmp_path, monkeypatch
) -> None:
    """Acceptance criterion 4: the orchestrator path's persisted shape
    must match ChatService's own -- one user row, one assistant row,
    same conversation."""
    settings = _settings(tmp_path, monkeypatch, conversation_routing="orchestrator")
    chat = _FakeChatService()
    orchestrator = _FakeOrchestrator(tokens=["42"])
    controller = _make_controller(chat, conversation_service, settings, orchestrator)

    await _send_and_wait(controller, "what is 6*7?")

    conv_id = controller._active_id
    assert conv_id is not None
    history = await conversation_service.history(conv_id)
    assert [m.role for m in history] == ["user", "assistant"]
    assert history[0].content == "what is 6*7?"
    assert history[1].content == "42"


@pytest.mark.asyncio
async def test_orchestrator_mode_reuses_conversation_id_as_thread_id(
    qapp, conversation_service, tmp_path, monkeypatch
) -> None:
    """The bridge between ConversationService's own id and
    AgentOrchestrator's `thread_id`, per the Logic Contract's
    SessionManager-mirroring design."""
    settings = _settings(tmp_path, monkeypatch, conversation_routing="orchestrator")
    chat = _FakeChatService()
    orchestrator = _FakeOrchestrator()
    controller = _make_controller(chat, conversation_service, settings, orchestrator)

    await _send_and_wait(controller, "hi")

    conv_id = controller._active_id
    assert orchestrator.requests[0].thread_id == conv_id


# --- hybrid mode -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hybrid_mode_defaults_to_chat_service(
    qapp, conversation_service, tmp_path, monkeypatch
) -> None:
    """Hybrid makes both paths *reachable* through this controller
    without making an ordinary send() non-deterministic -- its default
    is the same as legacy's."""
    settings = _settings(tmp_path, monkeypatch, conversation_routing="hybrid")
    chat = _FakeChatService()
    orchestrator = _FakeOrchestrator()
    controller = _make_controller(chat, conversation_service, settings, orchestrator)

    await _send_and_wait(controller, "hello")

    assert chat.calls
    assert not orchestrator.requests


@pytest.mark.asyncio
async def test_hybrid_mode_can_reach_the_orchestrator_explicitly(
    qapp, conversation_service, tmp_path, monkeypatch
) -> None:
    settings = _settings(tmp_path, monkeypatch, conversation_routing="hybrid")
    chat = _FakeChatService()
    orchestrator = _FakeOrchestrator(tokens=["via orchestrator"])
    controller = _make_controller(chat, conversation_service, settings, orchestrator)

    await controller._stream_via_orchestrator("hello")

    assert orchestrator.requests
    assert not chat.calls


# --- the flag itself -----------------------------------------------------------------


def test_orchestrator_mode_without_an_orchestrator_fails_at_construction(
    qapp, conversation_service, tmp_path, monkeypatch
) -> None:
    """Fail loudly at construction, naming the problem -- not the first
    time a user sends a message."""
    settings = _settings(tmp_path, monkeypatch, conversation_routing="orchestrator")
    chat = _FakeChatService()

    with pytest.raises(ValueError, match="conversation_routing"):
        _make_controller(chat, conversation_service, settings, orchestrator=None)


def test_legacy_mode_never_requires_an_orchestrator(
    qapp, conversation_service, tmp_path, monkeypatch
) -> None:
    settings = _settings(tmp_path, monkeypatch, conversation_routing="legacy")
    chat = _FakeChatService()

    controller = _make_controller(chat, conversation_service, settings, orchestrator=None)

    assert controller is not None


# --- regression: existing signals/behaviour unaffected by routing --------------------


@pytest.mark.asyncio
async def test_error_signal_fires_on_orchestrator_failure_without_falling_back(
    qapp, conversation_service, tmp_path, monkeypatch
) -> None:
    """No silent fallback to ChatService mid-request -- a failure in
    orchestrator mode must surface as `error`, never quietly retried
    through the other backend."""
    settings = _settings(tmp_path, monkeypatch, conversation_routing="orchestrator")
    chat = _FakeChatService()

    class _FailingOrchestrator(_FakeOrchestrator):
        async def stream(self, request: AgentRequest) -> AsyncIterator[str]:
            self.requests.append(request)
            raise RuntimeError("simulated orchestrator failure")
            yield  # pragma: no cover -- makes this a generator function

    orchestrator = _FailingOrchestrator()
    controller = _make_controller(chat, conversation_service, settings, orchestrator)

    errors: list[str] = []
    controller.error.connect(errors.append)

    await _send_and_wait(controller, "hello")

    assert errors
    assert not chat.calls, "a failed orchestrator call must not silently fall back to ChatService"
