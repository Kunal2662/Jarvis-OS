"""Developer Console -- Milestone 5, section 10A.

A real console, not a mock: commands typed here run through the actual
Milestone 4 :class:`AutomationService` pipeline (parse -> validate ->
permission -> execute -> history), with output streamed back into the
console log. This reuses the same safety rails (dangerous commands still
require confirmation) as every other automation entry point.
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

from jarvis.utils.async_utils import fire_and_forget

if TYPE_CHECKING:
    from jarvis.services.automation_service import AutomationService


class DeveloperConsoleView(QWidget):
    def __init__(
        self, automation_service: AutomationService | None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._automation = automation_service

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(10)

        title = QLabel("Developer Console")
        title.setObjectName("greetingTitle")
        outer.addWidget(title)

        subtitle = QLabel(
            "Runs real automation commands through the same engine voice/chat use "
            "(dangerous actions still ask for confirmation)."
        )
        subtitle.setObjectName("rowSubtitle")
        subtitle.setWordWrap(True)
        outer.addWidget(subtitle)

        self._output = QPlainTextEdit()
        self._output.setObjectName("updateTerminalLog")
        self._output.setReadOnly(True)
        outer.addWidget(self._output, 1)

        row = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setPlaceholderText("> take screenshot / open calculator / create folder Test")
        self._input.returnPressed.connect(self._run)
        row.addWidget(self._input, 1)
        run_btn = QPushButton("Run")
        run_btn.setProperty("variant", "primary")
        run_btn.clicked.connect(self._run)
        row.addWidget(run_btn)
        outer.addLayout(row)

    def _run(self) -> None:
        command = self._input.text().strip()
        if not command:
            return
        self._input.clear()
        self._output.appendPlainText(f"> {command}")
        if self._automation is None:
            self._output.appendPlainText("(automation service unavailable in this context)")
            return
        fire_and_forget(self._run_async(command))

    async def _run_async(self, command: str) -> None:
        try:
            result = await self._automation.run_command(command)
            for step in result.step_results:
                self._output.appendPlainText(
                    f"  [{step.action.value}] {step.status.value}"
                    + (f" -- {step.error}" if step.error else "")
                )
        except Exception as err:
            self._output.appendPlainText(f"  error: {err}")
