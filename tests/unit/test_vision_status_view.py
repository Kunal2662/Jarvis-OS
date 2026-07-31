"""Milestone 6, Phase 6 — ``VisionStatusView`` Developer Mode section.

Status-only: verifies the view builds, calls
:meth:`~jarvis.services.vision_service.VisionService.status`, and
displays exactly the provider/enabled/healthy/detail fields it
returns. No image, screenshot, OCR text, camera feed, logs, history,
or trace output exists here.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QLabel

from jarvis.core.config.settings import Settings
from jarvis.core.di.container import Container
from jarvis.ui.views.developer.developer_dashboard import _SECTIONS
from jarvis.ui.views.developer.vision_status_view import VisionStatusView


class _FakeVisionService:
    def __init__(self, *, healthy: bool = False) -> None:
        self._healthy = healthy
        self.status_called = False

    async def status(self) -> dict:
        self.status_called = True
        return {
            "vision": {
                "provider": "mock",
                "enabled": False,
                "healthy": self._healthy,
                "detail": "vision detail for test",
            },
            "ocr": {
                "provider": "mock",
                "enabled": False,
                "healthy": self._healthy,
                "detail": "ocr detail for test",
            },
        }


def _make_container(tmp_path, vision_service) -> Container:
    settings = Settings(data_dir=tmp_path)
    container = Container()
    container.settings.override(settings)
    container.vision_service.override(vision_service)
    return container


def _row_values(widget) -> list[str]:
    labels = widget.findChildren(QLabel)
    return [label.text() for label in labels if label.objectName() == "rowValue"]


@pytest.mark.asyncio
async def test_vision_status_view_builds_successfully(qapp, tmp_path) -> None:
    container = _make_container(tmp_path, _FakeVisionService())

    view = VisionStatusView(container)

    assert view is not None


@pytest.mark.asyncio
async def test_vision_status_view_calls_vision_service_status(qapp, tmp_path) -> None:
    service = _FakeVisionService()
    container = _make_container(tmp_path, service)
    view = VisionStatusView(container)

    await view._refresh()

    assert service.status_called is True


@pytest.mark.asyncio
async def test_vision_status_view_displays_vision_provider_status(qapp, tmp_path) -> None:
    container = _make_container(tmp_path, _FakeVisionService())
    view = VisionStatusView(container)

    await view._refresh()

    values = _row_values(view._vision_card)
    assert "mock" in values
    assert "False" in values  # enabled
    assert "vision detail for test" in values


@pytest.mark.asyncio
async def test_vision_status_view_displays_ocr_provider_status(qapp, tmp_path) -> None:
    container = _make_container(tmp_path, _FakeVisionService())
    view = VisionStatusView(container)

    await view._refresh()

    values = _row_values(view._ocr_card)
    assert "mock" in values
    assert "False" in values  # enabled
    assert "ocr detail for test" in values


@pytest.mark.asyncio
async def test_vision_status_view_reflects_service_response_exactly(qapp, tmp_path) -> None:
    """No invented fields, no transformation -- displayed values must
    exactly match what VisionService.status() returned."""
    service = _FakeVisionService(healthy=True)
    container = _make_container(tmp_path, service)
    view = VisionStatusView(container)
    expected = await service.status()

    await view._refresh()

    vision_values = set(_row_values(view._vision_card))
    for value in expected["vision"].values():
        assert str(value) in vision_values
    ocr_values = set(_row_values(view._ocr_card))
    for value in expected["ocr"].values():
        assert str(value) in ocr_values


@pytest.mark.asyncio
async def test_vision_status_view_shows_no_images_or_screenshots(qapp, tmp_path) -> None:
    """Regression guard against scope creep: no QPixmap/QImage/QLabel with
    pixmap content anywhere in the view."""
    container = _make_container(tmp_path, _FakeVisionService())
    view = VisionStatusView(container)

    await view._refresh()

    for label in view.findChildren(QLabel):
        assert label.pixmap() is None or label.pixmap().isNull()


# ---------------------------------------------------------------------------
# Developer dashboard registration
# ---------------------------------------------------------------------------
def test_developer_dashboard_registers_vision_status_section() -> None:
    ids = [section_id for section_id, _icon, _label in _SECTIONS]

    assert "vision_status" in ids


def test_developer_dashboard_vision_status_section_is_appended_last() -> None:
    """Regression guard: Phase 6 must append, never reorder, existing
    sections."""
    ids = [section_id for section_id, _icon, _label in _SECTIONS]

    assert ids[-1] == "vision_status"
    assert ids[:-1] == [
        "dashboard",
        "api_center",
        "update_center",
        "modules",
        "plugins",
        "ai_models",
        "performance",
        "logs",
        "configuration",
        "security",
        "backup",
        "console",
        "system_info",
        "agent_trace",
    ]
