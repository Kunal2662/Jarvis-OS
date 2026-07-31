"""Domain models for Workflow Intelligence (Milestone 7).

Everything in :mod:`jarvis.domain.workflow` is a plain, framework-free
value object, mirroring :mod:`jarvis.domain.automation`. Phase 1 only --
declared now so later M7 phases (builder, recorder, scheduler) have a
stable shape to build against.
"""

from __future__ import annotations

from jarvis.domain.workflow.models import (
    ScheduleDefinition,
    ScheduleKind,
    WorkflowDefinition,
    WorkflowStep,
    WorkflowStepKind,
)

__all__ = [
    "ScheduleDefinition",
    "ScheduleKind",
    "WorkflowDefinition",
    "WorkflowStep",
    "WorkflowStepKind",
]
