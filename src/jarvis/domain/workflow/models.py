"""Domain value objects for Workflow Intelligence (Milestone 7).

Pure data -- no imports from ``infrastructure``, ``services``, ``agents``
or ``core.di`` -- mirroring :mod:`jarvis.domain.automation.models`, which
these types deliberately sit alongside rather than replace. Phase 1 only:
these are declared now so Phases 2-7 (parallel dispatch, the Workflow
Builder, the Recorder, and the Scheduler) have a stable shape to build
against; nothing yet constructs, persists, or executes them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4


def _uuid() -> str:
    return uuid4().hex


def _utcnow() -> datetime:
    return datetime.now(UTC)


class WorkflowStepKind(StrEnum):
    """What a :class:`WorkflowStep` does when it runs.

    A workflow step is either an existing Milestone 4 automation
    instruction, or an agent-tool invocation. Modelled as a discriminated
    union via this enum -- rather than two separate step classes -- so
    :class:`WorkflowStep` stays one type that dependency-graph-based
    scheduling (Phase 2) can treat uniformly, matching how
    :class:`jarvis.domain.automation.models.Step` is one type regardless
    of which :class:`~jarvis.domain.automation.models.ActionType` it
    carries.
    """

    AUTOMATION = "automation"
    AGENT_TOOL = "agent_tool"


class ScheduleKind(StrEnum):
    """How a :class:`ScheduleDefinition` computes its next fire time."""

    INTERVAL = "interval"
    CRON = "cron"


@dataclass(slots=True)
class WorkflowStep:
    """One executable unit inside a :class:`WorkflowDefinition`.

    Deliberately shaped like
    :class:`jarvis.domain.automation.models.Step` (``id``, ``depends_on``,
    ``label``) so Phase 2's dependency-graph/parallel-dispatch logic --
    already correct for automation ``Step``s, just not yet used for
    parallel dispatch -- applies here without a second, parallel
    implementation.
    """

    kind: WorkflowStepKind
    id: str = field(default_factory=_uuid)
    # Populated when kind is AUTOMATION: the same natural-language
    # instruction line jarvis.features.automation.planner already parses
    # (one Recipe step == one WorkflowStep with this set).
    instruction: str = ""
    # Populated when kind is AGENT_TOOL: which registered agent tool
    # (see agents/tools/registry.py) to invoke, and with what arguments.
    tool_name: str = ""
    tool_args: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    label: str = ""


@dataclass(slots=True)
class WorkflowDefinition:
    """A named, persistable sequence of :class:`WorkflowStep`.

    The Workflow Builder's (Phase 4) unit of authoring and storage, and
    the Automation Recorder / Macro Engine's (Phase 5) output shape.
    Conceptually sits next to
    :class:`jarvis.domain.automation.models.Recipe` -- ``Recipe`` remains
    the pure-automation, agent-free case; a ``WorkflowDefinition`` is the
    superset that can also contain agent-tool steps.
    """

    name: str
    steps: list[WorkflowStep] = field(default_factory=list)
    description: str = ""
    id: str = field(default_factory=_uuid)
    created_at: datetime = field(default_factory=_utcnow)


@dataclass(slots=True)
class ScheduleDefinition:
    """When a :class:`WorkflowDefinition` should run unattended.

    Pure data -- Phase 6's ``Scheduler`` is the pure next-fire-time logic
    that will consume this; nothing here does I/O or owns a clock.
    """

    workflow_id: str
    kind: ScheduleKind = ScheduleKind.INTERVAL
    # Populated when kind is INTERVAL.
    interval_seconds: float = 0.0
    # Populated when kind is CRON (5-field cron expression).
    cron_expression: str = ""
    enabled: bool = True
    id: str = field(default_factory=_uuid)
    created_at: datetime = field(default_factory=_utcnow)
    last_fired_at: datetime | None = None
