"""Milestone 6, Phase 6 — ``VisionPage`` Settings dialog page.

Verifies the two toggles exist, are bound to ``SettingsService`` via
the existing ``JARVIS_VISION_ENABLED``/``JARVIS_OCR_ENABLED`` writable
keys, and have no runtime side effect beyond persisting a preference
(the mock providers ignore ``enabled`` entirely -- see Phase 3).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from PySide6.QtWidgets import QLabel

from jarvis.core.config.settings import Settings
from jarvis.core.di.container import Container
from jarvis.infrastructure.vision.mock_provider import MockVisionProvider
from jarvis.services.settings_service import SettingsService
from jarvis.ui.dialogs.settings_pages import PAGE_REGISTRY
from jarvis.ui.dialogs.settings_pages.vision_page import VisionPage


@pytest.fixture()
def env_file(tmp_path: Path) -> Path:
    p = tmp_path / ".env"
    p.write_text("JARVIS_UI_THEME=jarvis\n", encoding="utf-8")
    return p


def _make_page(env_file: Path, qapp) -> VisionPage:
    settings = Settings()
    service = SettingsService(settings, env_file=env_file)
    return VisionPage(settings, service, None)  # theme_manager unused by this page


def test_vision_page_builds_successfully(qapp, env_file: Path) -> None:
    page = _make_page(env_file, qapp)

    assert page is not None


def test_vision_page_has_id_title_category(qapp, env_file: Path) -> None:
    page = _make_page(env_file, qapp)

    assert page.id == "vision"
    assert page.title == "Vision"
    assert page.category == "Vision"


def test_vision_page_shows_vision_enabled_toggle(qapp, env_file: Path) -> None:
    page = _make_page(env_file, qapp)

    assert page._vision_enabled.text() == "Vision enabled"
    assert page._vision_enabled.isChecked() is False


def test_vision_page_shows_ocr_enabled_toggle(qapp, env_file: Path) -> None:
    page = _make_page(env_file, qapp)

    assert page._ocr_enabled.text() == "OCR enabled"
    assert page._ocr_enabled.isChecked() is False


def test_vision_page_indicates_providers_are_unavailable(qapp, env_file: Path) -> None:
    page = _make_page(env_file, qapp)

    body_text = " ".join(label.text() for label in page.findChildren(QLabel))
    assert "unavailable" in body_text.lower() or "not yet implemented" in body_text.lower()


@pytest.mark.asyncio
async def test_toggling_vision_enabled_persists_to_settings_service(qapp, env_file: Path) -> None:
    page = _make_page(env_file, qapp)

    page._vision_enabled.setChecked(True)
    await asyncio.sleep(0)  # let the fire_and_forget write task run

    text = env_file.read_text(encoding="utf-8")
    assert "JARVIS_VISION_ENABLED=true" in text


@pytest.mark.asyncio
async def test_toggling_ocr_enabled_persists_to_settings_service(qapp, env_file: Path) -> None:
    page = _make_page(env_file, qapp)

    page._ocr_enabled.setChecked(True)
    await asyncio.sleep(0)

    text = env_file.read_text(encoding="utf-8")
    assert "JARVIS_OCR_ENABLED=true" in text


def test_toggling_vision_enabled_updates_live_settings_object_only(qapp, env_file: Path) -> None:
    """The only in-process effect of toggling is updating the plain
    settings attribute the UI reads back -- no provider, service, or
    capability is touched."""
    page = _make_page(env_file, qapp)

    page._vision_enabled.setChecked(True)

    assert page._settings.vision.enabled is True


@pytest.mark.asyncio
async def test_vision_page_toggle_has_no_runtime_side_effects(qapp, env_file: Path) -> None:
    """Toggling must not raise, must not change any provider's reported
    health -- the mock providers ignore ``enabled`` entirely (Phase 3)."""
    page = _make_page(env_file, qapp)
    page._vision_enabled.setChecked(True)
    await asyncio.sleep(0)

    container = Container()
    container.settings.override(page._settings)
    provider = container.vision_provider()
    assert isinstance(provider, MockVisionProvider)
    status = await provider.health()

    assert status.enabled is False
    assert status.healthy is False


def test_vision_page_registered_in_page_registry() -> None:
    descriptor = next(d for d in PAGE_REGISTRY if d.id == "vision")

    assert descriptor.title == "Vision"
    assert descriptor.category == "Vision"
    assert descriptor.implemented is True
    assert descriptor.factory is VisionPage
