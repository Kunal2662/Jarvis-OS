"""AI Model Manager -- Milestone 5, section 10A.

Real data pulled from Settings: which LLM/STT/TTS providers are
configured and enabled, and which models they're pointed at.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from jarvis.ui.components import SectionCard, StatusBadge

if TYPE_CHECKING:
    from jarvis.core.config.settings import Settings


class AiModelManagerView(QWidget):
    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(14)

        title = QLabel("AI Model Manager")
        title.setObjectName("greetingTitle")
        outer.addWidget(title)

        llm_card = SectionCard("LLM Providers")
        for name, cfg, model_attr in [
            ("OpenAI", settings.openai, "chat_model"),
            ("Ollama", settings.ollama, "model"),
            ("Gemini", settings.gemini, "chat_model"),
        ]:
            row = QLabel(
                f"{name} — model: {getattr(cfg, model_attr, 'n/a')}"
                + (" (default)" if settings.llm_default_provider.value == name.lower() else "")
            )
            row.setObjectName("rowValue")
            llm_card.body.addWidget(row)
            badge = StatusBadge(
                "Enabled" if cfg.enabled else "Disabled", "success" if cfg.enabled else "neutral"
            )
            llm_card.body.addWidget(badge)
        outer.addWidget(llm_card)

        voice_card = SectionCard("Speech Providers")
        voice_card.body.addWidget(QLabel(f"STT backend: {settings.stt.backend.value}"))
        voice_card.body.addWidget(QLabel(f"TTS backend: {settings.tts.backend.value}"))
        outer.addWidget(voice_card)
        outer.addStretch(1)
