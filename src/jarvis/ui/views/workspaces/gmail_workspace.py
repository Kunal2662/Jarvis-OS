"""Gmail workspace -- full-screen inbox view backed by
``MockGmailProvider`` (Milestone 5, section 1 + future integration
interface from section 11: ``IGmailProvider``).
"""

from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget

from jarvis.features.integrations.mocks import MockGmailProvider
from jarvis.ui.async_utils import fire_and_forget
from jarvis.ui.components import (
    ActivityFeed,
    CardGrid,
    EmptyState,
    QuickActionsRow,
    ScrollableColumn,
    SectionCard,
    StatTile,
    VirtualTable,
    WorkspaceHeader,
    WorkspaceStateStack,
)


class GmailWorkspace(QWidget):
    def __init__(
        self, provider: MockGmailProvider | None = None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._provider = provider or MockGmailProvider()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollableColumn()
        outer.addWidget(scroll)
        column = scroll.column

        self._header = WorkspaceHeader(
            "Gmail",
            subtitle="mock@gmail.com",
            status_text="Connected",
            status_state="success",
            search_placeholder="Search mail…",
        )
        self._header.add_tool_button("Compose", icon="✎")
        self._header.add_tool_button("Refresh", icon="⟳").clicked.connect(
            lambda: fire_and_forget(self._load())
        )
        self._header.search_changed.connect(self._on_search)
        column.addWidget(self._header)

        self._stats = CardGrid(columns=3)
        self._unread_tile = StatTile("Unread", "—")
        self._total_tile = StatTile("Inbox", "—")
        self._sync_tile = StatTile("Last Sync", "—")
        for tile in (self._unread_tile, self._total_tile, self._sync_tile):
            self._stats.add_card(tile)
        column.addWidget(self._stats)

        inbox_card = SectionCard("Inbox")
        self._table = VirtualTable(["From", "Subject", "Preview", "Received"])
        empty = EmptyState("No messages", "Nothing matches your search.", glyph="✉")
        self._state_stack = WorkspaceStateStack(self._table, empty=empty)
        inbox_card.body.addWidget(self._state_stack)
        column.addWidget(inbox_card)

        self._activity = ActivityFeed("Recent Activity")
        column.addWidget(self._activity)

        actions = QuickActionsRow(
            [
                ("compose", "✎", "Compose"),
                ("mark_all_read", "✓", "Mark All Read"),
                ("connect", "🔗", "Connect Real Account"),
            ]
        )
        column.addWidget(actions)
        column.addStretch(1)

        self._all_rows: list[dict] = []
        fire_and_forget(self._load())

    async def _load(self) -> None:
        self._state_stack.show_state("loading")
        try:
            status = await self._provider.get_connection_status()
            unread = await self._provider.get_unread_count()
            messages = await self._provider.list_recent_messages(20)
            activity = await self._provider.get_recent_activity(6)
        except Exception:
            self._state_stack.show_state("error")
            return

        self._header.set_status(
            "Connected" if status.connected else "Disconnected",
            "success" if status.connected else "danger",
        )
        self._unread_tile.set_value(str(unread))
        self._total_tile.set_value(str(len(messages)))
        self._sync_tile.set_value(status.last_sync.strftime("%H:%M") if status.last_sync else "—")
        self._all_rows = messages
        self._render_table(messages)
        self._activity.set_items(
            [(a.icon, a.text, a.timestamp.strftime("%H:%M")) for a in activity]
        )

    def _render_table(self, messages: list[dict]) -> None:
        if not messages:
            self._state_stack.show_state("empty")
            return
        rows = [
            [m["from"], m["subject"], m["snippet"], f"{m['minutes_ago']}m ago"] for m in messages
        ]
        self._table.set_rows(rows)
        self._state_stack.show_state("content")

    def _on_search(self, text: str) -> None:
        text = text.lower().strip()
        if not text:
            self._render_table(self._all_rows)
            return
        filtered = [
            m
            for m in self._all_rows
            if text in m["from"].lower()
            or text in m["subject"].lower()
            or text in m["snippet"].lower()
        ]
        self._render_table(filtered)
