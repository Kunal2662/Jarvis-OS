"""Simple list panels -- used for Today's Schedule, Tasks, Recent
Notifications, and every Developer Mode mock data table."""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget


class KeyValueRow(QWidget):
    def __init__(self, key: str, value: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        key_label = QLabel(key)
        key_label.setObjectName("rowKey")
        value_label = QLabel(value)
        value_label.setObjectName("rowValue")
        row.addWidget(key_label)
        row.addStretch(1)
        row.addWidget(value_label)


class SimpleListPanel(QWidget):
    """A vertical stack of ``label — sublabel — trailing`` rows, optionally
    with a leading checkbox (for the Tasks card)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)

    def clear(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def add_row(
        self, title: str, subtitle: str = "", trailing: str = "", *, checkable: bool = False
    ) -> None:
        row = QHBoxLayout()
        row.setSpacing(8)
        if checkable:
            box = QCheckBox()
            row.addWidget(box)
        text_col = QVBoxLayout()
        text_col.setSpacing(0)
        title_label = QLabel(title)
        title_label.setObjectName("rowTitle")
        text_col.addWidget(title_label)
        if subtitle:
            sub_label = QLabel(subtitle)
            sub_label.setObjectName("rowSubtitle")
            text_col.addWidget(sub_label)
        row.addLayout(text_col, 1)
        if trailing:
            trailing_label = QLabel(trailing)
            trailing_label.setObjectName("rowTrailing")
            row.addWidget(trailing_label)
        self._layout.addLayout(row)
