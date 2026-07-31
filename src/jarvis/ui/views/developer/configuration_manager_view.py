"""Configuration Manager -- Milestone 5, section 10A.

Read-only tree of the live :class:`Settings` snapshot (real data via
:meth:`SettingsService.snapshot`), with secret-looking values redacted.
Editing individual settings already happens in the main Settings dialog
(``ui/dialogs/settings_dialog.py``); this view is the developer-facing
"show me everything at once" companion to that, not a replacement.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QLabel, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

if TYPE_CHECKING:
    from jarvis.services.settings_service import SettingsService

_REDACT_KEYS = {"secret_key", "api_key", "password_hash", "bearer_token", "secret"}


def _add_node(parent: QTreeWidgetItem, key: str, value: object) -> None:
    if isinstance(value, dict):
        node = QTreeWidgetItem([str(key), ""])
        parent.addChild(node)
        for k, v in value.items():
            _add_node(node, k, v)
    else:
        display = "••••••••" if key in _REDACT_KEYS and value else str(value)
        parent.addChild(QTreeWidgetItem([str(key), display]))


class ConfigurationManagerView(QWidget):
    def __init__(self, settings_service: SettingsService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(10)

        title = QLabel("Configuration Manager")
        title.setObjectName("greetingTitle")
        outer.addWidget(title)

        note = QLabel("Live, read-only snapshot of every setting currently in effect.")
        note.setObjectName("rowSubtitle")
        outer.addWidget(note)

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Key", "Value"])
        self._tree.setColumnWidth(0, 260)
        root = self._tree.invisibleRootItem()
        for key, value in settings_service.snapshot().items():
            _add_node(root, key, value)
        self._tree.expandToDepth(0)
        outer.addWidget(self._tree, 1)
