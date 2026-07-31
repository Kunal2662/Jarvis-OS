"""Performance Monitor -- Milestone 5, section 10A.

Live CPU/memory/disk gauges via ``psutil`` (already a project
dependency), refreshed on a QTimer. Falls back to a "psutil not
available" notice rather than fabricating numbers.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from jarvis.ui.components import SectionCard, StatTile


class PerformanceMonitorView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(14)

        title = QLabel("Performance Monitor")
        title.setObjectName("greetingTitle")
        outer.addWidget(title)

        card = SectionCard("Live System Load")
        row = QHBoxLayout()
        self._cpu_tile = StatTile("CPU", "—")
        self._mem_tile = StatTile("Memory", "—")
        self._disk_tile = StatTile("Disk", "—")
        row.addWidget(self._cpu_tile)
        row.addWidget(self._mem_tile)
        row.addWidget(self._disk_tile)
        card.body.addLayout(row)
        outer.addWidget(card)
        outer.addStretch(1)

        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()
        self._refresh()

    def _refresh(self) -> None:
        try:
            import psutil

            cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            self._set_tile(self._cpu_tile, f"{cpu:.0f}%")
            self._set_tile(self._mem_tile, f"{mem.percent:.0f}%")
            self._set_tile(self._disk_tile, f"{disk.percent:.0f}%")
        except ImportError:
            self._set_tile(self._cpu_tile, "n/a")
            self._set_tile(self._mem_tile, "n/a")
            self._set_tile(self._disk_tile, "n/a")

    @staticmethod
    def _set_tile(tile: StatTile, value: str) -> None:
        for label in tile.findChildren(QLabel):
            if label.objectName() == "statValue":
                label.setText(value)
                return
