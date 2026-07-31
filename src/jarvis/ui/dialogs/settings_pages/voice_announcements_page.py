"""Voice Announcements settings page -- Milestone 5, section 10F."""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QLabel, QLineEdit

from jarvis.ui.dialogs.settings_pages.base import SettingsPage
from jarvis.utils.async_utils import fire_and_forget

_STYLES = ["formal", "friendly", "concise"]


class VoiceAnnouncementsPage(SettingsPage):
    id = "voice_announcements"
    title = "Voice Announcements"
    category = "Voice"

    def build(self) -> None:
        title = QLabel(self.title)
        title.setStyleSheet("font-size:20px; font-weight:600;")
        self._layout.addWidget(title)

        subtitle = QLabel("JARVIS speaks update progress out loud (Checking, Downloading, ...).")
        subtitle.setProperty("role", "muted")
        subtitle.setWordWrap(True)
        self._layout.addWidget(subtitle)

        form = QFormLayout()
        form.setContentsMargins(0, 8, 0, 0)
        form.setSpacing(12)

        cfg = self._settings.voice_announce

        self._enabled = QCheckBox("Enable voice announcements")
        self._enabled.setChecked(cfg.enabled)
        self._enabled.toggled.connect(
            lambda v: self._persist(
                "JARVIS_VOICE_ANNOUNCE_ENABLED",
                "true" if v else "false",
                "voice_announce.enabled",
                v,
            )
        )
        form.addRow(self._enabled)

        self._style = QComboBox()
        self._style.addItems(_STYLES)
        self._style.setCurrentText(cfg.style)
        self._style.currentTextChanged.connect(
            lambda t: self._persist("JARVIS_VOICE_ANNOUNCE_STYLE", t, "voice_announce.style", t)
        )
        form.addRow("Voice style", self._style)

        self._volume = QDoubleSpinBox()
        self._volume.setRange(0.0, 1.0)
        self._volume.setSingleStep(0.05)
        self._volume.setValue(cfg.volume)
        self._volume.valueChanged.connect(
            lambda v: self._persist(
                "JARVIS_VOICE_ANNOUNCE_VOLUME", f"{v:.2f}", "voice_announce.volume", v
            )
        )
        form.addRow("Volume", self._volume)

        self._speed = QDoubleSpinBox()
        self._speed.setRange(0.5, 2.0)
        self._speed.setSingleStep(0.05)
        self._speed.setValue(cfg.speed)
        self._speed.valueChanged.connect(
            lambda v: self._persist(
                "JARVIS_VOICE_ANNOUNCE_SPEED", f"{v:.2f}", "voice_announce.speed", v
            )
        )
        form.addRow("Speed", self._speed)

        self._language = QLineEdit(cfg.language)
        self._language.editingFinished.connect(
            lambda: self._persist(
                "JARVIS_VOICE_ANNOUNCE_LANGUAGE",
                self._language.text().strip(),
                "voice_announce.language",
                self._language.text().strip(),
            )
        )
        form.addRow("Language", self._language)

        self._layout.addLayout(form)
        self._layout.addStretch(1)

    def _persist(self, env_key: str, env_value: str, attr_path: str, live_value) -> None:
        node = self._settings
        parts = attr_path.split(".")
        for p in parts[:-1]:
            node = getattr(node, p)
        setattr(node, parts[-1], live_value)
        fire_and_forget(self._service.set_env(env_key, env_value))
