"""Vision Status panel -- Milestone 6, Phase 6, Developer Mode section.

Displays :class:`~jarvis.services.vision_service.VisionService`'s
``status()`` output (provider name, enabled, healthy, detail) for the
vision and OCR providers. Status-only, following the same pattern as
:class:`~jarvis.ui.views.developer.agent_trace_view.AgentTraceView`
(async work via ``fire_and_forget``) and
:class:`~jarvis.ui.views.developer.system_information_view.SystemInformationView`
(``KeyValueRow`` display). No image, screenshot, OCR text, camera
feed, logs, history, or trace output is shown here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from jarvis.core.logging.logger import get_logger
from jarvis.ui.components import KeyValueRow, SectionCard, StatusBadge
from jarvis.utils.async_utils import fire_and_forget

if TYPE_CHECKING:
    from jarvis.core.di.container import Container

_logger = get_logger("jarvis.ui.developer.vision_status")


class VisionStatusView(QWidget):
    def __init__(self, container: Container, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._container = container

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(14)

        title = QLabel("Vision Status")
        title.setObjectName("greetingTitle")
        outer.addWidget(title)

        subtitle = QLabel(
            "Reports whether the vision and OCR providers are available. "
            "No capture, image analysis, or OCR happens here."
        )
        subtitle.setProperty("role", "muted")
        subtitle.setWordWrap(True)
        outer.addWidget(subtitle)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._on_refresh)
        outer.addWidget(refresh_btn)

        self._vision_card = SectionCard("Vision Provider")
        outer.addWidget(self._vision_card)

        self._ocr_card = SectionCard("OCR Provider")
        outer.addWidget(self._ocr_card)

        outer.addStretch(1)

        self._on_refresh()

    # ------------------------------------------------------------------
    def _on_refresh(self) -> None:
        fire_and_forget(self._refresh())

    async def _refresh(self) -> None:
        try:
            status = await self._container.vision_service().status()
        except Exception as err:
            _logger.exception("Vision Status refresh failed.")
            for card in (self._vision_card, self._ocr_card):
                self._clear_card(card)
                card.body.addWidget(StatusBadge("Error", "error"))
                card.body.addWidget(QLabel(f"Error: {err}"))
            return

        self._render_provider(self._vision_card, status["vision"])
        self._render_provider(self._ocr_card, status["ocr"])

    def _render_provider(self, card: SectionCard, info: dict[str, object]) -> None:
        self._clear_card(card)
        healthy = bool(info["healthy"])
        badge_text = "Healthy" if healthy else "Unavailable"
        badge_state = "success" if healthy else "warning"
        card.body.addWidget(StatusBadge(badge_text, badge_state))
        card.body.addWidget(KeyValueRow("Provider", str(info["provider"])))
        card.body.addWidget(KeyValueRow("Enabled", str(info["enabled"])))
        card.body.addWidget(KeyValueRow("Healthy", str(info["healthy"])))
        card.body.addWidget(KeyValueRow("Detail", str(info["detail"])))

    @staticmethod
    def _clear_card(card: SectionCard) -> None:
        while card.body.count():
            item = card.body.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
