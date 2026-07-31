"""Dependency-free mini charts for workspace dashboards (Finance
performance, Smart Home energy usage, Coding activity, ...).

No QtCharts / matplotlib dependency is introduced -- these are small
``QWidget`` subclasses that paint directly with ``QPainter``, which
keeps them cheap to construct and easy to reuse inside a ``Card``.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget


class MiniBarChart(QWidget):
    def __init__(
        self,
        values: list[float] | None = None,
        *,
        accent: str = "#5B8CFF",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._values = values or []
        self._accent = QColor(accent)
        self.setMinimumHeight(90)

    def set_values(self, values: list[float]) -> None:
        self._values = values
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        if not self._values:
            painter.setPen(QColor("#6B7A99"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "No data")
            return
        maximum = max(self._values) or 1.0
        n = len(self._values)
        gap = 6
        bar_width = max(4.0, (rect.width() - gap * (n - 1)) / n)
        painter.setPen(Qt.PenStyle.NoPen)
        for i, value in enumerate(self._values):
            height = (value / maximum) * (rect.height() - 4)
            x = i * (bar_width + gap)
            y = rect.height() - height
            color = QColor(self._accent)
            color.setAlphaF(0.55 + 0.45 * (value / maximum))
            painter.setBrush(color)
            painter.drawRoundedRect(QRectF(x, y, bar_width, height), 3, 3)


class MiniLineChart(QWidget):
    def __init__(
        self,
        values: list[float] | None = None,
        *,
        accent: str = "#3DDC97",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._values = values or []
        self._accent = QColor(accent)
        self.setMinimumHeight(90)

    def set_values(self, values: list[float]) -> None:
        self._values = values
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        if len(self._values) < 2:
            painter.setPen(QColor("#6B7A99"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "No data")
            return
        low, high = min(self._values), max(self._values)
        span = (high - low) or 1.0
        n = len(self._values)
        step = rect.width() / (n - 1)
        points = []
        for i, value in enumerate(self._values):
            x = i * step
            y = rect.height() - ((value - low) / span) * (rect.height() - 6) - 3
            points.append((x, y))
        pen = QPen(self._accent, 2.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        for (x1, y1), (x2, y2) in zip(points, points[1:], strict=False):
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))
