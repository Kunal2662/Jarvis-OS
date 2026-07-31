"""Update Center -- Milestone 5, sections 10C/10E/10F.

Dashboard for the mock update pipeline: current version, channel picker,
"Check for Updates" / "Update Now", version history & release notes.
Clicking "Update Now" automatically opens the Update Terminal (10D) and
runs the pipeline, which itself automatically creates a restore point
and rolls back on failure (10E) while announcing phase changes via TTS
(10F) -- this view just triggers and displays; the real work lives in
:class:`UpdateService`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from jarvis.domain.updates.models import UpdateChannel
from jarvis.ui.components import SectionCard, SimpleListPanel, StatusBadge
from jarvis.ui.dialogs.update_terminal_dialog import UpdateTerminalDialog
from jarvis.utils.async_utils import fire_and_forget

if TYPE_CHECKING:
    from jarvis.services.update_service import UpdateService


class UpdateCenterView(QWidget):
    def __init__(self, update_service: UpdateService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = update_service
        self._terminal: UpdateTerminalDialog | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(14)

        title = QLabel("Update Center")
        title.setObjectName("greetingTitle")
        outer.addWidget(title)

        dashboard = SectionCard("Update Dashboard")
        info_row = QHBoxLayout()
        self._version_label = QLabel(f"Current version: {update_service.current_version}")
        self._version_label.setObjectName("rowValue")
        info_row.addWidget(self._version_label)
        info_row.addStretch(1)

        info_row.addWidget(QLabel("Channel:"))
        self._channel_combo = QComboBox()
        for channel in UpdateChannel:
            self._channel_combo.addItem(channel.value.title(), channel)
        info_row.addWidget(self._channel_combo)
        dashboard.body.addLayout(info_row)

        self._status_badge = StatusBadge("Up to date", "success")
        dashboard.body.addWidget(self._status_badge)

        buttons_row = QHBoxLayout()
        check_btn = QPushButton("Check for Updates")
        check_btn.clicked.connect(self._check_for_updates)
        buttons_row.addWidget(check_btn)

        self._update_btn = QPushButton("Update Now")
        self._update_btn.setProperty("variant", "primary")
        self._update_btn.clicked.connect(self._start_update)
        buttons_row.addWidget(self._update_btn)

        self._simulate_failure = QCheckBox("Simulate failed update (demo rollback)")
        buttons_row.addWidget(self._simulate_failure)
        buttons_row.addStretch(1)
        dashboard.body.addLayout(buttons_row)
        outer.addWidget(dashboard)

        history = SectionCard("Version History & Release Notes")
        self._history_list = SimpleListPanel()
        history.body.addWidget(self._history_list)
        outer.addWidget(history)
        self._refresh_history()

        outer.addStretch(1)

    # ------------------------------------------------------------------
    def _refresh_history(self) -> None:
        channel = self._channel_combo.currentData()
        self._history_list.clear()
        for note in self._service.version_history(channel):
            self._history_list.add_row(
                f"{note.version} ({note.channel.value})",
                " · ".join(note.highlights),
                note.released_at.strftime("%d %b %Y"),
            )

    def _check_for_updates(self) -> None:
        channel = self._channel_combo.currentData()
        latest = self._service.check_for_updates(channel)
        if latest is None:
            self._status_badge.set_state("success", "Up to date")
        else:
            self._status_badge.set_state("warning", f"Update available: {latest.version}")
        self._refresh_history()

    def _start_update(self) -> None:
        self._terminal = UpdateTerminalDialog(self._service.event_bus, self)
        self._terminal.append_line("Update requested by user.")
        self._terminal.show()
        fire_and_forget(self._run_update())

    async def _run_update(self) -> None:
        channel = self._channel_combo.currentData()
        session = await self._service.run_update(
            channel, simulate_failure=self._simulate_failure.isChecked()
        )
        self._version_label.setText(f"Current version: {self._service.current_version}")
        if session.succeeded:
            self._status_badge.set_state("success", f"Updated to {session.to_version}")
        else:
            self._status_badge.set_state("danger", "Update failed -- rolled back")
        self._refresh_history()
