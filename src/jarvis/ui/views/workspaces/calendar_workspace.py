"""Calendar workspace -- future integration interface for calendar sync
(Milestone 5, section 1). Mock schedule data only; the shape here is
what an ``ICalendarProvider`` (a natural sibling to the section-11
interfaces) would eventually back.
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

_MOCK_EVENTS = [
    ("09:00", "Standup — Engineering", "15 min · Google Meet"),
    ("10:00", "Project Review Meeting", "1 hr · Conference Room B"),
    ("13:00", "Lunch with Sarah", "1 hr · The Grind Café"),
    ("15:30", "1:1 with Manager", "30 min · Zoom"),
    ("16:00", "Gym Session", "1 hr"),
]


class CalendarWorkspace(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollableColumn()
        outer.addWidget(scroll)
        column = scroll.column

        header = WorkspaceHeader(
            "Calendar",
            subtitle=datetime.now().strftime("%A, %B %d, %Y"),
            status_text="Synced",
            status_state="success",
            search_placeholder="Search events…",
        )
        header.add_tool_button("New Event", icon="＋")
        header.add_tool_button("Today", icon="📅")
        column.addWidget(header)

        stats = CardGrid(columns=4)
        stats.add_card(StatTile("Today's Events", str(len(_MOCK_EVENTS))))
        stats.add_card(StatTile("This Week", "17"))
        stats.add_card(StatTile("Conflicts", "0", "0", positive=True))
        stats.add_card(StatTile("Next Up", "Standup · 9:00"))
        column.addWidget(stats)

        today = SectionCard("Today's Schedule", action_text="View Week")
        today_list = SimpleListPanel()
        for time, title, detail in _MOCK_EVENTS:
            today_list.add_row(title, detail, time)
        today.body.addWidget(today_list)
        column.addWidget(today)

        activity = ActivityFeed("Recent Calendar Activity")
        activity.set_items(
            [
                (
                    "📅",
                    'Added "Project Review Meeting"',
                    (datetime.now() - timedelta(minutes=40)).strftime("%H:%M"),
                ),
                (
                    "✏",
                    'Rescheduled "1:1 with Manager" to 15:30',
                    (datetime.now() - timedelta(hours=2)).strftime("%H:%M"),
                ),
                (
                    "🗑",
                    'Cancelled "Vendor Sync"',
                    (datetime.now() - timedelta(hours=5)).strftime("%H:%M"),
                ),
            ]
        )
        column.addWidget(activity)

        actions = QuickActionsRow(
            [
                ("new_event", "＋", "New Event"),
                ("sync", "⟳", "Sync Now"),
                ("connect", "🔗", "Connect Calendar"),
            ]
        )
        column.addWidget(actions)
        column.addStretch(1)
