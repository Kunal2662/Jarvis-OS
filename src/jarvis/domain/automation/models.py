"""Domain value objects for the AI Automation Engine (Milestone 4).

Pure data — no imports from ``infrastructure``, ``services`` or ``core.di``.
Keeping these framework-free means the parser/planner can be unit tested
with zero mocking and the same types can flow from voice -> parser ->
planner -> executor -> history without translation layers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4


def _uuid() -> str:
    return uuid4().hex


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ActionType(str, Enum):
    """Every action the automation engine knows how to execute.

    Adding a new action means: add the member here, add an ``ActionType ->
    phrase`` rule in :mod:`jarvis.features.automation.parser`, and register
    a :class:`~jarvis.infrastructure.automation.actions.base.BaseAction`
    implementation in
    :mod:`jarvis.infrastructure.automation.actions.registry`.
    """

    OPEN_APP = "open_app"
    CLOSE_APP = "close_app"
    LAUNCH_URL = "launch_url"
    SEARCH_GOOGLE = "search_google"
    SEARCH_YOUTUBE = "search_youtube"
    SCREENSHOT = "screenshot"
    CLIPBOARD_COPY = "clipboard_copy"
    CLIPBOARD_PASTE = "clipboard_paste"
    CREATE_FOLDER = "create_folder"
    DELETE_FOLDER = "delete_folder"
    RENAME = "rename"
    MOVE = "move"
    COPY = "copy"
    OPEN_EXPLORER = "open_explorer"
    OPEN_DOWNLOADS = "open_downloads"
    OPEN_DOCUMENTS = "open_documents"
    EMPTY_RECYCLE_BIN = "empty_recycle_bin"
    SET_VOLUME = "set_volume"
    MUTE = "mute"
    SET_BRIGHTNESS = "set_brightness"
    SHUTDOWN = "shutdown"
    RESTART = "restart"
    SLEEP = "sleep"
    LOCK_PC = "lock_pc"
    OPEN_SETTINGS = "open_settings"
    TERMINAL_COMMAND = "terminal_command"
    UNKNOWN = "unknown"


class RiskLevel(str, Enum):
    """Coarse risk classification produced by the safety validator."""

    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PermissionDecision(str, Enum):
    """Outcome of :class:`~jarvis.features.automation.permission.PermissionGate`."""

    ALLOW = "allow"
    REQUIRE_CONFIRMATION = "require_confirmation"
    DENY = "deny"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    SKIPPED = "skipped"
    DENIED = "denied"


@dataclass(frozen=True, slots=True)
class Intent:
    """Structured meaning extracted from one natural-language instruction."""

    action: ActionType
    target: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""
    confidence: float = 1.0


@dataclass(slots=True)
class Step:
    """One executable unit inside an :class:`ExecutionPlan`."""

    action: ActionType
    args: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=_uuid)
    depends_on: list[str] = field(default_factory=list)
    max_retries: int = 0
    status: StepStatus = StepStatus.PENDING
    label: str = ""
    # Audit fix (Milestones 0-5 completion audit): safety-net timeout for
    # this step's execution. ``None`` (the default -- backward compatible
    # with every existing caller) falls back to the executor's own
    # default. A handful of action types (e.g. shell commands) already
    # enforce their own inner timeout; this is the *outer* guarantee that
    # every action type gets one, even ones that don't implement their
    # own (browser clicks, desktop mouse/keyboard, clipboard, file ops).
    timeout_seconds: float | None = None


@dataclass(slots=True)
class ExecutionPlan:
    """An ordered (possibly branching) set of steps derived from one instruction."""

    id: str = field(default_factory=_uuid)
    raw_text: str = ""
    steps: list[Step] = field(default_factory=list)
    created_at: datetime = field(default_factory=_utcnow)


@dataclass(slots=True)
class StepResult:
    step_id: str
    action: ActionType
    status: StepStatus
    output: Any = None
    error: str | None = None
    duration_ms: float = 0.0
    attempts: int = 1


@dataclass(slots=True)
class PlanResult:
    plan_id: str
    step_results: list[StepResult] = field(default_factory=list)

    @property
    def succeeded(self) -> bool:
        return bool(self.step_results) and all(
            r.status == StepStatus.SUCCEEDED for r in self.step_results
        )

    @property
    def failed_steps(self) -> list[StepResult]:
        return [r for r in self.step_results if r.status == StepStatus.FAILED]


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """One safety concern raised about an :class:`Intent`."""

    risk: RiskLevel
    reason: str


@dataclass(frozen=True, slots=True)
class UndoRecord:
    """Enough information to reverse one already-executed step."""

    step_id: str
    action: ActionType
    undo_args: dict[str, Any]
    id: str = field(default_factory=_uuid)
    created_at: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True, slots=True)
class TaskRecord:
    """One row of persisted automation task history."""

    action: ActionType
    target: str | None
    status: StepStatus
    id: str = field(default_factory=_uuid)
    args_json: str = "{}"
    result: str | None = None
    error: str | None = None
    duration_ms: float = 0.0
    created_at: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True, slots=True)
class Recipe:
    """A named, reusable sequence of natural-language instructions."""

    name: str
    steps: list[str]
    description: str = ""
