"""Logging settings page."""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QLabel

from jarvis.ui.dialogs.settings_pages.base import SettingsPage
from jarvis.utils.async_utils import fire_and_forget

_LEVELS = ["TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class LoggingPage(SettingsPage):
    id = "logging"
    title = "Logging"
    category = "General"

    def build(self) -> None:
        title = QLabel(self.title)
        title.setStyleSheet("font-size:20px; font-weight:600;")
        self._layout.addWidget(title)

        form = QFormLayout()
        form.setContentsMargins(0, 8, 0, 0)
        form.setSpacing(12)

        self._level = QComboBox()
        self._level.addItems(_LEVELS)
        self._level.setCurrentText(self._settings.log.level)
        self._level.currentIndexChanged.connect(self._on_level)
        form.addRow("Level", self._level)

        self._json = QCheckBox("Emit JSON logs (production style)")
        self._json.setChecked(self._settings.log.json)
        self._json.toggled.connect(self._on_json)
        form.addRow(self._json)

        self._file = QCheckBox("Also log to file (rotates automatically)")
        self._file.setChecked(self._settings.log.file_enabled)
        self._file.toggled.connect(self._on_file)
        form.addRow(self._file)

        hint = QLabel("Changes to logging take effect on the next launch.")
        hint.setStyleSheet("color:#6D8BAA;")
        self._layout.addLayout(form)
        self._layout.addWidget(hint)
        self._layout.addStretch(1)

    def _on_level(self) -> None:
        value = self._level.currentText()
        self._settings.log.level = value  # type: ignore[assignment]
        fire_and_forget(self._service.set_env("JARVIS_LOG_LEVEL", value))

    def _on_json(self, checked: bool) -> None:
        self._settings.log.json = checked
        fire_and_forget(self._service.set_env("JARVIS_LOG_JSON", "true" if checked else "false"))

    def _on_file(self, checked: bool) -> None:
        self._settings.log.file_enabled = checked
        fire_and_forget(
            self._service.set_env("JARVIS_LOG_FILE_ENABLED", "true" if checked else "false")
        )
