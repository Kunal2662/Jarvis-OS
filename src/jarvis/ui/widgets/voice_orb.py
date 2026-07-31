"""Animated voice-state indicator.

A single small widget that renders differently per
:class:`~jarvis.core.types.VoiceState`:

* ``listening``   — a pulsing microphone ring + a live-ish moving waveform
* ``thinking``    — a soft rotating spinner / animated dots
* ``speaking``    — an animated speech waveform
* ``interrupted`` — a brief flash, then falls back to listening
* ``idle``        — a static, dim microphone glyph
* ``offline`` / ``error`` — a dim glyph in a warning color

All animation is driven by a single ``QTimer`` ticking ~30x/sec; the
widget repaints itself via ``QPainter`` so there are no image assets to
ship.
"""

from __future__ import annotations

import math
import random

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

_COLORS = {
    "idle": QColor("#6D8BAA"),
    "listening": QColor("#0E9F6E"),
    "thinking": QColor("#B76E00"),
    "speaking": QColor("#3B82F6"),
    "interrupted": QColor("#D62839"),
    "offline": QColor("#6D8BAA"),
    "error": QColor("#D62839"),
}


class VoiceOrb(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("voiceOrb")
        self.setFixedSize(48, 48)
        self._state: str = "idle"
        self._phase: float = 0.0
        self._bars = [0.3, 0.6, 0.4, 0.8, 0.5]

        self._timer = QTimer(self)
        self._timer.setInterval(33)  # ~30 fps
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    # ------------------------------------------------------------------
    def set_state(self, state: str, _detail: str = "") -> None:
        self._state = state if state in _COLORS else "idle"
        self.update()

    # ------------------------------------------------------------------
    def _tick(self) -> None:
        self._phase += 0.12
        if self._state in ("listening", "speaking"):
            self._bars = [max(0.15, min(1.0, b + random.uniform(-0.25, 0.25))) for b in self._bars]
        self.update()

    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = _COLORS[self._state]
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2

        if self._state == "listening":
            self._paint_pulse(painter, cx, cy, color)
            self._paint_waveform(painter, cx, cy, color, amplitude=1.0)
        elif self._state == "speaking":
            self._paint_waveform(painter, cx, cy, color, amplitude=1.3)
        elif self._state == "thinking":
            self._paint_spinner(painter, cx, cy, color)
        elif self._state == "interrupted":
            self._paint_pulse(painter, cx, cy, color)
        else:
            self._paint_dot(painter, cx, cy, color)

        painter.end()

    # ------------------------------------------------------------------
    def _paint_dot(self, p: QPainter, cx: float, cy: float, color: QColor) -> None:
        p.setBrush(color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(int(cx - 5), int(cy - 5), 10, 10)

    def _paint_pulse(self, p: QPainter, cx: float, cy: float, color: QColor) -> None:
        radius = 10 + 6 * (0.5 + 0.5 * math.sin(self._phase))
        alpha = int(120 * (1.0 - (radius - 10) / 6))
        pen_color = QColor(color)
        pen_color.setAlpha(max(30, alpha))
        p.setPen(QPen(pen_color, 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(int(cx - radius), int(cy - radius), int(radius * 2), int(radius * 2))
        self._paint_dot(p, cx, cy, color)

    def _paint_waveform(
        self, p: QPainter, cx: float, cy: float, color: QColor, amplitude: float
    ) -> None:
        p.setPen(QPen(color, 2.5, cap=Qt.PenCapStyle.RoundCap))
        n = len(self._bars)
        spacing = 6
        total = spacing * (n - 1)
        start_x = cx - total / 2
        for i, bar in enumerate(self._bars):
            bar_h = 6 + bar * 14 * amplitude
            x = start_x + i * spacing
            p.drawLine(int(x), int(cy - bar_h / 2), int(x), int(cy + bar_h / 2))

    def _paint_spinner(self, p: QPainter, cx: float, cy: float, color: QColor) -> None:
        radius = 10
        for i in range(8):
            angle = self._phase * 2 + i * (math.pi / 4)
            fade = QColor(color)
            fade.setAlpha(int(255 * ((i + 1) / 8)))
            x = cx + radius * math.cos(angle)
            y = cy + radius * math.sin(angle)
            p.setBrush(fade)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(int(x - 2), int(y - 2), 4, 4)
