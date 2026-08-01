"""Private Live Transcript window (Milestone 5, section 5).

Matches the reference UI's floating "PRIVATE LIVE TRANSCRIPT (Only You
Can See)" panel: a small window showing the live conversation with a
lock badge, reusing the same :class:`ChatView` bubble rendering as the
main Chat page so transcript styling never drifts out of sync with the
primary chat surface.

Upgraded from a mirror-the-final-reply-only view to a real live
transcript:

* **Live streaming** -- both the user's own voice turn (partial STT
  results as they arrive) and the assistant's reply stream token by
  token into their own bubble via :meth:`begin_user_stream` /
  :meth:`append_user_token` / :meth:`end_user_stream` and the assistant
  equivalents, reusing :class:`ChatView`'s generic ``begin_stream`` /
  ``append_stream_token`` / ``end_stream``.
* **Timestamps** on every turn.
* **Search** -- ``Find`` steps through matches in the transcript via
  ``QTextBrowser.find()``; Enter repeats the last search.
* **Copy** / **Export** (.txt) / **Clear**.
* **Auto Scroll** toggle.
* **Pinned Mode** -- snaps to a small fixed-size overlay in the
  bottom-right corner of the screen, like an always-visible HUD panel.
* **Always-on-top** toggle (on by default, matching the original
  behaviour, but now switchable).
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from jarvis.core.types import Role
from jarvis.ui.components.icons import Icon
from jarvis.ui.widgets.chat_view import ChatView

_PINNED_SIZE = (360, 420)
_PINNED_MARGIN = 24


class PrivateTranscriptDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Private Live Transcript")
        self._always_on_top = True
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.resize(420, 560)
        self._pinned = False
        self._turns: list[tuple[str, str, str]] = []  # (role, text, timestamp)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(6)
        header.addWidget(Icon("lock", size=16))
        title = QLabel("PRIVATE LIVE TRANSCRIPT")
        title.setObjectName("cardTitle")
        header.addWidget(title)
        header.addStretch(1)
        subtitle = QLabel("(Only You Can See)")
        subtitle.setObjectName("rowSubtitle")
        header.addWidget(subtitle)
        outer.addLayout(header)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Find in transcript…")
        self._search.returnPressed.connect(self._find_next)
        toolbar.addWidget(self._search, 1)

        find_btn = QPushButton("Find")
        find_btn.setObjectName("cardAction")
        find_btn.clicked.connect(self._find_next)
        toolbar.addWidget(find_btn)
        outer.addLayout(toolbar)

        toggles = QHBoxLayout()
        toggles.setSpacing(10)
        self._auto_scroll = QCheckBox("Auto Scroll")
        self._auto_scroll.setChecked(True)
        toggles.addWidget(self._auto_scroll)

        self._pinned_check = QCheckBox("Pinned")
        self._pinned_check.toggled.connect(self._set_pinned)
        toggles.addWidget(self._pinned_check)

        self._always_on_top_check = QCheckBox("Always on Top")
        self._always_on_top_check.setChecked(True)
        self._always_on_top_check.toggled.connect(self._set_always_on_top)
        toggles.addWidget(self._always_on_top_check)
        toggles.addStretch(1)
        outer.addLayout(toggles)

        self._chat_view = ChatView(self)
        outer.addWidget(self._chat_view, 1)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        copy_btn = QPushButton("Copy")
        copy_btn.setObjectName("cardAction")
        copy_btn.clicked.connect(self.copy_transcript)
        actions.addWidget(copy_btn)

        export_btn = QPushButton("Export")
        export_btn.setObjectName("cardAction")
        export_btn.clicked.connect(self.export_transcript)
        actions.addWidget(export_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.setObjectName("cardAction")
        clear_btn.clicked.connect(self.clear)
        actions.addWidget(clear_btn)
        actions.addStretch(1)
        outer.addLayout(actions)

        footer_row = QHBoxLayout()
        footer_row.setSpacing(6)
        footer_row.addWidget(Icon("lock", size=12))
        footer = QLabel("Private. Secure. Encrypted. Only you can see this.")
        footer.setObjectName("rowSubtitle")
        footer_row.addWidget(footer, 1)
        outer.addLayout(footer_row)

    # ------------------------------------------------------------------
    # Finalized turns (backward-compatible with the original API)
    # ------------------------------------------------------------------
    def add_message(self, role: Role, content: str) -> None:
        if not content:
            return
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._chat_view.add_message(role, content, timestamp=timestamp)
        self._turns.append((role, content, timestamp))

    # ------------------------------------------------------------------
    # Live streaming -- assistant reply
    # ------------------------------------------------------------------
    def begin_assistant_stream(self) -> None:
        self._chat_view.begin_stream("assistant", timestamp=datetime.now().strftime("%H:%M:%S"))

    def append_assistant_token(self, token: str) -> None:
        self._chat_view.append_stream_token(token)

    def end_assistant_stream(self) -> None:
        text = self._chat_view.end_stream()
        if text:
            self._turns.append(("assistant", text, datetime.now().strftime("%H:%M:%S")))

    # ------------------------------------------------------------------
    # Live streaming -- user voice transcript (partial STT results)
    # ------------------------------------------------------------------
    def begin_user_stream(self) -> None:
        self._chat_view.begin_stream("user", timestamp=datetime.now().strftime("%H:%M:%S"))

    def append_user_token(self, token: str) -> None:
        self._chat_view.append_stream_token(token)

    def end_user_stream(self) -> None:
        text = self._chat_view.end_stream()
        if text:
            self._turns.append(("user", text, datetime.now().strftime("%H:%M:%S")))

    # ------------------------------------------------------------------
    # Toolbar actions
    # ------------------------------------------------------------------
    def clear(self) -> None:
        self._chat_view.clear()
        self._turns.clear()

    def copy_transcript(self) -> None:
        QGuiApplication.clipboard().setText(self._as_plain_text())

    def export_transcript(self) -> None:
        default_name = f"private_transcript_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Transcript", default_name, "Text Files (*.txt)"
        )
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self._as_plain_text())

    def _as_plain_text(self) -> str:
        who = {"user": "You", "assistant": "JARVIS", "system": "System", "tool": "Tool"}
        return "\n\n".join(
            f"[{timestamp}] {who.get(role, role)}: {text}" for role, text, timestamp in self._turns
        )

    def _find_next(self) -> None:
        query = self._search.text().strip()
        if not query:
            return
        found = self._chat_view._browser.find(query)
        if not found:
            # Wrap around: jump to the top and search again.
            cursor = self._chat_view._browser.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            self._chat_view._browser.setTextCursor(cursor)
            self._chat_view._browser.find(query)

    # ------------------------------------------------------------------
    # Display modes
    # ------------------------------------------------------------------
    def _set_pinned(self, pinned: bool) -> None:
        self._pinned = pinned
        if pinned:
            screen = QGuiApplication.primaryScreen()
            width, height = _PINNED_SIZE
            self.resize(width, height)
            if screen is not None:
                geo = screen.availableGeometry()
                self.move(
                    geo.x() + geo.width() - width - _PINNED_MARGIN,
                    geo.y() + geo.height() - height - _PINNED_MARGIN,
                )
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
            self._always_on_top_check.setChecked(True)
            self.show()
        else:
            self.resize(420, 560)

    def _set_always_on_top(self, enabled: bool) -> None:
        self._always_on_top = enabled
        was_visible = self.isVisible()
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, enabled)
        if was_visible:
            self.show()
