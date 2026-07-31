"""Two-column Settings dialog.

Left column: category-grouped list of pages (categories are non-selectable
headings). Right column: a QStackedWidget containing one page per entry
in :data:`PAGE_REGISTRY`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
    QWidget,
)

from jarvis.ui.dialogs.settings_pages import (
    CATEGORY_ORDER,
    PAGE_REGISTRY,
    SettingsPage,
)

if TYPE_CHECKING:
    from jarvis.core.config.settings import Settings
    from jarvis.services.settings_service import SettingsService
    from jarvis.ui.themes.theme_manager import ThemeManager


class SettingsDialog(QDialog):
    def __init__(
        self,
        settings: Settings,
        settings_service: SettingsService,
        theme_manager: ThemeManager,
        parent: QWidget | None = None,
        *,
        memory_service: object | None = None,
        container: object | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings — JARVIS OS")
        self.setModal(True)
        self.resize(920, 640)

        self._settings = settings
        self._service = settings_service
        self._theme_manager = theme_manager
        self._memory_service = memory_service
        self._container = container

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._nav = QListWidget()
        self._nav.setFixedWidth(220)
        self._nav.setObjectName("settingsNav")
        self._nav.setUniformItemSizes(False)

        self._stack = QStackedWidget()
        self._stack.setObjectName("settingsStack")

        root.addWidget(self._nav)
        root.addWidget(self._stack, 1)

        self._populate()
        self._nav.currentRowChanged.connect(self._on_nav_changed)

        if self._nav.count() > 0:
            # Select the first *selectable* row.
            for i in range(self._nav.count()):
                if self._nav.item(i).flags() & Qt.ItemFlag.ItemIsSelectable:
                    self._nav.setCurrentRow(i)
                    break

    # ------------------------------------------------------------------
    # Population
    # ------------------------------------------------------------------
    def _populate(self) -> None:
        # Group descriptors by category, preserving registration order.
        by_category: dict[str, list] = {c: [] for c in CATEGORY_ORDER}
        for desc in PAGE_REGISTRY:
            by_category.setdefault(desc.category, []).append(desc)

        for category in CATEGORY_ORDER:
            entries = by_category.get(category, [])
            if not entries:
                continue

            heading = QListWidgetItem(category.upper())
            heading.setFlags(Qt.ItemFlag.NoItemFlags)  # non-selectable
            font = QFont()
            font.setBold(True)
            font.setPointSize(font.pointSize() - 1)
            heading.setFont(font)
            heading.setForeground(QBrush(QColor("#6D8BAA")))
            heading.setSizeHint(heading.sizeHint())
            self._nav.addItem(heading)

            for desc in entries:
                item = QListWidgetItem(f"   {desc.title}")
                item.setData(Qt.ItemDataRole.UserRole, desc.id)
                if not desc.implemented:
                    item.setForeground(QBrush(QColor("#6D8BAA")))
                    item.setToolTip(desc.milestone)
                self._nav.addItem(item)

                page: SettingsPage = desc.factory(
                    settings=self._settings,
                    settings_service=self._service,
                    theme_manager=self._theme_manager,
                    memory_service=self._memory_service,
                    container=self._container,
                )
                self._stack.addWidget(page)

    def _on_nav_changed(self, row: int) -> None:
        if row < 0:
            return
        item = self._nav.item(row)
        if item is None or not (item.flags() & Qt.ItemFlag.ItemIsSelectable):
            return
        page_id = item.data(Qt.ItemDataRole.UserRole)
        # Map page_id → stack index by scanning children.
        for i in range(self._stack.count()):
            page = self._stack.widget(i)
            if isinstance(page, SettingsPage) and page.id == page_id:
                self._stack.setCurrentIndex(i)
                return
