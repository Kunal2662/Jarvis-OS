"""Buttons -- pill-shaped quick-action buttons and icon+text buttons."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QWidget


class PillButton(QPushButton):
    """Rounded quick-action button, e.g. "Summarize my emails"."""

    def __init__(self, icon: str, text: str, parent: QWidget | None = None) -> None:
        super().__init__(f"{icon}  {text}" if icon else text, parent)
        self.setObjectName("pillButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)


class IconTextButton(QPushButton):
    """Bigger tile-style button used in the Quick Actions grid."""

    def __init__(self, icon: str, text: str, parent: QWidget | None = None) -> None:
        super().__init__(f"{icon}\n{text}", parent)
        self.setObjectName("iconTextButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(64)


class NavItemButton(QPushButton):
    """Sidebar navigation entry -- checkable so exactly one stays "active"."""

    def __init__(self, icon: str, text: str, parent: QWidget | None = None) -> None:
        super().__init__(f"{icon}   {text}", parent)
        self.setObjectName("navItem")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
