"""AI provider selection page."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
)

from jarvis.core.types import LLMProviderName
from jarvis.ui.dialogs.settings_pages.base import SettingsPage
from jarvis.utils.async_utils import fire_and_forget


class AIProviderPage(SettingsPage):
    id = "ai_provider"
    title = "AI Provider"
    category = "AI"

    def build(self) -> None:
        title = QLabel(self.title)
        title.setStyleSheet("font-size:20px; font-weight:600;")
        self._layout.addWidget(title)

        form = QFormLayout()
        form.setContentsMargins(0, 8, 0, 0)
        form.setSpacing(12)

        self._default = QComboBox()
        for p in LLMProviderName:
            self._default.addItem(p.value, p)
        idx = self._default.findData(self._settings.llm_default_provider)
        if idx >= 0:
            self._default.setCurrentIndex(idx)
        self._default.currentIndexChanged.connect(self._on_default_provider)
        form.addRow("Default provider", self._default)

        # OpenAI enabled flag.
        self._openai_enabled = QCheckBox("OpenAI enabled")
        self._openai_enabled.setChecked(self._settings.openai.enabled)
        self._openai_enabled.toggled.connect(self._on_openai_enabled)
        form.addRow(self._openai_enabled)

        # Ollama enabled flag + base URL.
        self._ollama_enabled = QCheckBox("Ollama enabled (local)")
        self._ollama_enabled.setChecked(self._settings.ollama.enabled)
        self._ollama_enabled.toggled.connect(self._on_ollama_enabled)
        form.addRow(self._ollama_enabled)

        self._ollama_base = QLineEdit(self._settings.ollama.base_url)
        self._ollama_base.editingFinished.connect(self._on_ollama_base)
        form.addRow("Ollama base URL", self._ollama_base)

        hint = QLabel("Changes to the default provider take effect on the next launch.")
        hint.setStyleSheet("color:#6D8BAA;")
        self._layout.addLayout(form)
        self._layout.addWidget(hint)
        self._layout.addStretch(1)

    def _on_default_provider(self) -> None:
        p: LLMProviderName = self._default.currentData()
        self._settings.llm_default_provider = p
        fire_and_forget(self._service.set_env("JARVIS_LLM_DEFAULT_PROVIDER", p.value))

    def _on_openai_enabled(self, checked: bool) -> None:
        self._settings.openai.enabled = checked
        fire_and_forget(
            self._service.set_env("JARVIS_OPENAI_ENABLED", "true" if checked else "false")
        )

    def _on_ollama_enabled(self, checked: bool) -> None:
        self._settings.ollama.enabled = checked
        fire_and_forget(
            self._service.set_env("JARVIS_OLLAMA_ENABLED", "true" if checked else "false")
        )

    def _on_ollama_base(self) -> None:
        value = self._ollama_base.text().strip()
        if value:
            self._settings.ollama.base_url = value
            fire_and_forget(self._service.set_env("JARVIS_OLLAMA_BASE_URL", value))
