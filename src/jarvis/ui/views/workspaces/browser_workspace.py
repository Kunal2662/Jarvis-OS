"""Browser workspace -- browser-automation console (Milestone 5,
section 1). Natural-language browser automation already works via the
existing automation engine; this gives it a dedicated dashboard: recent
sessions, open tabs snapshot, and quick automation shortcuts. Mock data
only -- no real browser is driven from this view.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtWidgets import QVBoxLayout, QWidget

from jarvis.ui.components import (
    ActivityFeed,
    CardGrid,
    QuickActionsRow,
    ScrollableColumn,
    SectionCard,
    SimpleListPanel,
    StatTile,
    WorkspaceHeader,
)

_MOCK_TABS = [
    ("GitHub — jarvis-os/2.0", "github.com", "Active"),
    ("Gmail Inbox", "mail.google.com", "Idle"),
    ("Amazon — Cart (3 items)", "amazon.in", "Idle"),
]


class BrowserWorkspace(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollableColumn()
        outer.addWidget(scroll)
        column = scroll.column

        header = WorkspaceHeader(
            "Browser",
            subtitle="Natural-language browser automation console.",
            status_text="Idle",
            status_state="neutral",
            search_placeholder="Search browsing history…",
        )
        header.add_tool_button("New Automation", icon="add")
        column.addWidget(header)

        stats = CardGrid(columns=4)
        stats.add_card(StatTile("Open Tabs", str(len(_MOCK_TABS))))
        stats.add_card(StatTile("Automations Today", "6"))
        stats.add_card(StatTile("Success Rate", "94%", "+2%", positive=True))
        stats.add_card(StatTile("Avg Duration", "3.2s"))
        column.addWidget(stats)

        tabs_card = SectionCard("Open Tabs")
        tabs_list = SimpleListPanel()
        for title, url, state in _MOCK_TABS:
            tabs_list.add_row(title, url, state)
        tabs_card.body.addWidget(tabs_list)
        column.addWidget(tabs_card)

        activity = ActivityFeed("Recent Automation Runs")
        activity.set_items(
            [
                (
                    "browser",
                    "Filled checkout form on amazon.in",
                    (datetime.now() - timedelta(minutes=8)).strftime("%H:%M"),
                ),
                (
                    "search",
                    'Searched "PySide6 QDockWidget" on Google',
                    (datetime.now() - timedelta(minutes=35)).strftime("%H:%M"),
                ),
                (
                    "gmail",
                    "Opened Gmail and archived 4 emails",
                    (datetime.now() - timedelta(hours=1)).strftime("%H:%M"),
                ),
            ]
        )
        column.addWidget(activity)

        actions = QuickActionsRow(
            [
                ("new_tab", "add", "New Tab"),
                ("run_automation", "play", "Run Automation"),
                ("clear_history", "delete", "Clear History"),
            ]
        )
        column.addWidget(actions)
        column.addStretch(1)
