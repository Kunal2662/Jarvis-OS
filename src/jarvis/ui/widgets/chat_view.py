"""Chat display widget — a scrollable list of message bubbles.

Uses a single QTextBrowser for simplicity + correctness of rich-text
rendering. Each message is appended as an HTML block; the streaming
assistant message updates the *last* block in place.
"""

from __future__ import annotations

import html

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QTextBrowser, QVBoxLayout, QWidget

from jarvis.core.types import Role

_BUBBLE_TEMPLATE = """
<div style="margin:12px 0; padding:12px 14px; border-radius:8px;
            background:{bg}; color:{fg}; border:1px solid {border};">
  <div style="font-size:11px; opacity:0.7; margin-bottom:4px;">{who}{timestamp}</div>
  <div style="white-space:pre-wrap; font-family:inherit;">{content}</div>
</div>
"""

_ROLE_STYLES: dict[str, dict[str, str]] = {
    "user": {"bg": "#0F1A33", "fg": "#DFF6FF", "border": "#12253F", "who": "You"},
    "assistant": {"bg": "#0A1122", "fg": "#DFF6FF", "border": "#00E5FF", "who": "JARVIS"},
    "system": {"bg": "transparent", "fg": "#6D8BAA", "border": "transparent", "who": "System"},
    "tool": {"bg": "#12253F", "fg": "#DFF6FF", "border": "#12253F", "who": "Tool"},
}


class ChatView(QWidget):
    """Displays a conversation. Owned by :class:`MainWindow` (and reused
    by :class:`PrivateTranscriptDialog`, Milestone 5 section 5)."""

    scrolled_to_bottom = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("chatView")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._browser = QTextBrowser(self)
        self._browser.setObjectName("chatBrowser")
        self._browser.setOpenExternalLinks(True)
        self._browser.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addWidget(self._browser)

        # Generic streaming state -- supports streaming *any* role (not
        # just "assistant"), e.g. a live user voice transcript, without
        # every open bubble needing its own bespoke buffer/flag pair.
        self._stream_open: bool = False
        self._stream_role: Role = "assistant"
        self._stream_buffer: str = ""
        self._stream_timestamp: str | None = None

        # Backward-compatible aliases some call sites still poke at directly.
        self._assistant_open = False
        self._assistant_buffer = ""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def clear(self) -> None:
        self._browser.clear()
        self._stream_open = False
        self._stream_buffer = ""
        self._assistant_open = False
        self._assistant_buffer = ""

    def add_message(self, role: Role, content: str, *, timestamp: str | None = None) -> None:
        """Append a fully-formed message bubble."""
        html_block = _render(role, content, timestamp)
        self._browser.append(html_block)
        self._scroll_to_end()

    # ---- Generic streaming (any role) ---------------------------------
    def begin_stream(self, role: Role, *, timestamp: str | None = None) -> None:
        """Start a streaming bubble for ``role`` (assistant reply, live
        user voice transcript, ...)."""
        self._stream_open = True
        self._stream_role = role
        self._stream_buffer = ""
        self._stream_timestamp = timestamp
        self._browser.append(_render(role, "", timestamp))
        self._scroll_to_end()
        if role == "assistant":
            self._assistant_open = True
            self._assistant_buffer = ""

    def append_stream_token(self, token: str) -> None:
        """Append a token to the currently-open streaming bubble."""
        if not self._stream_open:
            self.begin_stream("assistant")
        self._stream_buffer += token
        self._replace_last_bubble(self._stream_role, self._stream_buffer, self._stream_timestamp)
        self._scroll_to_end()
        if self._stream_role == "assistant":
            self._assistant_buffer = self._stream_buffer

    def end_stream(self) -> str:
        """Close the open streaming bubble and return its final text."""
        final_text = self._stream_buffer
        self._stream_open = False
        self._stream_buffer = ""
        self._assistant_open = False
        self._assistant_buffer = ""
        return final_text

    # ---- Assistant-only aliases (kept for existing call sites) --------
    def begin_assistant(self) -> None:
        """Start a streaming assistant bubble."""
        self.begin_stream("assistant")

    def append_token(self, token: str) -> None:
        """Append a token to the currently-open assistant bubble."""
        self.append_stream_token(token)

    def end_assistant(self) -> None:
        self.end_stream()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _replace_last_bubble(self, role: Role, content: str, timestamp: str | None = None) -> None:
        cursor = self._browser.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
        cursor.removeSelectedText()
        cursor.deletePreviousChar()  # remove trailing newline the block leaves behind
        self._browser.append(_render(role, content, timestamp))

    def _scroll_to_end(self) -> None:
        bar = self._browser.verticalScrollBar()
        bar.setValue(bar.maximum())


def _render(role: Role, content: str, timestamp: str | None = None) -> str:
    style = _ROLE_STYLES.get(role, _ROLE_STYLES["assistant"])
    timestamp_html = f"  ·  {html.escape(timestamp)}" if timestamp else ""
    return _BUBBLE_TEMPLATE.format(
        bg=style["bg"],
        fg=style["fg"],
        border=style["border"],
        who=style["who"],
        timestamp=timestamp_html,
        content=html.escape(content).replace("\n", "<br>"),
    )
