"""Startup + UI-behaviour settings page."""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QLabel

from jarvis.core.types import StreamingMode
from jarvis.ui.dialogs.settings_pages.base import SettingsPage
from jarvis.utils.async_utils import fire_and_forget


class StartupPage(SettingsPage):
    id = "startup"
    title = "Startup & Behaviour"
    category = "General"

    def build(self) -> None:
        title = QLabel(self.title)
        title.setStyleSheet("font-size:20px; font-weight:600;")
        self._layout.addWidget(title)

        form = QFormLayout()
        form.setContentsMargins(0, 8, 0, 0)
        form.setSpacing(12)

        self._start_min = QCheckBox("Start minimized to system tray")
        self._start_min.setChecked(self._settings.ui.start_minimized)
        self._start_min.toggled.connect(self._on_start_min)
        form.addRow(self._start_min)

        self._stream_combo = QComboBox()
        for m in StreamingMode:
            self._stream_combo.addItem(m.value, m)
        idx = self._stream_combo.findData(self._settings.ui.streaming_mode)
        if idx >= 0:
            self._stream_combo.setCurrentIndex(idx)
        self._stream_combo.currentIndexChanged.connect(self._on_streaming_mode)
        form.addRow("Streaming style", self._stream_combo)

        self._layout.addLayout(form)
        self._layout.addStretch(1)

    def _on_start_min(self, checked: bool) -> None:
        self._settings.ui.start_minimized = checked
        fire_and_forget(
            self._service.set_env("JARVIS_UI_START_MINIMIZED", "true" if checked else "false")
        )

    def _on_streaming_mode(self) -> None:
        mode: StreamingMode = self._stream_combo.currentData()
        self._settings.ui.streaming_mode = mode
        fire_and_forget(self._service.set_env("JARVIS_UI_STREAMING_MODE", mode.value))
