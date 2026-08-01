"""Workspace scaffold -- the shared shell every full-screen desktop
workspace (Voice, Browser, Files & Drive, Coding, Finance, Smart Home,
Gmail, Spotify, Calendar) is built from (Milestone 5, section 1).

Every workspace follows the same anatomy so they read as one product
instead of nine bolted-on screens: a ``WorkspaceHeader`` (title, live
status badge, search box, toolbar buttons), a body that swaps between
``LoadingState`` / ``EmptyState`` / ``ErrorState`` / real content via
``WorkspaceStateStack``, and optional ``ActivityFeed`` / ``QuickActions``
strips reused across screens. All content in concrete workspaces is
realistic mock data -- no real API calls are made from this layer.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from jarvis.ui.components.badges import StatusBadge
from jarvis.ui.components.buttons import PillButton
from jarvis.ui.components.card import SectionCard
from jarvis.ui.components.icons import Icon, icon_or_literal


class WorkspaceHeader(QWidget):
    """Title + connection/status badge + search + toolbar row, identical
    shape across every workspace."""

    search_changed = Signal(str)

    def __init__(
        self,
        title: str,
        *,
        subtitle: str = "",
        status_text: str = "Connected",
        status_state: str = "success",
        search_placeholder: str = "Search…",
        show_search: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)

        top = QHBoxLayout()
        title_label = QLabel(title)
        title_label.setObjectName("greetingTitle")
        top.addWidget(title_label)

        self.status_badge = StatusBadge(status_text, status_state)
        top.addWidget(self.status_badge)
        top.addStretch(1)

        self.toolbar = QHBoxLayout()
        self.toolbar.setSpacing(8)
        top.addLayout(self.toolbar)
        outer.addLayout(top)

        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("rowSubtitle")
            outer.addWidget(sub)

        if show_search:
            search_row = QHBoxLayout()
            self.search_box = QLineEdit()
            self.search_box.setObjectName("workspaceSearch")
            self.search_box.setPlaceholderText(search_placeholder)
            self.search_box.textChanged.connect(self.search_changed)
            search_row.addWidget(self.search_box)
            outer.addLayout(search_row)
        else:
            self.search_box = None

    def add_tool_button(self, text: str, *, icon: str = "") -> QPushButton:
        button = PillButton(icon, text)
        self.toolbar.addWidget(button)
        return button

    def set_status(self, text: str, state: str) -> None:
        self.status_badge.set_state(state, text)


class _CenteredMessageState(QWidget):
    def __init__(
        self,
        glyph_key: str,
        title: str,
        message: str,
        object_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName(object_name)
        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.setSpacing(6)

        glyph_row = QHBoxLayout()
        glyph_row.addStretch(1)
        glyph_row.addWidget(Icon(glyph_key, size=24))
        glyph_row.addStretch(1)
        outer.addLayout(glyph_row)

        title_label = QLabel(title)
        title_label.setObjectName("cardTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(title_label)

        message_label = QLabel(message)
        message_label.setObjectName("rowSubtitle")
        message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        message_label.setWordWrap(True)
        outer.addWidget(message_label)

        self.action_button: QPushButton | None = None


class LoadingState(_CenteredMessageState):
    def __init__(self, message: str = "Loading…", parent: QWidget | None = None) -> None:
        super().__init__("loading", "Loading", message, "workspaceLoadingState", parent)


class EmptyState(_CenteredMessageState):
    action_clicked = Signal()

    def __init__(
        self,
        title: str = "Nothing here yet",
        message: str = "",
        *,
        action_text: str = "",
        glyph: str = "offline",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(glyph, title, message, "workspaceEmptyState", parent)
        if action_text:
            self.action_button = PillButton("", action_text)
            self.action_button.clicked.connect(self.action_clicked)
            self.layout().addWidget(self.action_button, 0, Qt.AlignmentFlag.AlignCenter)


class ErrorState(_CenteredMessageState):
    retry_clicked = Signal()

    def __init__(
        self,
        title: str = "Something went wrong",
        message: str = "That request failed. This is mock data, so nothing was actually lost.",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("warning", title, message, "workspaceErrorState", parent)
        self.action_button = PillButton("", "Retry")
        self.action_button.clicked.connect(self.retry_clicked)
        self.layout().addWidget(self.action_button, 0, Qt.AlignmentFlag.AlignCenter)


class WorkspaceStateStack(QStackedWidget):
    """Swaps between loading / empty / error / real content, the same
    four states every workspace and service card must support."""

    def __init__(
        self, content: QWidget, *, empty: EmptyState | None = None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.content = content
        self.loading = LoadingState()
        self.empty = empty or EmptyState()
        self.error = ErrorState()
        self._index = {
            "loading": self.addWidget(self.loading),
            "empty": self.addWidget(self.empty),
            "error": self.addWidget(self.error),
            "content": self.addWidget(content),
        }
        self.error.retry_clicked.connect(lambda: self.show_state("loading"))
        self.show_state("content")

    def show_state(self, state: str) -> None:
        self.setCurrentIndex(self._index[state])


class ActivityFeed(SectionCard):
    """Reverse-chronological activity list -- reused by every workspace's
    'Recent Activity' section and by service-card widgets."""

    def __init__(self, title: str = "Activity Feed", parent: QWidget | None = None) -> None:
        super().__init__(title, parent)
        self._container = QVBoxLayout()
        self._container.setSpacing(6)
        self.body.addLayout(self._container)
        self._empty_label = QLabel("No recent activity.")
        self._empty_label.setObjectName("rowSubtitle")
        self.body.addWidget(self._empty_label)

    def clear(self) -> None:
        while self._container.count():
            item = self._container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def set_items(self, items: list[tuple[str, str, str]]) -> None:
        """items: list of (icon key or literal glyph, text, timestamp_text)."""
        self.clear()
        self._empty_label.setVisible(not items)
        for glyph, text, when in items:
            row = QHBoxLayout()
            row.setSpacing(8)
            row.addWidget(icon_or_literal(glyph, size=20))
            text_label = QLabel(text)
            text_label.setObjectName("rowTitle")
            text_label.setWordWrap(True)
            row.addWidget(text_label, 1)
            when_label = QLabel(when)
            when_label.setObjectName("rowTrailing")
            row.addWidget(when_label)
            self._container.addLayout(row)

    def add_item(self, glyph: str, text: str, when: datetime | None = None) -> None:
        when = when or datetime.now()
        self._empty_label.setVisible(False)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(icon_or_literal(glyph, size=20))
        text_label = QLabel(text)
        text_label.setObjectName("rowTitle")
        row.addWidget(text_label, 1)
        row.addWidget(QLabel(when.strftime("%H:%M")))
        self._container.insertLayout(0, row)


class QuickActionsRow(QWidget):
    """A row of pill buttons -- 'Compose', 'Refresh', 'Play', etc."""

    action_triggered = Signal(str)

    def __init__(self, actions: list[tuple[str, str, str]], parent: QWidget | None = None) -> None:
        """actions: list of (action_id, icon, label)."""
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        for action_id, icon, label in actions:
            button = PillButton(icon, label)
            button.clicked.connect(lambda _c=False, a=action_id: self.action_triggered.emit(a))
            layout.addWidget(button)
        layout.addStretch(1)


class CardGrid(QWidget):
    """Responsive-ish N-column grid of dashboard cards/stat tiles."""

    def __init__(self, columns: int = 3, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._columns = max(1, columns)
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(12)
        self._count = 0

    def add_card(self, widget: QWidget) -> None:
        row, col = divmod(self._count, self._columns)
        self._grid.addWidget(widget, row, col)
        self._count += 1

    def clear(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._count = 0


class Toolbar(QFrame):
    """Slim horizontal action bar under the header (Files & Drive,
    Coding workspace, etc.)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("workspaceToolbar")
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(10, 6, 10, 6)
        self._layout.setSpacing(6)
        self._layout.addStretch(1)

    def add_button(self, text: str, *, icon: str = "") -> QPushButton:
        button = PillButton(icon, text)
        self._layout.insertWidget(self._layout.count() - 1, button)
        return button


class ScrollableColumn(QScrollArea):
    """A vertically scrollable column -- the outer container most
    workspaces wrap their content in so long pages don't blow out the
    window (also the entry point for future virtualization, see
    ``ui/components/virtual_list.py``)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        self.setWidget(inner)
        self.column = QVBoxLayout(inner)
        self.column.setContentsMargins(20, 20, 20, 20)
        self.column.setSpacing(16)
        inner.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
