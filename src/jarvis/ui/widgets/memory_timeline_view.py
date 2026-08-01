"""Memory Timeline view — Milestone 3.1.

Browsing memories by type / pinned / archived state was previously
DB-or-CLI-only; Settings ▸ Memory only covered config + maintenance. This
widget is the missing UI view: a filterable list backed by
:class:`~jarvis.features.memory.controller.MemoryController`, with
per-row pin / archive / forget actions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from jarvis.core.types import MemoryType

if TYPE_CHECKING:
    from jarvis.services.memory_service import MemoryRecord

_TYPE_LABELS: dict[str, str] = {
    "": "All types",
    MemoryType.CONVERSATION.value: "Conversation",
    MemoryType.LONG_TERM.value: "Long-term",
    MemoryType.PREFERENCE.value: "Preference",
    MemoryType.PROJECT.value: "Project",
    MemoryType.TASK.value: "Task",
    MemoryType.FILE.value: "File",
    MemoryType.AI_CONTEXT.value: "AI context",
}


class MemoryTimelineView(QWidget):
    """Filter bar + list. Emits ``filters_changed`` whenever a filter
    control changes; the owning dialog wires that straight into
    ``MemoryController.browse``.
    """

    filters_changed = Signal(str, bool, bool)  # memory_type, pinned_only, include_archived
    pin_toggled = Signal(str, bool)  # memory_id, new_pinned_state
    archive_requested = Signal(str)  # memory_id
    forget_requested = Signal(str)  # memory_id

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        filters = QHBoxLayout()
        filters.setSpacing(8)

        self._type_combo = QComboBox()
        for value, label in _TYPE_LABELS.items():
            self._type_combo.addItem(label, value)
        self._type_combo.currentIndexChanged.connect(self._emit_filters_changed)
        filters.addWidget(QLabel("Type:"))
        filters.addWidget(self._type_combo)

        self._pinned_only = QCheckBox("Pinned only")
        self._pinned_only.toggled.connect(self._emit_filters_changed)
        filters.addWidget(self._pinned_only)

        self._include_archived = QCheckBox("Show archived")
        self._include_archived.toggled.connect(self._emit_filters_changed)
        filters.addWidget(self._include_archived)

        filters.addStretch(1)

        self._refresh_btn = QPushButton("Refresh")
        filters.addWidget(self._refresh_btn)

        outer.addLayout(filters)

        self._list = QListWidget()
        self._list.setObjectName("memoryTimelineList")
        self._list.setAlternatingRowColors(True)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context_menu)
        outer.addWidget(self._list, 1)

        self._empty_label = QLabel("No memories match these filters.")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("color:#6D8BAA; padding:24px;")
        self._empty_label.hide()
        outer.addWidget(self._empty_label)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @property
    def refresh_button(self) -> QPushButton:
        return self._refresh_btn

    def current_filters(self) -> tuple[str, bool, bool]:
        return (
            self._type_combo.currentData() or "",
            self._pinned_only.isChecked(),
            self._include_archived.isChecked(),
        )

    def set_records(self, records: list[MemoryRecord]) -> None:
        self._list.clear()
        self._empty_label.setVisible(not records)
        for record in records:
            item = QListWidgetItem(self._format_record(record))
            item.setData(Qt.ItemDataRole.UserRole, record.id)
            item.setData(Qt.ItemDataRole.UserRole + 1, record.pinned)
            item.setToolTip(record.content)
            self._list.addItem(item)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _emit_filters_changed(self, *_args) -> None:
        mtype, pinned_only, include_archived = self.current_filters()
        self.filters_changed.emit(mtype, pinned_only, include_archived)

    @staticmethod
    def _format_record(record: MemoryRecord) -> str:
        # QListWidgetItem is plain text -- a real icon per flag would need
        # a per-row custom widget, out of scope for this pass; short
        # bracketed text markers replace the previous emoji instead.
        flags = []
        if record.pinned:
            flags.append("[Pinned]")
        if record.archived:
            flags.append("[Archived]")
        flag_str = " ".join(flags) + (" " if flags else "")
        type_label = _TYPE_LABELS.get(record.memory_type, record.memory_type)
        preview = record.content.replace("\n", " ").strip()
        if len(preview) > 140:
            preview = preview[:137] + "…"
        when = record.created_at.strftime("%Y-%m-%d %H:%M")
        return f"{flag_str}[{type_label}] {when} — {preview}"

    def _on_context_menu(self, pos) -> None:
        item = self._list.itemAt(pos)
        if item is None:
            return
        memory_id = item.data(Qt.ItemDataRole.UserRole)
        pinned = bool(item.data(Qt.ItemDataRole.UserRole + 1))

        menu = QMenu(self)
        pin_action = menu.addAction("Unpin" if pinned else "Pin")
        archive_action = menu.addAction("Archive")
        menu.addSeparator()
        forget_action = menu.addAction("Delete permanently")

        chosen = menu.exec(self._list.viewport().mapToGlobal(pos))
        if chosen is pin_action:
            self.pin_toggled.emit(memory_id, not pinned)
        elif chosen is archive_action:
            self.archive_requested.emit(memory_id)
        elif chosen is forget_action:
            self.forget_requested.emit(memory_id)
