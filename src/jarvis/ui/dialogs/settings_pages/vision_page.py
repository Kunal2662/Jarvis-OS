"""Vision settings page -- Milestone 6, Phase 6.

Exposes the ``JARVIS_VISION_ENABLED`` / ``JARVIS_OCR_ENABLED`` toggles
added in Phase 2. No vision/OCR provider exists yet (Phase 3's mocks
always report unavailable) -- these toggles are configuration only and
have no runtime effect.
"""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QFormLayout, QLabel

from jarvis.ui.dialogs.settings_pages.base import SettingsPage
from jarvis.utils.async_utils import fire_and_forget


class VisionPage(SettingsPage):
    id = "vision"
    title = "Vision"
    category = "Vision"

    def build(self) -> None:
        title = QLabel(self.title)
        title.setStyleSheet("font-size:20px; font-weight:600;")
        self._layout.addWidget(title)

        subtitle = QLabel(
            "Vision and OCR providers are unavailable / not yet implemented. "
            "These toggles only save your preference for when a provider "
            "ships in a later milestone -- turning them on does not enable "
            "any capture, image analysis, or OCR functionality today."
        )
        subtitle.setProperty("role", "muted")
        subtitle.setWordWrap(True)
        self._layout.addWidget(subtitle)

        form = QFormLayout()
        form.setContentsMargins(0, 8, 0, 0)
        form.setSpacing(12)

        self._vision_enabled = QCheckBox("Vision enabled")
        self._vision_enabled.setChecked(self._settings.vision.enabled)
        self._vision_enabled.toggled.connect(
            lambda v: self._persist(
                "JARVIS_VISION_ENABLED", "true" if v else "false", "vision.enabled", v
            )
        )
        form.addRow(self._vision_enabled)

        self._ocr_enabled = QCheckBox("OCR enabled")
        self._ocr_enabled.setChecked(self._settings.ocr.enabled)
        self._ocr_enabled.toggled.connect(
            lambda v: self._persist(
                "JARVIS_OCR_ENABLED", "true" if v else "false", "ocr.enabled", v
            )
        )
        form.addRow(self._ocr_enabled)

        self._layout.addLayout(form)
        self._layout.addStretch(1)

    def _persist(self, env_key: str, env_value: str, attr_path: str, live_value: bool) -> None:
        node = self._settings
        parts = attr_path.split(".")
        for p in parts[:-1]:
            node = getattr(node, p)
        setattr(node, parts[-1], live_value)
        fire_and_forget(self._service.set_env(env_key, env_value))
