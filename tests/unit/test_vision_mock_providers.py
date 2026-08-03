"""Milestone 6, Phase 3 — mock provider + DI wiring tests for Vision/OCR.

Only verifies the mock providers report an honest "unavailable" status
and that the DI container resolves them. No real capture, OCR, image
processing, VisionService, events, tools, or UI exist yet — those are
later phases.
"""

from __future__ import annotations

import pytest

from jarvis.core.config.settings import OCRSettings, Settings, VisionSettings
from jarvis.core.di.container import Container
from jarvis.core.interfaces.ocr_provider import IOCRProvider
from jarvis.core.interfaces.vision_provider import IVisionProvider
from jarvis.core.types import ProviderStatus
from jarvis.infrastructure.ocr.mock_provider import MockOCRProvider
from jarvis.infrastructure.ocr.provider_factory import build_ocr_provider
from jarvis.infrastructure.vision.mock_provider import MockVisionProvider
from jarvis.infrastructure.vision.provider_factory import build_vision_provider


def test_mock_vision_provider_implements_ivision_provider() -> None:
    provider = MockVisionProvider(VisionSettings())

    assert isinstance(provider, IVisionProvider)


def test_mock_ocr_provider_implements_iocr_provider() -> None:
    provider = MockOCRProvider(OCRSettings())

    assert isinstance(provider, IOCRProvider)


def test_mock_vision_provider_name_is_mock() -> None:
    provider = MockVisionProvider(VisionSettings())

    assert provider.name == "mock"


def test_mock_ocr_provider_name_is_mock() -> None:
    provider = MockOCRProvider(OCRSettings())

    assert provider.name == "mock"


@pytest.mark.asyncio
async def test_mock_vision_provider_health_reports_unavailable() -> None:
    provider = MockVisionProvider(VisionSettings())

    status = await provider.health()

    assert isinstance(status, ProviderStatus)
    assert status.name == "mock"
    assert status.enabled is False
    assert status.healthy is False
    assert "not yet configured" in status.detail
    assert "deferred to a later phase" in status.detail


@pytest.mark.asyncio
async def test_mock_ocr_provider_health_reports_unavailable() -> None:
    provider = MockOCRProvider(OCRSettings())

    status = await provider.health()

    assert isinstance(status, ProviderStatus)
    assert status.name == "mock"
    assert status.enabled is False
    assert status.healthy is False
    assert "not yet configured" in status.detail
    assert "deferred to a later phase" in status.detail


@pytest.mark.asyncio
async def test_mock_vision_provider_health_stays_unavailable_even_if_enabled_true() -> None:
    """Phase 3 provides no backend selection -- ``enabled=True`` in settings
    must not change anything, since the only concrete provider is the mock."""
    provider = MockVisionProvider(VisionSettings(enabled=True))

    status = await provider.health()

    assert status.enabled is False
    assert status.healthy is False


def test_vision_provider_factory_returns_mock_vision_provider() -> None:
    provider = build_vision_provider(VisionSettings())

    assert isinstance(provider, MockVisionProvider)


def test_ocr_provider_factory_returns_mock_ocr_provider() -> None:
    provider = build_ocr_provider(OCRSettings())

    assert isinstance(provider, MockOCRProvider)


def test_di_container_declares_vision_and_ocr_providers() -> None:
    assert hasattr(Container, "vision_provider")
    assert hasattr(Container, "ocr_provider")


def test_di_container_resolves_vision_provider() -> None:
    container = Container()
    container.settings.override(Settings())

    provider = container.vision_provider()

    assert isinstance(provider, MockVisionProvider)
    assert isinstance(provider, IVisionProvider)


def test_di_container_resolves_ocr_provider() -> None:
    container = Container()
    container.settings.override(Settings())

    provider = container.ocr_provider()

    assert isinstance(provider, MockOCRProvider)
    assert isinstance(provider, IOCRProvider)


def test_di_container_vision_provider_is_a_singleton() -> None:
    container = Container()
    container.settings.override(Settings())

    first = container.vision_provider()
    second = container.vision_provider()

    assert first is second


def test_di_container_ocr_provider_is_a_singleton() -> None:
    container = Container()
    container.settings.override(Settings())

    first = container.ocr_provider()
    second = container.ocr_provider()

    assert first is second


def test_di_container_still_declares_pre_existing_providers() -> None:
    """Regression guard: adding vision/ocr must not disturb any existing
    provider registration."""
    for name in (
        "settings",
        "event_bus",
        "llm_provider",
        "stt_provider",
        "tts_provider",
        "vector_store",
        "database",
        "browser",
        "os_automation",
        "chat_service",
        "voice_service",
        "memory_service",
        "agent_orchestrator",
        "runtime_manager",
    ):
        assert hasattr(Container, name), f"DI container missing pre-existing provider: {name}"
