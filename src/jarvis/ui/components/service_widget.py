"""``ServiceWidget`` -- the production-quality replacement for the
placeholder Gmail / Spotify / Weather / Finance / Smart Home cards on
the Home dashboard (Milestone 5, section 2).

Every widget shows: a connection indicator + status badge, a one-line
summary, a compact recent-activity list, a last-sync timestamp, quick
action buttons, and swaps to a loading spinner or an inline error +
retry state while its (mock, for now) provider is fetched. The refresh
callback is injected (``on_refresh``), so hooking a real
``IGmailProvider`` etc. adapter up later is a constructor-argument
change only -- this widget never imports a concrete provider.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from jarvis.ui.async_utils import fire_and_forget
from jarvis.ui.components.card import ServiceCard

RefreshResult = dict[str, Any]
RefreshCallback = Callable[[], Awaitable[RefreshResult]]


class ServiceWidget(ServiceCard):
    """``on_refresh`` must return a dict shaped like::

    {
        "connected": bool,
        "summary": str,
        "activity": [(icon, text, when_text), ...],   # up to ~3
        "quick_actions": [(action_id, icon, label), ...],
        "last_sync": datetime | None,
    }
    """

    def __init__(
        self,
        icon: str,
        title: str,
        *,
        on_refresh: RefreshCallback,
        on_action: Callable[[str], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(icon, title, parent=parent)
        self._on_refresh = on_refresh
        self._on_action = on_action

        # Connection indicator, replacing the plain status text with a
        # dot + badge combo.
        self._indicator = QLabel("●")
        self._indicator.setObjectName("connectionIndicatorUnknown")

        self._summary_label = QLabel("Loading…")
        self._summary_label.setObjectName("rowSubtitle")
        self._summary_label.setWordWrap(True)
        self.body.addWidget(self._summary_label)

        self._activity_container = QVBoxLayout()
        self._activity_container.setSpacing(4)
        self.body.addLayout(self._activity_container)

        self._sync_label = QLabel("Last sync: —")
        self._sync_label.setObjectName("rowTrailing")
        self.body.addWidget(self._sync_label)

        self._actions_row = QHBoxLayout()
        self._actions_row.setSpacing(6)
        self.body.addLayout(self._actions_row)

        self._error_label = QLabel()
        self._error_label.setObjectName("serviceErrorText")
        self._error_label.setWordWrap(True)
        self._error_label.setVisible(False)
        self._retry_button = QPushButton("Retry")
        self._retry_button.setObjectName("cardAction")
        self._retry_button.setFlat(True)
        self._retry_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._retry_button.setVisible(False)
        self._retry_button.clicked.connect(lambda: fire_and_forget(self.refresh()))
        self.body.addWidget(self._error_label)
        self.body.addWidget(self._retry_button)

        fire_and_forget(self.refresh())

    # ------------------------------------------------------------------
    async def refresh(self) -> None:
        self._set_loading(True)
        try:
            data = await self._on_refresh()
        except Exception as err:
            self._show_error(str(err))
            return
        self._set_loading(False)
        self._render(data)

    # ------------------------------------------------------------------
    def _set_loading(self, loading: bool) -> None:
        self._error_label.setVisible(False)
        self._retry_button.setVisible(False)
        if loading:
            self._summary_label.setText("Loading…")
            self._indicator.setObjectName("connectionIndicatorUnknown")

    def _show_error(self, message: str) -> None:
        self._summary_label.setText("")
        self._error_label.setText(f"⚠ Couldn't refresh: {message}")
        self._error_label.setVisible(True)
        self._retry_button.setVisible(True)
        self._indicator.setObjectName("connectionIndicatorOffline")

    def _render(self, data: RefreshResult) -> None:
        connected = bool(data.get("connected", True))
        self._indicator.setObjectName(
            "connectionIndicatorOnline" if connected else "connectionIndicatorOffline"
        )
        self._summary_label.setText(str(data.get("summary", "")))

        while self._activity_container.count():
            item = self._activity_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for icon, text, when in data.get("activity", [])[:3]:
            row = QHBoxLayout()
            row.setSpacing(6)
            glyph = QLabel(icon)
            glyph.setFixedWidth(16)
            row.addWidget(glyph)
            text_label = QLabel(text)
            text_label.setObjectName("rowSubtitle")
            text_label.setWordWrap(True)
            row.addWidget(text_label, 1)
            when_label = QLabel(when)
            when_label.setObjectName("rowTrailing")
            row.addWidget(when_label)
            self._activity_container.addLayout(row)

        last_sync = data.get("last_sync")
        if isinstance(last_sync, datetime):
            self._sync_label.setText(f"Last sync: {last_sync.strftime('%H:%M')}")
        else:
            self._sync_label.setText("Last sync: —")

        while self._actions_row.count():
            item = self._actions_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for action_id, icon, label in data.get("quick_actions", []):
            button = QPushButton(f"{icon} {label}".strip())
            button.setObjectName("pillButtonSmall")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _c=False, a=action_id: self._handle_action(a))
            self._actions_row.addWidget(button)
        self._actions_row.addStretch(1)

    def _handle_action(self, action_id: str) -> None:
        if self._on_action is not None:
            self._on_action(action_id)
