"""Coding workspace -- coding-assistant console (Milestone 5, section
1). Mock project/activity data only; no real code execution happens
from this view (the Developer Console already covers real automation
commands).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtWidgets import QVBoxLayout, QWidget

from jarvis.ui.components import (
    ActivityFeed,
    CardGrid,
    MiniBarChart,
    QuickActionsRow,
    ScrollableColumn,
    SectionCard,
    SimpleTable,
    StatTile,
    WorkspaceHeader,
)

_MOCK_PROJECTS = [
    ["jarvis-os", "Python", "2.0-main", "12 min ago"],
    ["portfolio-site", "TypeScript", "main", "Yesterday"],
    ["automation-scripts", "Python", "main", "3 days ago"],
]


class CodingWorkspace(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollableColumn()
        outer.addWidget(scroll)
        column = scroll.column

        header = WorkspaceHeader(
            "Coding",
            subtitle="Recent projects, commit activity, and quick scaffolds.",
            status_text="Idle",
            status_state="neutral",
            search_placeholder="Search projects…",
        )
        header.add_tool_button("New Project", icon="add")
        column.addWidget(header)

        stats = CardGrid(columns=4)
        stats.add_card(StatTile("Active Projects", str(len(_MOCK_PROJECTS))))
        stats.add_card(StatTile("Commits This Week", "27", "+9", positive=True))
        stats.add_card(StatTile("Open PRs", "3"))
        stats.add_card(StatTile("CI Status", "Passing"))
        column.addWidget(stats)

        chart_card = SectionCard("Commits (Last 7 Days)")
        chart = MiniBarChart([4, 7, 2, 9, 5, 0, 6])
        chart_card.body.addWidget(chart)
        column.addWidget(chart_card)

        projects_card = SectionCard("Recent Projects")
        table = SimpleTable(["Project", "Language", "Branch", "Last Commit"])
        table.set_rows(_MOCK_PROJECTS)
        projects_card.body.addWidget(table)
        column.addWidget(projects_card)

        activity = ActivityFeed("Recent Activity")
        activity.set_items(
            [
                (
                    "commit",
                    "CI passed on jarvis-os @ 8f3a1c",
                    (datetime.now() - timedelta(minutes=12)).strftime("%H:%M"),
                ),
                (
                    "merge",
                    'Opened PR #142: "Milestone 5 completion pass"',
                    (datetime.now() - timedelta(hours=1)).strftime("%H:%M"),
                ),
                (
                    "bug",
                    "Fixed lint warning in update_service.py",
                    (datetime.now() - timedelta(hours=4)).strftime("%H:%M"),
                ),
            ]
        )
        column.addWidget(activity)

        actions = QuickActionsRow(
            [
                ("new_project", "add", "New Project"),
                ("open_terminal", "terminal", "Open Terminal"),
                ("run_tests", "play", "Run Tests"),
            ]
        )
        column.addWidget(actions)
        column.addStretch(1)
