"""Files & Drive workspace -- local + cloud file browser (Milestone 5,
section 1). Mock file listing only; no real filesystem/Drive access is
performed from this view.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtWidgets import QVBoxLayout, QWidget

from jarvis.ui.components import (
    ActivityFeed,
    CardGrid,
    EmptyState,
    QuickActionsRow,
    ScrollableColumn,
    SectionCard,
    SimpleTable,
    StatTile,
    Toolbar,
    WorkspaceHeader,
    WorkspaceStateStack,
)

_MOCK_FILES = [
    ["Q3 Roadmap.docx", "Word Document", "1.2 MB", "2 hours ago"],
    ["Architecture Diagram.png", "Image", "840 KB", "Yesterday"],
    ["milestone5-delivery.pdf", "PDF", "310 KB", "Yesterday"],
    ["Budget 2026.xlsx", "Spreadsheet", "220 KB", "3 days ago"],
    ["Meeting Notes.md", "Markdown", "12 KB", "5 days ago"],
    ["project-backup.zip", "Archive", "48.6 MB", "1 week ago"],
]


class FilesWorkspace(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollableColumn()
        outer.addWidget(scroll)
        column = scroll.column

        self._header = WorkspaceHeader(
            "Files & Drive",
            subtitle="Local storage + connected cloud drives.",
            status_text="Synced",
            status_state="success",
            search_placeholder="Search files…",
        )
        self._header.search_changed.connect(self._on_search)
        column.addWidget(self._header)

        toolbar = Toolbar()
        toolbar.add_button("Upload", icon="⬆")
        toolbar.add_button("New Folder", icon="📁")
        toolbar.add_button("Connect Drive", icon="🔗")
        column.addWidget(toolbar)

        stats = CardGrid(columns=3)
        stats.add_card(StatTile("Total Files", str(len(_MOCK_FILES))))
        stats.add_card(StatTile("Storage Used", "2.4 GB / 15 GB"))
        stats.add_card(StatTile("Connected Drives", "1 (Local)"))
        column.addWidget(stats)

        files_card = SectionCard("All Files")
        self._table = SimpleTable(["Name", "Type", "Size", "Modified"])
        empty = EmptyState("No files found", "Try a different search term.", glyph="📁")
        self._state_stack = WorkspaceStateStack(self._table, empty=empty)
        files_card.body.addWidget(self._state_stack)
        column.addWidget(files_card)

        activity = ActivityFeed("Recent File Activity")
        activity.set_items(
            [
                (
                    "⬆",
                    'Uploaded "Q3 Roadmap.docx"',
                    (datetime.now() - timedelta(hours=2)).strftime("%H:%M"),
                ),
                (
                    "✏",
                    'Edited "Meeting Notes.md"',
                    (datetime.now() - timedelta(days=5)).strftime("%H:%M"),
                ),
                (
                    "🔗",
                    "Connected Google Drive",
                    (datetime.now() - timedelta(days=6)).strftime("%H:%M"),
                ),
            ]
        )
        column.addWidget(activity)

        actions = QuickActionsRow(
            [
                ("upload", "⬆", "Upload"),
                ("new_folder", "📁", "New Folder"),
                ("connect_drive", "🔗", "Connect Drive"),
            ]
        )
        column.addWidget(actions)
        column.addStretch(1)

        self._render(_MOCK_FILES)

    def _render(self, rows: list[list[str]]) -> None:
        if not rows:
            self._state_stack.show_state("empty")
            return
        self._table.set_rows(rows)
        self._state_stack.show_state("content")

    def _on_search(self, text: str) -> None:
        text = text.lower().strip()
        if not text:
            self._render(_MOCK_FILES)
            return
        self._render([row for row in _MOCK_FILES if text in row[0].lower()])
