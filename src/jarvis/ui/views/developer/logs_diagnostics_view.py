"""Logs & Diagnostics -- Milestone 5, section 10A.

Tails the real ``jarvis.log`` file (see ``jarvis.core.logging.logger``)
when file logging is enabled; otherwise explains why there's nothing to
show yet, rather than fabricating log lines.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from jarvis.core.config import paths as _paths

if TYPE_CHECKING:
    from jarvis.core.config.settings import Settings


class LogsDiagnosticsView(QWidget):
    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(10)

        title = QLabel("Logs & Diagnostics")
        title.setObjectName("greetingTitle")
        outer.addWidget(title)

        toolbar = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter log lines…")
        self._search.textChanged.connect(self._refresh)
        toolbar.addWidget(self._search, 1)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh)
        toolbar.addWidget(refresh_btn)
        outer.addLayout(toolbar)

        self._log_view = QPlainTextEdit()
        self._log_view.setObjectName("updateTerminalLog")
        self._log_view.setReadOnly(True)
        outer.addWidget(self._log_view, 1)

        self._refresh()

    def _refresh(self) -> None:
        log_path = _paths.log_dir(self._settings.resolved_data_dir) / "jarvis.log"
        if not log_path.exists():
            self._log_view.setPlainText(
                "No log file yet. Enable JARVIS_LOG_FILE_ENABLED=true and restart to start logging to disk."
            )
            return
        try:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-500:]
        except OSError as err:
            self._log_view.setPlainText(f"Could not read log file: {err}")
            return

        query = self._search.text().strip().lower()
        if query:
            lines = [l for l in lines if query in l.lower()]
        self._log_view.setPlainText("\n".join(lines) or "No matching log lines.")
