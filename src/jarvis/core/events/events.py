"""Domain events published on the in-process :class:`EventBus`.

Concrete event types will be added by feature milestones. All events must
inherit from :class:`Event` so subscribers can filter by type.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class Event:
    """Base class for every event published on the bus."""

    id: str = field(default_factory=lambda: uuid4().hex)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


# --- Application Lifecycle (Milestone 9, Runtime Core) ----------------------
@dataclass(frozen=True, slots=True)
class AppReadyEvent(Event):
    """Published by :class:`~jarvis.app.ApplicationBootstrapper` once every
    registered ``RuntimeManager`` startup hook has run (``_run_gui``)."""


@dataclass(frozen=True, slots=True)
class ShutdownRequestedEvent(Event):
    """Published by :meth:`~jarvis.ui.main_window.MainWindow._graceful_quit`
    before ``RuntimeManager.shutdown()`` releases any real resource."""


@dataclass(frozen=True, slots=True)
class VoiceStateChangedEvent(Event):
    """Fired whenever the voice pipeline's state machine transitions."""

    state: str = "idle"
    detail: str = ""


@dataclass(frozen=True, slots=True)
class AutomationStepEvent(Event):
    """Fired by the AI Automation Engine after every step attempt (Milestone 4)."""

    step_id: str = ""
    action: str = ""
    status: str = ""


@dataclass(frozen=True, slots=True)
class UpdatePhaseEvent(Event):
    """Fired by the (mock) Update Center pipeline on every phase transition
    (Milestone 5). Drives the sidebar progress indicator, the Update
    Terminal's live log feed, and AI voice announcements."""

    session_id: str = ""
    phase: str = "idle"
    progress_percent: int = 0
    message: str = ""


@dataclass(frozen=True, slots=True)
class AgentStepEvent(Event):
    """Fired by :class:`~jarvis.agents.orchestrator.AgentOrchestrator` after
    every LangGraph node transition (Milestone 5-Agents). Drives the
    Developer Mode Agent Trace panel; not persisted anywhere."""

    thread_id: str = ""
    step: int = 0
    node: str = ""
    status: str = "ok"
    detail: str = ""


@dataclass(frozen=True, slots=True)
class VisionProviderStatusEvent(Event):
    """Reports a vision/OCR provider's health (Milestone 6, Phase 4). Not
    yet published anywhere -- no provider does real capture/OCR work, so
    there is nothing to report a status change *from*. Defined now so
    future phases can publish it without touching this file again."""

    provider: str = ""
    healthy: bool = False
    detail: str = ""


@dataclass(frozen=True, slots=True)
class WorkflowStepEvent(Event):
    """Fired after every WorkflowStep attempt (Milestone 7). Not yet
    published anywhere -- no workflow executes until Phase 4 (Workflow
    Builder) wires a WorkflowDefinition through the same execution path
    AutomationStepEvent already drives. Defined now, mirroring
    AutomationStepEvent's shape, so future phases can publish it without
    touching this file again."""

    workflow_id: str = ""
    step_id: str = ""
    status: str = ""


@dataclass(frozen=True, slots=True)
class ScheduledJobFiredEvent(Event):
    """Fired when the Scheduler (Milestone 7, Phase 6) dispatches a due
    job. Not yet published anywhere -- no scheduler loop exists until
    Phase 6. Defined now so future phases can publish it without
    touching this file again."""

    schedule_id: str = ""
    workflow_id: str = ""
    status: str = ""
