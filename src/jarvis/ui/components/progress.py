"""Progress primitives -- labeled progress bar + multi-step phase tracker
(used by the Update Center dashboard and the Update Terminal)."""

from __future__ import annotations

from typing import ClassVar

from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget

from jarvis.ui.components.icons import Icon, icon_registry


class LabeledProgressBar(QWidget):
    def __init__(self, label: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        row = QHBoxLayout()
        self._label = QLabel(label)
        self._label.setObjectName("progressLabel")
        self._percent = QLabel("0%")
        self._percent.setObjectName("progressPercent")
        row.addWidget(self._label)
        row.addStretch(1)
        row.addWidget(self._percent)
        outer.addLayout(row)

        self._bar = QProgressBar()
        self._bar.setObjectName("progressBar")
        self._bar.setRange(0, 100)
        self._bar.setTextVisible(False)
        outer.addWidget(self._bar)

    def set_progress(self, percent: int, label: str | None = None) -> None:
        self._bar.setValue(max(0, min(100, percent)))
        self._percent.setText(f"{percent}%")
        if label is not None:
            self._label.setText(label)


class StepProgress(QWidget):
    """Vertical list of pipeline phases with a status glyph per row --
    Download / Install / Verify / Optimize / Restart, etc."""

    _ICON_KEYS: ClassVar[dict[str, str]] = {
        "pending": "pending",
        "running": "running",
        "succeeded": "check",
        "failed": "error",
        "skipped": "skipped",
    }

    def __init__(self, steps: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: dict[str, Icon] = {}
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)
        for step in steps:
            row = QHBoxLayout()
            glyph = Icon(self._ICON_KEYS["pending"], size=16)
            text = QLabel(step)
            row.addWidget(glyph)
            row.addWidget(text)
            row.addStretch(1)
            outer.addLayout(row)
            self._rows[step] = glyph

    def set_status(self, step: str, status: str) -> None:
        glyph = self._rows.get(step)
        if glyph is None:
            return
        glyph.set_key(self._ICON_KEYS.get(status, "pending"))
        glyph.set_color(
            {
                "succeeded": icon_registry.success_color,
                "failed": icon_registry.danger_color,
                "running": icon_registry.hover_color,
            }.get(status)
        )
