"""Wake-word settings page.

Backed by :mod:`jarvis.infrastructure.wake_word.provider_factory`, a
pluggable registry keyed by :class:`WakeWordEngine` — same pattern as
the TTS provider page. Adding a new engine only means writing an
adapter + registering it; this page doesn't change.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
)

from jarvis.core.types import WakeWordEngine
from jarvis.ui.dialogs.settings_pages.base import SettingsPage
from jarvis.utils.async_utils import fire_and_forget


class WakeWordPage(SettingsPage):
    id = "wake_word"
    title = "Wake Word"
    category = "Voice"

    def build(self) -> None:
        title = QLabel(self.title)
        title.setStyleSheet("font-size:20px; font-weight:600;")
        self._layout.addWidget(title)

        subtitle = QLabel(
            "Say a keyword and JARVIS starts listening automatically — " "no hotkey needed."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color:#6D8BAA;")
        self._layout.addWidget(subtitle)

        form = QFormLayout()
        form.setContentsMargins(0, 8, 0, 0)
        form.setSpacing(12)

        self._enabled = QCheckBox("Enable wake-word detection")
        self._enabled.setChecked(self._settings.wake.enabled)
        self._enabled.toggled.connect(
            lambda v: self._persist(
                "JARVIS_WAKE_ENABLED", "true" if v else "false", "wake.enabled", v
            )
        )
        form.addRow(self._enabled)

        self._engine = QComboBox()
        for e in WakeWordEngine:
            self._engine.addItem(e.value, e)
        idx = self._engine.findData(self._settings.wake.engine)
        if idx >= 0:
            self._engine.setCurrentIndex(idx)
        self._engine.currentIndexChanged.connect(self._on_engine)
        form.addRow("Engine", self._engine)

        self._keywords = QLineEdit(", ".join(self._settings.wake.keywords))
        self._keywords.setPlaceholderText("jarvis, hey jarvis")
        self._keywords.editingFinished.connect(self._on_keywords)
        form.addRow("Keywords (comma-sep)", self._keywords)

        self._sensitivity = QDoubleSpinBox()
        self._sensitivity.setRange(0.0, 1.0)
        self._sensitivity.setSingleStep(0.05)
        self._sensitivity.setValue(self._settings.wake.sensitivity)
        self._sensitivity.valueChanged.connect(self._on_sensitivity)
        form.addRow("Sensitivity", self._sensitivity)

        self._model_path = QLineEdit(self._settings.wake.model_path)
        self._model_path.setPlaceholderText("(optional) custom model / .ppn keyword file")
        self._model_path.editingFinished.connect(self._on_model_path)
        form.addRow("Custom model path", self._model_path)

        self._access_key = QLineEdit()
        self._access_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._access_key.setPlaceholderText("Porcupine AccessKey (leave blank to keep current)")
        self._access_key.editingFinished.connect(self._on_access_key)
        form.addRow("Porcupine AccessKey", self._access_key)

        self._layout.addLayout(form)

        hint = QLabel(
            "Porcupine needs a free AccessKey from console.picovoice.ai. "
            "openWakeWord is fully offline and community-model based. "
            "Changes take effect the next time wake-word listening starts."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#6D8BAA;")
        self._layout.addWidget(hint)
        self._layout.addStretch(1)

    # ------------------------------------------------------------------
    def _persist(self, env_key: str, env_value: str, attr_path: str, live_value) -> None:
        node = self._settings
        parts = attr_path.split(".")
        for p in parts[:-1]:
            node = getattr(node, p)
        setattr(node, parts[-1], live_value)
        fire_and_forget(self._service.set_env(env_key, env_value))

    def _on_engine(self) -> None:
        e: WakeWordEngine = self._engine.currentData()
        self._persist("JARVIS_WAKE_ENGINE", e.value, "wake.engine", e)

    def _on_keywords(self) -> None:
        raw = self._keywords.text()
        keys = [k.strip() for k in raw.split(",") if k.strip()]
        self._persist("JARVIS_WAKE_KEYWORDS", ",".join(keys), "wake.keywords", keys)

    def _on_sensitivity(self, value: float) -> None:
        self._persist("JARVIS_WAKE_SENSITIVITY", f"{value:.2f}", "wake.sensitivity", value)

    def _on_model_path(self) -> None:
        text = self._model_path.text().strip()
        self._persist("JARVIS_WAKE_MODEL_PATH", text, "wake.model_path", text)

    def _on_access_key(self) -> None:
        text = self._access_key.text().strip()
        if not text:
            return
        from pydantic import SecretStr

        self._settings.wake.access_key = SecretStr(text)
        fire_and_forget(self._service.set_env("JARVIS_WAKE_ACCESS_KEY", text))
        self._access_key.clear()
