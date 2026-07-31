"""Milestone 6, Phase 5 — vision agent tool + registry + orchestrator wiring.

Uses a tiny duck-typed fake ``VisionService`` (not the real one, which
needs real providers), matching the established fake-service idiom in
``tests/unit/test_agent_tools_registry.py``. Only verifies provider
availability reporting through the agent tool surface -- no capture,
OCR, image analysis, or processing exists yet.
"""

from __future__ import annotations

import pytest

pytest.importorskip("langchain_core")

from jarvis.agents.orchestrator import AgentOrchestrator
from jarvis.agents.tools.registry import build_tool_registry
from jarvis.agents.tools.vision_tools import build_vision_tools
from jarvis.core.config.settings import AgentSettings, Settings
from jarvis.core.di.container import Container
from tests.fakes.fake_scripted_llm import ScriptedFakeLLM


class _FakeVisionService:
    def __init__(self) -> None:
        self.status_called = False

    async def status(self) -> dict:
        self.status_called = True
        return {
            "vision": {"provider": "mock", "enabled": False, "healthy": False, "detail": "fake"},
            "ocr": {"provider": "mock", "enabled": False, "healthy": False, "detail": "fake"},
        }


class _FakeMemoryService:
    async def remember(self, content: str, *, memory_type: str = "long_term") -> str:
        return "mem-1"

    async def recall(self, query: str, *, top_k: int = 5):
        return []


def _agent_settings(tmp_path) -> Settings:
    return Settings(data_dir=tmp_path, agent=AgentSettings(checkpoint_enabled=False))


# ---------------------------------------------------------------------------
# Vision tool
# ---------------------------------------------------------------------------
def test_build_vision_tools_returns_exactly_one_tool() -> None:
    tools = build_vision_tools(_FakeVisionService())

    assert len(tools) == 1


def test_vision_status_tool_name() -> None:
    (vision_status,) = build_vision_tools(_FakeVisionService())

    assert vision_status.name == "vision_status"


@pytest.mark.asyncio
async def test_vision_status_tool_calls_vision_service_status() -> None:
    service = _FakeVisionService()
    (vision_status,) = build_vision_tools(service)

    await vision_status.ainvoke({})

    assert service.status_called is True


@pytest.mark.asyncio
async def test_vision_status_tool_returns_service_response_unchanged() -> None:
    service = _FakeVisionService()
    (vision_status,) = build_vision_tools(service)
    expected = await service.status()
    service.status_called = False  # reset; the tool call below re-invokes status()

    result = await vision_status.ainvoke({})

    assert result == str(expected)


# ---------------------------------------------------------------------------
# Registry composition
# ---------------------------------------------------------------------------
def test_registry_includes_vision_tool_when_vision_service_injected() -> None:
    tools = build_tool_registry(vision=_FakeVisionService())
    names = {t.name for t in tools}

    assert "vision_status" in names


def test_registry_excludes_vision_tool_when_vision_is_none() -> None:
    tools = build_tool_registry(vision=None)

    assert tools == []


def test_registry_is_still_empty_with_no_services() -> None:
    """Regression guard: the pre-existing no-args behavior is unchanged."""
    assert build_tool_registry() == []


def test_registry_still_excludes_vision_when_only_other_services_injected() -> None:
    """Regression guard: adding the optional vision kwarg must not make it
    appear unless explicitly injected."""
    tools = build_tool_registry(memory=_FakeMemoryService())
    names = {t.name for t in tools}

    assert "vision_status" not in names
    assert names == {"remember", "recall_memory"}


# ---------------------------------------------------------------------------
# AgentOrchestrator wiring
# ---------------------------------------------------------------------------
def test_agent_orchestrator_accepts_optional_vision_service(tmp_path) -> None:
    orchestrator = AgentOrchestrator(
        _agent_settings(tmp_path),
        llm=None,  # type: ignore[arg-type]
        memory=None,  # type: ignore[arg-type]
        automation=None,  # type: ignore[arg-type]
        browser=None,  # type: ignore[arg-type]
        vision=_FakeVisionService(),
    )

    assert orchestrator is not None


@pytest.mark.asyncio
async def test_agent_orchestrator_start_registers_vision_tool_when_injected(tmp_path) -> None:
    orchestrator = AgentOrchestrator(
        _agent_settings(tmp_path),
        llm=ScriptedFakeLLM({}),
        memory=None,  # type: ignore[arg-type]
        automation=None,  # type: ignore[arg-type]
        browser=None,  # type: ignore[arg-type]
        vision=_FakeVisionService(),
    )

    await orchestrator.start()

    tool_names = {t.name for t in orchestrator._tools}
    assert "vision_status" in tool_names

    await orchestrator.stop()


@pytest.mark.asyncio
async def test_agent_orchestrator_start_omits_vision_tool_when_not_injected(tmp_path) -> None:
    """Backward-compatibility guard: vision defaults to None, so an
    orchestrator built exactly like before Phase 5 behaves identically."""
    orchestrator = AgentOrchestrator(
        _agent_settings(tmp_path),
        llm=ScriptedFakeLLM({}),
        memory=None,  # type: ignore[arg-type]
        automation=None,  # type: ignore[arg-type]
        browser=None,  # type: ignore[arg-type]
    )

    await orchestrator.start()

    tool_names = {t.name for t in orchestrator._tools}
    assert "vision_status" not in tool_names
    assert tool_names == set()

    await orchestrator.stop()


# ---------------------------------------------------------------------------
# DI container
# ---------------------------------------------------------------------------
def test_di_container_agent_orchestrator_accepts_vision_service_wiring() -> None:
    """Confirms the container's agent_orchestrator Singleton resolves with
    vision=vision_service threaded in, without raising."""
    container = Container()
    container.settings.override(Settings())

    orchestrator = container.agent_orchestrator()

    assert orchestrator is not None


def test_di_container_still_declares_pre_existing_providers() -> None:
    """Regression guard: adding vision wiring must not disturb any
    existing provider registration."""
    for name in (
        "settings",
        "event_bus",
        "llm_provider",
        "memory_service",
        "automation_service",
        "browser_service",
        "chat_service",
        "voice_service",
        "system_service",
        "vision_service",
        "agent_orchestrator",
        "shutdown_manager",
    ):
        assert hasattr(Container, name), f"DI container missing pre-existing provider: {name}"
