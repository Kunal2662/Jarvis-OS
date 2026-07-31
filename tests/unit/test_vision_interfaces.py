"""Milestone 6, Phase 1 — interface-shape tests for the new vision/OCR ports.

These only verify the ``Protocol`` contract itself (importable,
runtime-checkable, ``name``/``health()`` present). No provider
implementation, DI wiring, settings, or vision/OCR logic exists yet —
those are later phases.
"""

from __future__ import annotations

import typing
from typing import Protocol, runtime_checkable

import pytest

from jarvis.core.exceptions import InfrastructureError, OCRProviderError, VisionProviderError
from jarvis.core.interfaces import IOCRProvider as IOCRProviderFromPackage
from jarvis.core.interfaces import IVisionProvider as IVisionProviderFromPackage
from jarvis.core.interfaces.ocr_provider import IOCRProvider
from jarvis.core.interfaces.vision_provider import IVisionProvider
from jarvis.core.types import ProviderStatus


def test_ivision_provider_importable_from_its_own_module() -> None:
    assert IVisionProvider is not None


def test_iocr_provider_importable_from_its_own_module() -> None:
    assert IOCRProvider is not None


def test_ivision_provider_importable_from_interfaces_package() -> None:
    assert IVisionProviderFromPackage is IVisionProvider


def test_iocr_provider_importable_from_interfaces_package() -> None:
    assert IOCRProviderFromPackage is IOCRProvider


def test_ivision_provider_is_a_runtime_checkable_protocol() -> None:
    assert issubclass(type(IVisionProvider), type(Protocol))
    assert getattr(IVisionProvider, "_is_runtime_protocol", False) is True


def test_iocr_provider_is_a_runtime_checkable_protocol() -> None:
    assert issubclass(type(IOCRProvider), type(Protocol))
    assert getattr(IOCRProvider, "_is_runtime_protocol", False) is True


def test_ivision_provider_declares_only_name_and_health() -> None:
    assert set(typing.get_protocol_members(IVisionProvider)) == {"name", "health"}


def test_iocr_provider_declares_only_name_and_health() -> None:
    assert set(typing.get_protocol_members(IOCRProvider)) == {"name", "health"}


@runtime_checkable
class _ConformingProviderShape(Protocol):
    """Reference shape only, to document what "conforming" means below —
    not used directly, the real check is the isinstance tests."""

    name: str

    async def health(self) -> ProviderStatus: ...


class _FakeVisionLikeProvider:
    """A minimal object satisfying the ``name`` + ``health()`` shape,
    used only to prove the Protocol is structurally checkable — not a
    real provider implementation."""

    name = "fake"

    async def health(self) -> ProviderStatus:
        return ProviderStatus(name=self.name, enabled=False, healthy=False, detail="test double")


def test_a_conforming_object_satisfies_ivision_provider_structurally() -> None:
    assert isinstance(_FakeVisionLikeProvider(), IVisionProvider)


def test_a_conforming_object_satisfies_iocr_provider_structurally() -> None:
    assert isinstance(_FakeVisionLikeProvider(), IOCRProvider)


class _MissingHealth:
    name = "incomplete"


def test_an_object_missing_health_does_not_satisfy_ivision_provider() -> None:
    assert not isinstance(_MissingHealth(), IVisionProvider)


def test_an_object_missing_health_does_not_satisfy_iocr_provider() -> None:
    assert not isinstance(_MissingHealth(), IOCRProvider)


@pytest.mark.asyncio
async def test_fake_vision_like_provider_health_returns_provider_status() -> None:
    provider = _FakeVisionLikeProvider()
    status = await provider.health()

    assert isinstance(status, ProviderStatus)
    assert status.name == "fake"
    assert status.enabled is False
    assert status.healthy is False


def test_vision_provider_error_inherits_infrastructure_error() -> None:
    assert issubclass(VisionProviderError, InfrastructureError)


def test_ocr_provider_error_inherits_infrastructure_error() -> None:
    assert issubclass(OCRProviderError, InfrastructureError)


def test_vision_provider_error_is_raisable_and_catchable() -> None:
    with pytest.raises(VisionProviderError):
        raise VisionProviderError("boom")


def test_ocr_provider_error_is_raisable_and_catchable() -> None:
    with pytest.raises(OCRProviderError):
        raise OCRProviderError("boom")
