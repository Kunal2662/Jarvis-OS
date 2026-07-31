"""Card primitives -- the recurring rounded-corner surface unit seen
throughout the official JARVIS dashboard (schedule, tasks, Gmail,
Spotify, weather, finance, smart-home, quick actions, ...)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class Card(QFrame):
    """A rounded, bordered surface. The base unit for every panel."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.setFrameShape(QFrame.Shape.NoFrame)


class SectionCard(Card):
    """A :class:`Card` with a header row: title (+ optional badge) on the
    left, an optional "View All" / action link on the right."""

    def __init__(
        self,
        title: str,
        parent: QWidget | None = None,
        *,
        action_text: str = "",
        badge_text: str = "",
    ) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 16)
        outer.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(8)
        title_label = QLabel(title)
        title_label.setObjectName("cardTitle")
        header.addWidget(title_label)

        if badge_text:
            badge = QLabel(badge_text)
            badge.setObjectName("cardBadge")
            header.addWidget(badge)

        header.addStretch(1)

        self.action_button: QPushButton | None = None
        if action_text:
            self.action_button = QPushButton(action_text)
            self.action_button.setObjectName("cardAction")
            self.action_button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.action_button.setFlat(True)
            header.addWidget(self.action_button)

        outer.addLayout(header)

        self.body = QVBoxLayout()
        self.body.setSpacing(8)
        outer.addLayout(self.body, 1)


class ServiceCard(Card):
    """Compact card used for the Gmail / Spotify / Weather / Finance /
    Smart Home row: icon glyph + title on top, status text top-right,
    then a custom body the caller fills in via :attr:`body`."""

    def __init__(
        self,
        icon: str,
        title: str,
        status: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 14)
        outer.setSpacing(8)

        header = QHBoxLayout()
        icon_label = QLabel(icon)
        icon_label.setObjectName("serviceIcon")
        header.addWidget(icon_label)
        title_label = QLabel(title)
        title_label.setObjectName("cardTitle")
        header.addWidget(title_label)
        header.addStretch(1)
        if status:
            status_label = QLabel(status)
            status_label.setObjectName("serviceStatus")
            header.addWidget(status_label)
        outer.addLayout(header)

        self.body = QVBoxLayout()
        self.body.setSpacing(6)
        outer.addLayout(self.body, 1)


class StatTile(Card):
    """Small metric tile: label, big value, optional delta chip."""

    def __init__(
        self,
        label: str,
        value: str,
        delta: str = "",
        *,
        positive: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(4)

        self._label_widget = QLabel(label)
        self._label_widget.setObjectName("statLabel")
        outer.addWidget(self._label_widget)

        row = QHBoxLayout()
        self._value_widget = QLabel(value)
        self._value_widget.setObjectName("statValue")
        row.addWidget(self._value_widget)
        row.addStretch(1)
        self._delta_widget: QLabel | None = None
        if delta:
            self._delta_widget = QLabel(delta)
            self._delta_widget.setObjectName(
                "statDeltaPositive" if positive else "statDeltaNegative"
            )
            row.addWidget(self._delta_widget)
        outer.addLayout(row)
        self._delta_row = row

    def set_value(self, value: str, delta: str = "", *, positive: bool = True) -> None:
        """Live-update the tile after an async refresh (workspaces poll
        mock providers and call this instead of rebuilding the tile)."""
        self._value_widget.setText(value)
        if delta:
            if self._delta_widget is None:
                self._delta_widget = QLabel(delta)
                self._delta_row.addWidget(self._delta_widget)
            self._delta_widget.setText(delta)
            self._delta_widget.setObjectName(
                "statDeltaPositive" if positive else "statDeltaNegative"
            )
            self._delta_widget.style().unpolish(self._delta_widget)
            self._delta_widget.style().polish(self._delta_widget)
