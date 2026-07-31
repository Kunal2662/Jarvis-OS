"""Sidebar -- primary navigation for the official JARVIS dashboard (Milestone 5).

Matches the reference UI's left rail: brand header, a flat list of nav
items (Home, Chat, Voice, Memory, Automations, Files & Drive, Browser,
Coding, Finance, Smart Home, Calendar, Gmail, Spotify, Settings), and a
user profile row at the bottom. Exactly one nav item is checked at a
time (QButtonGroup), mirroring the reference image's active-item
highlight.

The per-conversation history list that used to live here in Milestone 2
now lives inside the Chat page itself (see ``ui/widgets/chat_page.py``)
so the sidebar stays exactly as clean as the official UI -- this widget
only ever shows the 14 fixed nav entries plus the profile row.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from jarvis.ui.components.buttons import NavItemButton
from jarvis.ui.components.icons import icon_registry

# (id, icon key, label) -- order matches the official UI exactly. The
# glyph shown is resolved through ``icon_registry`` (Milestone 5,
# section 3) so every nav icon is replaceable from one central place
# instead of being a literal emoji scattered through this file.
_NAV_KEYS: list[tuple[str, str]] = [
    ("home", "Home"),
    ("chat", "Chat"),
    ("voice", "Voice"),
    ("memory", "Memory"),
    ("automations", "Automations"),
    ("files", "Files & Drive"),
    ("browser", "Browser"),
    ("coding", "Coding"),
    ("finance", "Finance"),
    ("smart_home", "Smart Home"),
    ("calendar", "Calendar"),
    ("gmail", "Gmail"),
    ("spotify", "Spotify"),
    ("settings", "Settings"),
]
NAV_ITEMS: list[tuple[str, str, str]] = [
    (item_id, icon_registry.glyph(item_id), label) for item_id, label in _NAV_KEYS
]


class Sidebar(QWidget):
    nav_selected = Signal(str)  # one of NAV_ITEMS ids
    new_conversation_requested = Signal()
    conversation_selected = Signal(str)
    settings_requested = Signal()
    memory_requested = Signal()
    developer_mode_requested = Signal()
    update_indicator_clicked = Signal()
    update_history_requested = Signal()

    def __init__(self, parent: QWidget | None = None, *, app_version: str = "v1.0.0") -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(230)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 18, 16, 16)
        outer.setSpacing(4)

        # --- Brand header -------------------------------------------------
        header = QHBoxLayout()
        brand = QLabel("◈  JARVIS")
        brand.setObjectName("sidebarBrand")
        header.addWidget(brand)
        outer.addLayout(header)
        version = QLabel(f"{app_version} · PRO")
        version.setObjectName("sidebarVersion")
        outer.addWidget(version)
        outer.addSpacing(14)

        # --- Nav items ------------------------------------------------------
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, NavItemButton] = {}

        for item_id, icon, label in NAV_ITEMS:
            btn = NavItemButton(icon, label)
            btn.clicked.connect(lambda _checked, i=item_id: self._on_nav_clicked(i))
            self._group.addButton(btn)
            self._buttons[item_id] = btn
            outer.addWidget(btn)

        self._buttons["home"].setChecked(True)
        outer.addStretch(1)

        # --- Update progress indicator (Milestone 5, 10D) --------------------
        # Hidden until an update session starts; clicking it reopens the
        # Update Terminal. See MainWindow._on_update_phase_event.
        from jarvis.ui.components.progress import LabeledProgressBar

        self._update_indicator = QWidget()
        self._update_indicator.setObjectName("updateSidebarIndicator")
        self._update_indicator.setCursor(Qt.CursorShape.PointingHandCursor)
        indicator_layout = QVBoxLayout(self._update_indicator)
        indicator_layout.setContentsMargins(8, 6, 8, 6)
        self._update_progress = LabeledProgressBar("Updating…")
        indicator_layout.addWidget(self._update_progress)
        self._update_indicator.mousePressEvent = (  # type: ignore[assignment]
            lambda _e: self.update_indicator_clicked.emit()
        )
        self._update_indicator.setVisible(False)
        outer.addWidget(self._update_indicator)
        outer.addSpacing(4)

        # --- Update history (Milestone 5, section 8) --------------------
        # Extends the live-progress indicator above with a persistent
        # summary that survives after an update finishes: last update
        # result, last successful/failed update, rollback result, and a
        # shortcut into recent history -- all without touching Update
        # Center itself.
        self._history_row = QWidget()
        self._history_row.setObjectName("updateHistoryRow")
        self._history_row.setCursor(Qt.CursorShape.PointingHandCursor)
        history_layout = QHBoxLayout(self._history_row)
        history_layout.setContentsMargins(8, 4, 8, 4)
        history_layout.setSpacing(6)

        self._history_summary_label = QLabel("No updates yet")
        self._history_summary_label.setObjectName("rowSubtitle")
        history_layout.addWidget(self._history_summary_label, 1)

        self._history_badge = QLabel("")
        self._history_badge.setObjectName("updateHistoryBadge")
        self._history_badge.setVisible(False)
        history_layout.addWidget(self._history_badge)

        self._history_row.mousePressEvent = (  # type: ignore[assignment]
            lambda _e: self.update_history_requested.emit()
        )
        outer.addWidget(self._history_row)
        outer.addSpacing(8)

        # --- Developer Mode entry point (10A -- password gated, not shown
        # as a normal nav item so it doesn't compete visually with the
        # official UI's fixed nav list). ------------------------------------
        dev_row = QHBoxLayout()
        dev_button = QLabel("🔒  Developer Mode")
        dev_button.setObjectName("rowSubtitle")
        dev_button.setCursor(Qt.CursorShape.PointingHandCursor)
        dev_button.mousePressEvent = lambda _e: self.developer_mode_requested.emit()  # type: ignore[assignment]
        dev_row.addWidget(dev_button)
        outer.addLayout(dev_row)
        outer.addSpacing(8)

        # --- Profile footer --------------------------------------------------
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("color: #12253F;")
        outer.addWidget(divider)

        profile = QHBoxLayout()
        avatar = QLabel("🧑")
        profile.addWidget(avatar)
        name_col = QVBoxLayout()
        name_col.setSpacing(0)
        self._name_label = QLabel("You")
        self._name_label.setObjectName("rowTitle")
        name_col.addWidget(self._name_label)
        status = QLabel("● Online")
        status.setObjectName("serviceStatus")
        name_col.addWidget(status)
        profile.addLayout(name_col)
        profile.addStretch(1)
        outer.addLayout(profile)

    # ------------------------------------------------------------------
    def set_user_name(self, name: str) -> None:
        self._name_label.setText(name)

    def show_update_progress(self, percent: int, label: str) -> None:
        self._update_indicator.setVisible(True)
        self._update_progress.set_progress(percent, label)

    def hide_update_progress(self) -> None:
        self._update_indicator.setVisible(False)

    def set_update_history(self, sessions: list) -> None:
        """Feed the persistent history row from
        ``UpdateService.session_history()``. Each item only needs
        ``.succeeded``, ``.to_version``, ``.finished_at``, and
        ``.rollback_report`` attributes (a real ``UpdateSession``)."""
        if not sessions:
            self._history_summary_label.setText("No updates yet")
            self._history_badge.setVisible(False)
            return

        latest = sessions[0]
        when = latest.finished_at.strftime("%b %d, %H:%M") if latest.finished_at else "in progress"
        if latest.rollback_report is not None:
            status = "Rolled back" if latest.rollback_report.succeeded else "Rollback failed"
        elif latest.succeeded:
            status = f"Updated to {latest.to_version}"
        else:
            status = "Update failed"
        self._history_summary_label.setText(f"🕘 {status} · {when}")

        failures = sum(1 for s in sessions if s.succeeded is False)
        if failures:
            self._history_badge.setText(str(failures))
            self._history_badge.setVisible(True)
        else:
            self._history_badge.setVisible(False)

    def select(self, item_id: str) -> None:
        button = self._buttons.get(item_id)
        if button is not None:
            button.setChecked(True)

    def _on_nav_clicked(self, item_id: str) -> None:
        self.nav_selected.emit(item_id)
        if item_id == "settings":
            self.settings_requested.emit()
        elif item_id == "memory":
            self.memory_requested.emit()

    # ------------------------------------------------------------------
    # Backward-compatible no-ops (Milestone 2's conversation list lived
    # here; it now lives in ChatPage, but MainWindow may still connect
    # these before the refactor lands everywhere).
    # ------------------------------------------------------------------
    def set_conversations(self, conversations: list) -> None:
        return None
