"""Update Terminal -- Milestone 5, section 10D (and section 4: docking
improvements).

A premium live-log window that opens automatically whenever an update
starts. Subscribes to :class:`UpdatePhaseEvent` on the shared
:class:`EventBus`, so it shows exactly the same phase transitions the
sidebar progress indicator does -- one source of truth, two views.

Supports: live logs, search/filter, copy, export, auto-scroll, and five
display modes -- Dock Bottom / Dock Left / Dock Right / Float /
Fullscreen -- plus collapse. The dock modes reposition+resize this
top-level window to hug a screen edge (this stays a ``QDialog``, not a
``QMainWindow``-owned ``QDockWidget``, so "docked" means visually
snapped to the edge and resizable from its inner edge, not physically
merged into ``MainWindow``'s frame -- a real ``QDockWidget`` refactor
remains a reasonable follow-up if the terminal needs to feel physically
attached). The last-used mode and geometry are persisted via
``QSettings`` and restored next launch.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QSettings
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSizeGrip,
    QVBoxLayout,
    QWidget,
)

from jarvis.ui.components import LabeledProgressBar, StepProgress
from jarvis.ui.components.icons import icon_registry

if TYPE_CHECKING:
    from jarvis.core.events.event_bus import EventBus

_STEPS = [
    "Checking Updates",
    "Downloading",
    "Installing",
    "Verifying",
    "Optimizing",
    "Restart Required",
]
_PHASE_TO_STEP = {
    "checking_updates": "Checking Updates",
    "downloading": "Downloading",
    "installing": "Installing",
    "verifying": "Verifying",
    "optimizing": "Optimizing",
    "restart_required": "Restart Required",
}

_DOCK_SIDE_HEIGHT = 260
_DOCK_SIDE_WIDTH = 420


class UpdateTerminalDialog(QDialog):
    def __init__(self, event_bus: EventBus | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Update Terminal")
        self.resize(640, 520)
        self._event_bus = event_bus
        self._all_lines: list[str] = []
        self._unsubscribe = None
        self._mode = "float"
        self._settings = QSettings("JarvisOS", "UpdateTerminal")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel(f"{icon_registry.glyph('terminal')}  Update Terminal")
        title.setObjectName("cardTitle")
        header.addWidget(title)
        header.addStretch(1)

        self._mode_buttons: dict[str, QPushButton] = {}
        for mode, label, icon_key, handler in [
            ("dock_bottom", "Dock Bottom", "dock_bottom", self._dock_bottom),
            ("dock_left", "Dock Left", "dock_left", self._dock_left),
            ("dock_right", "Dock Right", "dock_right", self._dock_right),
            ("float", "Float", "float", self._float),
            ("fullscreen", "Fullscreen", "fullscreen", self._fullscreen),
        ]:
            btn = QPushButton(f"{icon_registry.glyph(icon_key)} {label}")
            btn.setObjectName("cardAction")
            btn.setCheckable(True)
            btn.clicked.connect(handler)
            header.addWidget(btn)
            self._mode_buttons[mode] = btn

        collapse_btn = QPushButton("Collapse")
        collapse_btn.setObjectName("cardAction")
        collapse_btn.clicked.connect(self._toggle_collapse)
        header.addWidget(collapse_btn)
        outer.addLayout(header)

        self._progress = LabeledProgressBar("Idle")
        outer.addWidget(self._progress)

        self._steps = StepProgress(_STEPS)
        outer.addWidget(self._steps)

        self._body = QWidget()
        body_layout = QVBoxLayout(self._body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(8)

        toolbar = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search logs…")
        self._search.textChanged.connect(self._apply_filter)
        toolbar.addWidget(self._search, 1)

        self._auto_scroll = QCheckBox("Auto-scroll")
        self._auto_scroll.setChecked(True)
        toolbar.addWidget(self._auto_scroll)

        copy_btn = QPushButton("Copy")
        copy_btn.clicked.connect(self._copy)
        toolbar.addWidget(copy_btn)

        export_btn = QPushButton("Export")
        export_btn.clicked.connect(self._export)
        toolbar.addWidget(export_btn)
        body_layout.addLayout(toolbar)

        self._log = QPlainTextEdit()
        self._log.setObjectName("updateTerminalLog")
        self._log.setReadOnly(True)
        body_layout.addWidget(self._log, 1)

        # A visible grip makes "resizable" discoverable even while docked
        # to an edge, where the window border alone can be hard to grab.
        grip_row = QHBoxLayout()
        grip_row.addStretch(1)
        grip_row.addWidget(QSizeGrip(self))
        body_layout.addLayout(grip_row)

        outer.addWidget(self._body, 1)

        if event_bus is not None:
            self._subscribe(event_bus)

        self._restore_state()

    # ------------------------------------------------------------------
    def _subscribe(self, event_bus: EventBus) -> None:
        from jarvis.core.events.events import UpdatePhaseEvent

        async def _on_event(evt: UpdatePhaseEvent) -> None:
            self.append_line(f"[{evt.phase}] {evt.message}")
            self._progress.set_progress(evt.progress_percent, evt.phase.replace("_", " ").title())
            step = _PHASE_TO_STEP.get(evt.phase)
            if step:
                self._steps.set_status(step, "running")
                # Mark earlier steps succeeded once we've moved past them.
                idx = _STEPS.index(step)
                for earlier in _STEPS[:idx]:
                    self._steps.set_status(earlier, "succeeded")
            if evt.phase == "update_completed":
                for s in _STEPS:
                    self._steps.set_status(s, "succeeded")
            if evt.phase == "failed":
                if step:
                    self._steps.set_status(step, "failed")

        self._unsubscribe = event_bus.subscribe(UpdatePhaseEvent, _on_event)

    def append_line(self, line: str) -> None:
        self._all_lines.append(line)
        self._apply_filter()

    def _apply_filter(self) -> None:
        query = self._search.text().strip().lower()
        lines = [l for l in self._all_lines if query in l.lower()] if query else self._all_lines
        self._log.setPlainText("\n".join(lines))
        if self._auto_scroll.isChecked():
            bar = self._log.verticalScrollBar()
            bar.setValue(bar.maximum())

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self._log.toPlainText())

    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Logs", "update_log.txt", "Text Files (*.txt)"
        )
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self._log.toPlainText())

    # ------------------------------------------------------------------
    # Display modes -- Dock Bottom / Dock Left / Dock Right / Float /
    # Fullscreen, all resizable via the size grip and the OS window
    # border, and persisted across sessions (Milestone 5, section 4).
    # ------------------------------------------------------------------
    def _set_mode(self, mode: str) -> None:
        self._mode = mode
        for name, btn in self._mode_buttons.items():
            btn.setChecked(name == mode)
        self._persist_state()

    def _dock_bottom(self) -> None:
        self.showNormal()
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            geo = screen.availableGeometry()
            self.resize(geo.width(), _DOCK_SIDE_HEIGHT)
            self.move(geo.x(), geo.y() + geo.height() - _DOCK_SIDE_HEIGHT)
        self._set_mode("dock_bottom")

    def _dock_left(self) -> None:
        self.showNormal()
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            geo = screen.availableGeometry()
            self.resize(_DOCK_SIDE_WIDTH, geo.height())
            self.move(geo.x(), geo.y())
        self._set_mode("dock_left")

    def _dock_right(self) -> None:
        self.showNormal()
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            geo = screen.availableGeometry()
            self.resize(_DOCK_SIDE_WIDTH, geo.height())
            self.move(geo.x() + geo.width() - _DOCK_SIDE_WIDTH, geo.y())
        self._set_mode("dock_right")

    def _float(self) -> None:
        self.showNormal()
        self.resize(640, 520)
        self._set_mode("float")

    def _fullscreen(self) -> None:
        self.showFullScreen()
        self._set_mode("fullscreen")

    def _toggle_collapse(self) -> None:
        self._body.setVisible(not self._body.isVisible())
        self._settings.setValue("collapsed", not self._body.isVisible())

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _persist_state(self) -> None:
        self._settings.setValue("mode", self._mode)
        self._settings.setValue("geometry", self.saveGeometry())

    def _restore_state(self) -> None:
        mode = self._settings.value("mode", "float")
        geometry = self._settings.value("geometry")
        collapsed = self._settings.value("collapsed", False, type=bool)

        dispatch = {
            "dock_bottom": self._dock_bottom,
            "dock_left": self._dock_left,
            "dock_right": self._dock_right,
            "float": self._float,
            "fullscreen": self._fullscreen,
        }
        # Apply the remembered mode first (sets geometry to that mode's
        # default), then restore the exact saved geometry on top of it
        # if the user had resized/moved the window since.
        dispatch.get(mode, self._float)()
        if geometry is not None:
            self.restoreGeometry(geometry)
        if collapsed:
            self._body.setVisible(False)

    def closeEvent(self, event) -> None:
        self._persist_state()
        super().closeEvent(event)
