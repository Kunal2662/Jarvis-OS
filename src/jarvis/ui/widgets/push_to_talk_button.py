"""Push-to-talk button widget.

* Hold down → emits ``pressed`` on mouse-down and ``released`` on mouse-up.
* Click (short press) → emits ``toggled`` for `VoiceMode.TOGGLE`.

The parent widget decides which signal to hook up based on
``settings.voice.mode``.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QPushButton, QWidget


class PushToTalkButton(QPushButton):
    pressed_ptt = Signal()
    released_ptt = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("🎤  Hold to talk", parent)
        self.setObjectName("pushToTalkButton")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(38)

    # ------------------------------------------------------------------
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.setChecked(True)
            self.setText("🎙  Listening…")
            self.pressed_ptt.emit()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.isChecked():
            self.setChecked(False)
            self.setText("🎤  Hold to talk")
            self.released_ptt.emit()
        super().mouseReleaseEvent(event)

    # Convenience for external state (e.g. hotkey-driven).
    def set_listening(self, on: bool) -> None:
        self.setChecked(on)
        self.setText("🎙  Listening…" if on else "🎤  Hold to talk")
