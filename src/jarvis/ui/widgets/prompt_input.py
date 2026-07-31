"""Prompt input widget — multi-line text area + Send button.

Enter → send, Shift+Enter → newline (standard chat UX).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class _PromptTextEdit(QTextEdit):
    submit = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("promptTextEdit")
        self.setPlaceholderText("Ask JARVIS anything…  (Enter to send · Shift+Enter for newline)")
        self.setAcceptRichText(False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setFixedHeight(90)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (
            event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            event.accept()
            self.submit.emit()
            return
        super().keyPressEvent(event)


class PromptInput(QWidget):
    submitted = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("promptInput")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 8, 12, 12)
        outer.setSpacing(8)

        row = QHBoxLayout()
        row.setSpacing(8)

        self._text = _PromptTextEdit(self)
        self._send = QPushButton("Send", self)
        self._send.setObjectName("sendButton")
        self._send.setProperty("variant", "primary")
        self._send.setFixedHeight(38)
        self._send.setMinimumWidth(96)

        row.addWidget(self._text, 1)
        row.addWidget(self._send, 0, Qt.AlignmentFlag.AlignBottom)
        outer.addLayout(row)

        self._text.submit.connect(self._submit)
        self._send.clicked.connect(self._submit)

    def _submit(self) -> None:
        text = self._text.toPlainText().strip()
        if not text:
            return
        self._text.clear()
        self.submitted.emit(text)

    def set_enabled_input(self, enabled: bool) -> None:
        self._text.setEnabled(enabled)
        self._send.setEnabled(enabled)
