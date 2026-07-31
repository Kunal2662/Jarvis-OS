"""Status bar helpers — provider health chip."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QWidget


class ProviderChip(QLabel):
    """Small pill indicating the active LLM provider + health."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("providerChip")
        self.set_state("unknown", "…")

    def set_state(self, state: str, text: str) -> None:
        colors = {
            "healthy": ("#0E9F6E", "#FFFFFF"),
            "degraded": ("#B76E00", "#FFFFFF"),
            "down": ("#D62839", "#FFFFFF"),
            "unknown": ("#12253F", "#6D8BAA"),
        }
        bg, fg = colors.get(state, colors["unknown"])
        self.setText(text)
        self.setStyleSheet(
            f"background:{bg}; color:{fg}; padding:2px 10px; "
            f"border-radius:10px; font-size:11px;"
        )
