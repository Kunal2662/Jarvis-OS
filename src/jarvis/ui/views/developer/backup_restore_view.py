"""Backup & Restore -- Milestone 5, section 10A (backed by the real
Automatic Rollback plumbing from section 10E).

Restore points here are the exact same ones the Update Center creates
automatically before every update -- this view just exposes manual
"create now" / "restore" controls over the same
:class:`~jarvis.features.updates.rollback_manager.RollbackManager`, so
there is only one restore-point store in the whole app.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from jarvis.ui.components import Card, SectionCard
from jarvis.utils.async_utils import fire_and_forget

if TYPE_CHECKING:
    from jarvis.services.update_service import UpdateService


class BackupRestoreView(QWidget):
    def __init__(self, update_service: UpdateService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = update_service

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(14)

        title = QLabel("Backup & Restore")
        title.setObjectName("greetingTitle")
        outer.addWidget(title)

        note = QLabel(
            "Backs up settings, memory, plugins, themes, models, configuration and API keys."
        )
        note.setObjectName("rowSubtitle")
        note.setWordWrap(True)
        outer.addWidget(note)

        create_btn = QPushButton("Create Restore Point Now")
        create_btn.setProperty("variant", "primary")
        create_btn.clicked.connect(self._create_now)
        outer.addWidget(create_btn)

        self._card = SectionCard("Restore Points")
        outer.addWidget(self._card)
        outer.addStretch(1)

        self.refresh()

    def refresh(self) -> None:
        while self._card.body.count():
            item = self._card.body.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        points = self._service.list_restore_points()
        if not points:
            empty = QLabel("No restore points yet.")
            empty.setObjectName("rowSubtitle")
            self._card.body.addWidget(empty)
            return

        for point in points:
            row = Card()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(12, 8, 12, 8)
            text = QLabel(
                f"{point.version} · {point.created_at:%Y-%m-%d %H:%M} · {point.size_mb:.2f} MB"
            )
            text.setObjectName("rowValue")
            row_layout.addWidget(text, 1)
            restore_btn = QPushButton("Restore")
            restore_btn.setObjectName("cardAction")
            restore_btn.clicked.connect(lambda _c=False, pid=point.id: self._restore(pid))
            row_layout.addWidget(restore_btn)
            self._card.body.addWidget(row)

    def _create_now(self) -> None:
        self._service.create_restore_point_now()
        self.refresh()

    def _restore(self, point_id: str) -> None:
        confirm = QMessageBox.question(
            self, "Restore", "Restore settings, memory and configuration from this point?"
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        fire_and_forget(self._restore_async(point_id))

    async def _restore_async(self, point_id: str) -> None:
        report = await self._service.rollback_to(point_id)
        QMessageBox.information(
            self,
            "Restore",
            "Restore completed." if report.succeeded else f"Restore failed: {report.notes}",
        )
