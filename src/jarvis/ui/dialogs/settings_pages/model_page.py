"""Model selection page."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QFormLayout, QLabel, QLineEdit

from jarvis.ui.dialogs.settings_pages.base import SettingsPage
from jarvis.utils.async_utils import fire_and_forget

# Curated defaults; users can also type any string.
_OPENAI_MODELS = ["gpt-5.4", "gpt-5.4-mini", "gpt-5.2", "gpt-4o", "gpt-4o-mini", "gpt-4.1"]
_OLLAMA_MODELS = [
    "llama3.1:8b-instruct-q4_K_M",
    "llama3.1:70b-instruct-q4_K_M",
    "qwen2.5:14b-instruct-q4_K_M",
    "mistral:7b-instruct",
]


class ModelPage(SettingsPage):
    id = "model"
    title = "Model Selection"
    category = "AI"

    def build(self) -> None:
        title = QLabel(self.title)
        title.setStyleSheet("font-size:20px; font-weight:600;")
        self._layout.addWidget(title)

        form = QFormLayout()
        form.setContentsMargins(0, 8, 0, 0)
        form.setSpacing(12)

        # OpenAI chat model — editable combo.
        self._openai_model = QComboBox()
        self._openai_model.setEditable(True)
        self._openai_model.addItems(_OPENAI_MODELS)
        self._openai_model.setCurrentText(self._settings.openai.chat_model)
        self._openai_model.editTextChanged.connect(self._on_openai_model)
        form.addRow("OpenAI chat model", self._openai_model)

        # Ollama model.
        self._ollama_model = QComboBox()
        self._ollama_model.setEditable(True)
        self._ollama_model.addItems(_OLLAMA_MODELS)
        self._ollama_model.setCurrentText(self._settings.ollama.model)
        self._ollama_model.editTextChanged.connect(self._on_ollama_model)
        form.addRow("Ollama model", self._ollama_model)

        # System prompt.
        self._system_prompt = QLineEdit(self._settings.ui.system_prompt)
        self._system_prompt.editingFinished.connect(self._on_system_prompt)
        form.addRow("System prompt", self._system_prompt)

        self._layout.addLayout(form)
        self._layout.addStretch(1)

    def _on_openai_model(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        self._settings.openai.chat_model = text
        fire_and_forget(self._service.set_env("JARVIS_OPENAI_CHAT_MODEL", text))

    def _on_ollama_model(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        self._settings.ollama.model = text
        fire_and_forget(self._service.set_env("JARVIS_OLLAMA_MODEL", text))

    def _on_system_prompt(self) -> None:
        text = self._system_prompt.text().strip()
        if not text:
            return
        self._settings.ui.system_prompt = text
        fire_and_forget(self._service.set_env("JARVIS_UI_SYSTEM_PROMPT", text))
