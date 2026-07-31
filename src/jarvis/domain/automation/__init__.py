"""Domain models for the AI Automation Engine (Milestone 4).

Everything in :mod:`jarvis.domain.automation` is a plain, framework-free
value object. Parser, planner, executor, validator, permission, undo,
history and recipe modules all depend on these types; nothing here
depends on them back.
"""

from __future__ import annotations

from jarvis.domain.automation.models import (
    ActionType,
    ExecutionPlan,
    Intent,
    PermissionDecision,
    PlanResult,
    Recipe,
    RiskLevel,
    Step,
    StepResult,
    StepStatus,
    TaskRecord,
    UndoRecord,
    ValidationIssue,
)

__all__ = [
    "ActionType",
    "ExecutionPlan",
    "Intent",
    "PermissionDecision",
    "PlanResult",
    "Recipe",
    "RiskLevel",
    "Step",
    "StepResult",
    "StepStatus",
    "TaskRecord",
    "UndoRecord",
    "ValidationIssue",
]
