"""Status badges -- small colored pills used for API health, update phase,
connection state, etc."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QWidget

# Maps a semantic state name to a QSS ``variant`` property value; the QSS
# theme (see resources/themes/jarvis.qss) supplies the actual colors so
# badges automatically match whichever theme is active.
_VARIANTS = {
    "success": "success",
    "connected": "success",
    "healthy": "success",
    "warning": "warning",
    "running": "warning",
    "degraded": "warning",
    "danger": "danger",
    "auth_failed": "danger",
    "network_error": "danger",
    "invalid_key": "danger",
    "failed": "danger",
    "neutral": "neutral",
    "disabled": "neutral",
    "unknown": "neutral",
}


class StatusBadge(QLabel):
    def __init__(self, text: str, state: str = "neutral", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("statusBadge")
        self.set_state(state, text)

    def set_state(self, state: str, text: str | None = None) -> None:
        if text is not None:
            self.setText(text)
        self.setProperty("variant", _VARIANTS.get(state, "neutral"))
        self.style().unpolish(self)
        self.style().polish(self)
