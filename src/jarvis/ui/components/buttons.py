"""Buttons -- pill-shaped quick-action buttons and icon+text buttons.

``icon`` is a semantic :mod:`jarvis.ui.components.icons` registry key
(e.g. ``"gmail"``, ``"screenshot"``), not a raw glyph -- rendered as a
real ``QIcon`` via ``QPushButton.setIcon``, not concatenated into the
button's text. Pass ``""`` for a button with no icon.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QPushButton, QWidget

from jarvis.ui.components.icons import icon_registry


class PillButton(QPushButton):
    """Rounded quick-action button, e.g. "Summarize my emails"."""

    def __init__(self, icon: str, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("pillButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if icon:
            self.setIcon(icon_registry.qicon(icon, size=16))
            self.setIconSize(QSize(16, 16))


class IconTextButton(QPushButton):
    """Bigger tile-style button used in the Quick Actions grid."""

    def __init__(self, icon: str, text: str, parent: QWidget | None = None) -> None:
        super().__init__(f"\n{text}" if icon else text, parent)
        self.setObjectName("iconTextButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(64)
        if icon:
            self.setIcon(icon_registry.qicon(icon, size=22))
            self.setIconSize(QSize(22, 22))


class NavItemButton(QPushButton):
    """Sidebar navigation entry -- checkable so exactly one stays "active"."""

    def __init__(self, icon: str, text: str, parent: QWidget | None = None) -> None:
        super().__init__(f"  {text}" if icon else text, parent)
        self.setObjectName("navItem")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if icon:
            self.setIcon(icon_registry.qicon(icon, size=18))
            self.setIconSize(QSize(18, 18))
