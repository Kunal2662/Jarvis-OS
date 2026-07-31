"""Agent Trace panel -- Milestone 5-Agents, Developer Mode section.

Lets a developer run an ad-hoc prompt through the real
``AgentOrchestrator`` and watch each graph step (planner -> tool-selector
-> tool-executor -> critic -> responder) arrive live via
``AgentStepEvent`` on the shared ``EventBus``, plus the final answer.
Event-bus push rather than a polling ``QTimer`` — same reasoning as
``VoiceStateChangedEvent``/``UpdatePhaseEvent`` subscribers elsewhere in
this UI: steps happen when they happen, not on a fixed cadence.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from jarvis.core.events.events import AgentStepEvent
from jarvis.core.interfaces.agent import AgentRequest
from jarvis.core.logging.logger import get_logger
from jarvis.ui.components import SectionCard, StatusBadge
from jarvis.utils.async_utils import fire_and_forget

if TYPE_CHECKING:
    from jarvis.core.di.container import Container

_logger = get_logger("jarvis.ui.developer.agent_trace")

_MAX_TRACE_ROWS = 200


class AgentTraceView(QWidget):
    def __init__(self, container: Container, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._container = container

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(14)

        title = QLabel("Agent Trace")
        title.setObjectName("greetingTitle")
        outer.addWidget(title)

        run_card = SectionCard("Run a prompt through AgentOrchestrator")
        row = QHBoxLayout()
        self._prompt_input = QLineEdit()
        self._prompt_input.setPlaceholderText(
            "e.g. Search for today's weather and remember my preference"
        )
        self._prompt_input.returnPressed.connect(self._on_run)
        self._run_btn = QPushButton("Run")
        self._run_btn.clicked.connect(self._on_run)
        row.addWidget(self._prompt_input, 1)
        row.addWidget(self._run_btn)
        run_card.body.addLayout(row)
        self._status_badge = StatusBadge("Idle", "neutral")
        run_card.body.addWidget(self._status_badge)
        outer.addWidget(run_card)

        trace_card = SectionCard("Step Trace")
        self._trace_list = QListWidget()
        trace_card.body.addWidget(self._trace_list)
        outer.addWidget(trace_card, 1)

        response_card = SectionCard("Final Response")
        self._response_view = QTextEdit()
        self._response_view.setReadOnly(True)
        response_card.body.addWidget(self._response_view)
        outer.addWidget(response_card)

        event_bus = self._container.event_bus()
        self._unsubscribe = event_bus.subscribe(AgentStepEvent, self._on_step_event)
        self.destroyed.connect(self._on_destroyed)

    # ------------------------------------------------------------------
    def _on_destroyed(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

    def _on_run(self) -> None:
        prompt = self._prompt_input.text().strip()
        if not prompt:
            return
        self._trace_list.clear()
        self._response_view.clear()
        self._status_badge.set_state("warning", "Running…")
        self._run_btn.setEnabled(False)
        fire_and_forget(self._run(prompt))

    async def _run(self, prompt: str) -> None:
        orchestrator = self._container.agent_orchestrator()
        try:
            response = await orchestrator.invoke(AgentRequest(prompt=prompt))
            self._response_view.setPlainText(response.text or "(empty response)")
            self._status_badge.set_state("success", f"Done ({response.steps} step(s))")
        except Exception as err:
            _logger.exception("Agent Trace run failed.")
            self._response_view.setPlainText(f"Error: {err}")
            self._status_badge.set_state("error", "Error")
        finally:
            self._run_btn.setEnabled(True)

    def _on_step_event(self, event: AgentStepEvent) -> None:
        label = f"[{event.step}] {event.node or '…'} — {event.status}"
        if event.detail:
            label += f": {event.detail[:120]}"
        self._trace_list.addItem(QListWidgetItem(label))
        while self._trace_list.count() > _MAX_TRACE_ROWS:
            self._trace_list.takeItem(0)
        self._trace_list.scrollToBottom()
