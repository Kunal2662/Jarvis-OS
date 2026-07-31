"""Memory ▸ Timeline dialog — Milestone 3.1.

Opened from the sidebar's "🧠 Memory" button. Wires
:class:`~jarvis.features.memory.controller.MemoryController` to
:class:`~jarvis.ui.widgets.memory_timeline_view.MemoryTimelineView`
following the same controller/widget split used everywhere else in the
app — the dialog itself is just plumbing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QDialog, QMessageBox, QVBoxLayout, QWidget

from jarvis.features.memory.controller import MemoryController
from jarvis.ui.widgets.memory_timeline_view import MemoryTimelineView

if TYPE_CHECKING:
    from jarvis.services.memory_service import MemoryService


class MemoryTimelineDialog(QDialog):
    def __init__(self, memory_service: MemoryService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Memory — Timeline")
        self.resize(760, 560)

        self._controller = MemoryController(memory_service, parent=self)
        self._view = MemoryTimelineView(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.addWidget(self._view)

        self._wire_signals()

        # Initial load with default filters (all types, active only).
        mtype, pinned_only, include_archived = self._view.current_filters()
        self._controller.browse(mtype, pinned_only, include_archived)

    def _wire_signals(self) -> None:
        self._view.filters_changed.connect(self._controller.browse)
        self._view.refresh_button.clicked.connect(
            lambda: self._controller.browse(*self._view.current_filters())
        )
        self._view.pin_toggled.connect(self._on_pin_toggled)
        self._view.archive_requested.connect(self._on_archive_requested)
        self._view.forget_requested.connect(self._on_forget_requested)

        self._controller.memories_loaded.connect(self._view.set_records)
        self._controller.error.connect(self._on_error)

    def _on_pin_toggled(self, memory_id: str, new_state: bool) -> None:
        self._controller.set_pinned(memory_id, new_state)

    def _on_archive_requested(self, memory_id: str) -> None:
        self._controller.archive(memory_id)

    def _on_forget_requested(self, memory_id: str) -> None:
        confirm = QMessageBox.question(
            self,
            "Delete memory",
            "Permanently delete this memory? This cannot be undone.",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self._controller.forget(memory_id)

    def _on_error(self, message: str) -> None:
        QMessageBox.warning(self, "Memory", message)
