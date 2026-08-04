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
from jarvis.ui.components.icons import Icon, icon_or_literal, icon_registry

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
        "preview": bool,   # optional; see below
    }

    ``preview`` marks a card whose data comes from a stand-in rather
    than a connected service (Aug 2026 final backlog pass). The Gmail /
    Spotify / Weather / Finance / Smart Home providers are all still
    stand-ins -- their real adapters are M11 and M12 -- and before this
    flag existed those cards rendered a green "online" indicator over
    invented figures, which read as a genuine reading of the user's
    inbox, music and local weather.

    A preview card forces the offline indicator and shows a visible
    note, so the illustrative data stays (it is what M5 shipped, and
    what proves the widget works) without the card claiming to be
    connected to anything.
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

        self._preview_label = QLabel("Preview — no integration connected yet")
        self._preview_label.setObjectName("rowSubtitle")
        self._preview_label.setWordWrap(True)
        self._preview_label.setVisible(False)
        self.body.addWidget(self._preview_label)

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

        self._error_row = QWidget()
        error_row_layout = QHBoxLayout(self._error_row)
        error_row_layout.setContentsMargins(0, 0, 0, 0)
        error_row_layout.setSpacing(6)
        self._error_icon = Icon("warning", size=14)
        error_row_layout.addWidget(self._error_icon)
        self._error_label = QLabel()
        self._error_label.setObjectName("serviceErrorText")
        self._error_label.setWordWrap(True)
        error_row_layout.addWidget(self._error_label, 1)
        self._error_row.setVisible(False)
        self._retry_button = QPushButton("Retry")
        self._retry_button.setObjectName("cardAction")
        self._retry_button.setFlat(True)
        self._retry_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._retry_button.setVisible(False)
        self._retry_button.clicked.connect(lambda: fire_and_forget(self.refresh()))
        self.body.addWidget(self._error_row)
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
        self._error_row.setVisible(False)
        self._retry_button.setVisible(False)
        if loading:
            self._summary_label.setText("Loading…")
            self._indicator.setObjectName("connectionIndicatorUnknown")

    def _show_error(self, message: str) -> None:
        self._summary_label.setText("")
        self._error_label.setText(f"Couldn't refresh: {message}")
        self._error_row.setVisible(True)
        self._retry_button.setVisible(True)
        self._indicator.setObjectName("connectionIndicatorOffline")

    def _render(self, data: RefreshResult) -> None:
        preview = bool(data.get("preview", False))
        # A preview card is not connected to anything, whatever its
        # payload claims -- the indicator must never say otherwise.
        connected = bool(data.get("connected", True)) and not preview
        self._indicator.setObjectName(
            "connectionIndicatorOnline" if connected else "connectionIndicatorOffline"
        )
        self._preview_label.setVisible(preview)
        self._summary_label.setText(str(data.get("summary", "")))

        while self._activity_container.count():
            item = self._activity_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for icon, text, when in data.get("activity", [])[:3]:
            row = QHBoxLayout()
            row.setSpacing(6)
            # `icon` is a semantic icon_registry key for activity rows
            # this widget itself defines; mock-provider-sourced activity
            # (see features/integrations/mocks.py, intentionally left
            # untouched) still supplies a raw glyph -- icon_or_literal
            # renders whichever this is correctly either way.
            row.addWidget(icon_or_literal(icon, size=16))
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
            button = QPushButton(label)
            button.setObjectName("pillButtonSmall")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            if icon:
                button.setIcon(icon_registry.qicon(icon, size=14))
            button.clicked.connect(lambda _c=False, a=action_id: self._handle_action(a))
            self._actions_row.addWidget(button)
        self._actions_row.addStretch(1)

    def _handle_action(self, action_id: str) -> None:
        if self._on_action is not None:
            self._on_action(action_id)
