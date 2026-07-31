"""Virtualized table (Milestone 5, section 12: performance).

``SimpleTable`` (``ui/components/table.py``) is a ``QTableWidget`` --
simple to use, but it materializes a ``QTableWidgetItem`` per cell for
every row up front. Fine for the tens-of-rows mock tables most
workspaces show today, but not for anything that could grow into the
thousands (a real Gmail inbox, a real file listing).

``VirtualTable`` is the scale-ready alternative: a ``QTableView`` over
a plain ``QAbstractTableModel`` that only ever constructs a
``QModelIndex`` on demand for the rows Qt is actually about to paint --
genuine virtualization, not just fewer widgets. Swap-in compatible with
``SimpleTable``'s ``set_rows(list[list[str]])`` shape so call sites can
adopt it without changing how they think about their data.
"""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableView, QWidget


class _RowModel(QAbstractTableModel):
    def __init__(self, headers: list[str]) -> None:
        super().__init__()
        self._headers = headers
        self._rows: list[list[str]] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._headers)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        return self._rows[index.row()][index.column()]

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ):
        if role != Qt.ItemDataRole.DisplayRole or orientation != Qt.Orientation.Horizontal:
            return None
        return self._headers[section]

    def set_rows(self, rows: list[list[str]]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()


class VirtualTable(QTableView):
    def __init__(self, headers: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("workspaceTable")
        self._model = _RowModel(headers)
        self.setModel(self._model)
        self.verticalHeader().setVisible(False)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(False)  # sorting a virtual model needs a proxy -- future follow-up
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setHighlightSections(False)

    def set_rows(self, rows: list[list[str]]) -> None:
        self._model.set_rows(rows)

    def row_count(self) -> int:
        return self._model.rowCount()
