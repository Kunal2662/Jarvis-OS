"""Milestone 6, Phase 4 — ``VisionService`` + event + DI wiring tests.

Only verifies provider-availability reporting. No capture, OCR, image
handling, image storage, event publishing, tools, or UI exist yet —
those are later phases.
"""

from __future__ import annotations

import pytest

from jarvis.core.config.settings import OCRSettings, Settings, VisionSettings
from jarvis.core.di.container import Container
from jarvis.core.events.events import Event, VisionProviderStatusEvent
from jarvis.core.types import ProviderStatus
from jarvis.infrastructure.ocr.mock_provider import MockOCRProvider
from jarvis.infrastructure.vision.mock_provider import MockVisionProvider
from jarvis.services.vision_service import VisionService


class _FakeVisionProvider:
    """Duck-typed fake -- records that ``health()`` was called, matching
    this test suite's established fake-service idiom
    (see ``tests/unit/test_agent_tools_registry.py``)."""

    name = "fake-vision"

    def __init__(self) -> None:
        self.health_called = False

    async def health(self) -> ProviderStatus:
        self.health_called = True
        return ProviderStatus(name=self.name, enabled=False, healthy=False, detail="fake vision")


class _FakeOCRProvider:
    name = "fake-ocr"

    def __init__(self) -> None:
        self.health_called = False

    async def health(self) -> ProviderStatus:
        self.health_called = True
        return ProviderStatus(name=self.name, enabled=False, healthy=False, detail="fake ocr")


def test_vision_service_constructs_with_vision_ocr_and_settings() -> None:
    vision = MockVisionProvider(VisionSettings())
    ocr = MockOCRProvider(OCRSettings())
    settings = Settings()

    service = VisionService(vision, ocr, settings)

    assert service is not None


@pytest.mark.asyncio
async def test_status_returns_a_dict() -> None:
    vision = MockVisionProvider(VisionSettings())
    ocr = MockOCRProvider(OCRSettings())
    service = VisionService(vision, ocr, Settings())

    result = await service.status()

    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_status_queries_the_vision_provider() -> None:
    vision = _FakeVisionProvider()
    service = VisionService(vision, MockOCRProvider(OCRSettings()), Settings())

    await service.status()

    assert vision.health_called is True


@pytest.mark.asyncio
async def test_status_queries_the_ocr_provider() -> None:
    ocr = _FakeOCRProvider()
    service = VisionService(MockVisionProvider(VisionSettings()), ocr, Settings())

    await service.status()

    assert ocr.health_called is True


@pytest.mark.asyncio
async def test_status_reflects_the_fake_providers_returned_values() -> None:
    vision = _FakeVisionProvider()
    ocr = _FakeOCRProvider()
    service = VisionService(vision, ocr, Settings())

    result = await service.status()

    assert result["vision"] == {
        "provider": "fake-vision",
        "enabled": False,
        "healthy": False,
        "detail": "fake vision",
    }
    assert result["ocr"] == {
        "provider": "fake-ocr",
        "enabled": False,
        "healthy": False,
        "detail": "fake ocr",
    }


@pytest.mark.asyncio
async def test_status_honestly_reports_mock_providers_as_unavailable() -> None:
    vision = MockVisionProvider(VisionSettings())
    ocr = MockOCRProvider(OCRSettings())
    service = VisionService(vision, ocr, Settings())

    result = await service.status()

    assert result["vision"]["provider"] == "mock"
    assert result["vision"]["enabled"] is False
    assert result["vision"]["healthy"] is False
    assert "not yet configured" in result["vision"]["detail"]
    assert result["ocr"]["provider"] == "mock"
    assert result["ocr"]["enabled"] is False
    assert result["ocr"]["healthy"] is False
    assert "not yet configured" in result["ocr"]["detail"]


def test_vision_service_exposes_only_status() -> None:
    """Regression guard against scope creep -- Phase 4 authorizes exactly
    one public method."""
    public_methods = [
        name
        for name in dir(VisionService)
        if not name.startswith("_") and callable(getattr(VisionService, name))
    ]

    assert public_methods == ["status"]


def test_vision_provider_status_event_is_an_event_subclass() -> None:
    assert issubclass(VisionProviderStatusEvent, Event)


def test_vision_provider_status_event_default_fields() -> None:
    event = VisionProviderStatusEvent()

    assert event.provider == ""
    assert event.healthy is False
    assert event.detail == ""


def test_vision_provider_status_event_accepts_explicit_fields() -> None:
    event = VisionProviderStatusEvent(provider="mock", healthy=False, detail="unavailable")

    assert event.provider == "mock"
    assert event.healthy is False
    assert event.detail == "unavailable"


def test_vision_provider_status_event_is_frozen() -> None:
    event = VisionProviderStatusEvent()

    with pytest.raises(AttributeError):
        event.provider = "changed"  # type: ignore[misc]


def test_di_container_declares_vision_service() -> None:
    assert hasattr(Container, "vision_service")


def test_di_container_resolves_vision_service() -> None:
    container = Container()
    container.settings.override(Settings())

    service = container.vision_service()

    assert isinstance(service, VisionService)


@pytest.mark.asyncio
async def test_di_container_resolved_vision_service_status_works_end_to_end() -> None:
    container = Container()
    container.settings.override(Settings())

    service = container.vision_service()
    result = await service.status()

    assert result["vision"]["healthy"] is False
    assert result["ocr"]["healthy"] is False


def test_di_container_vision_service_is_a_singleton() -> None:
    container = Container()
    container.settings.override(Settings())

    first = container.vision_service()
    second = container.vision_service()

    assert first is second


def test_di_container_still_declares_pre_existing_providers() -> None:
    """Regression guard: adding vision_service must not disturb any
    existing provider registration, including Phase 3's vision_provider
    and ocr_provider."""
    for name in (
        "settings",
        "event_bus",
        "llm_provider",
        "stt_provider",
        "tts_provider",
        "vision_provider",
        "ocr_provider",
        "vector_store",
        "database",
        "browser",
        "os_automation",
        "chat_service",
        "voice_service",
        "memory_service",
        "system_service",
        "agent_orchestrator",
        "shutdown_manager",
    ):
        assert hasattr(Container, name), f"DI container missing pre-existing provider: {name}"
