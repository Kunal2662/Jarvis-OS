"""System tray icon + quick-access menu (Milestone 5, 'Minimized to
System Tray' in the official UI).

Menu order matches the reference image exactly: Open Jarvis, Voice Mode,
Private Transcript (lock glyph), Quick Commands, Smart Home, Recent
Notifications, Settings, Exit Jarvis.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction, QIcon, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from jarvis.ui.components.icons import icon_registry

if TYPE_CHECKING:
    from PySide6.QtWidgets import QMainWindow


def _fallback_icon() -> QIcon:
    """Solid cyan square — placeholder until real branding lands."""
    pix = QPixmap(64, 64)
    pix.fill(0xFF00E5FF)  # ARGB
    return QIcon(pix)


class SystemTrayIcon(QSystemTrayIcon):
    show_requested = Signal()
    hide_requested = Signal()
    quit_requested = Signal()
    toggle_requested = Signal()
    voice_mode_requested = Signal()
    private_transcript_requested = Signal()
    quick_commands_requested = Signal()
    smart_home_requested = Signal()
    settings_requested = Signal()

    def __init__(self, window: QMainWindow) -> None:
        super().__init__(_fallback_icon(), window)
        self.setToolTip("JARVIS OS — running in the background")

        menu = QMenu(window)

        open_action = QAction("Open Jarvis", menu)
        open_action.triggered.connect(self.show_requested)
        menu.addAction(open_action)

        voice_action = QAction("Voice Mode", menu)
        voice_action.triggered.connect(self.voice_mode_requested)
        menu.addAction(voice_action)

        transcript_action = QAction(
            icon_registry.qicon("lock", size=16), "Private Transcript", menu
        )
        transcript_action.triggered.connect(self.private_transcript_requested)
        menu.addAction(transcript_action)

        commands_action = QAction("Quick Commands", menu)
        commands_action.triggered.connect(self.quick_commands_requested)
        menu.addAction(commands_action)

        smart_home_action = QAction("Smart Home", menu)
        smart_home_action.triggered.connect(self.smart_home_requested)
        menu.addAction(smart_home_action)

        notifications_action = QAction("Recent Notifications", menu)
        notifications_action.setEnabled(False)  # no real notification feed yet
        menu.addAction(notifications_action)

        menu.addSeparator()

        settings_action = QAction("Settings", menu)
        settings_action.triggered.connect(self.settings_requested)
        menu.addAction(settings_action)

        menu.addSeparator()
        quit_act = QAction("Exit Jarvis", menu)
        quit_act.triggered.connect(self.quit_requested)
        menu.addAction(quit_act)

        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.toggle_requested.emit()
