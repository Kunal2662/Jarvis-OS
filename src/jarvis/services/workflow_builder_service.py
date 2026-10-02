"""Workflow Builder service -- M7 Workflow Builder.

The single, DI-registered orchestration entry point for standalone
workflow authoring, mirroring how ``HomeAutomationService`` fronts
event-triggered automation and ``ScheduleService`` fronts time-triggered
automation. See ``docs/M7_WORKFLOW_BUILDER_LOGIC_CONTRACT.md`` for the
full design -- this docstring only summarizes the load-bearing
decisions:

**Standalone, never trigger-owned (§6).** A ``WorkflowDefinition`` row
created here is never referenced by a ``Schedule`` or
``AutomationTrigger``, and vice versa -- the two universes do not
intersect in this MVP. Attaching a Workflow-Builder-authored workflow
to a new Schedule or Automation Trigger is explicitly deferred (§19).

**Execution is delegated, not duplicated (§9).** The only execution
path is manual: ``run_workflow`` fetches the workflow, creates a
``queued`` execution row, and calls the shared
:class:`~jarvis.services.workflow_execution_service.WorkflowExecutionService`
-- the identical call path ``ScheduleService``/``HomeAutomationService``
already use -- awaited synchronously, since a manual caller expects to
wait for the result. No background dispatch, no ``EventBus``
subscription, no concurrency semaphore of its own -- there is no
trigger, so no burst-of-events scenario to guard against.

**Confirmation policy (§12, Policy A): always deny.** No ``confirm``
callback is supplied anywhere in this module -- zero new authorization
code.

**Permission separation (§11), mirroring both sibling services'
own:** ``WORKFLOW_BUILDER_PRINCIPAL``/``WORKFLOW_BUILDER_SCOPE`` gate
CRUD on ``WorkflowDefinition``/``WorkflowBuilderExecution`` rows only.
They never grant permission to execute a step's own underlying action
-- that is independently, separately re-evaluated at execution time by
whichever existing gate already governs that step kind, every time,
with no caching.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from jarvis.core.exceptions import ServiceError
from jarvis.core.logging.logger import get_logger
from jarvis.domain.workflow.models import WorkflowStepKind
from jarvis.infrastructure.database.repositories.schedule_repository import WorkflowRepository
from jarvis.infrastructure.database.repositories.workflow_builder_repository import (
    WorkflowBuilderExecutionRepository,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from jarvis.core.interfaces.database import IDatabase
    from jarvis.core.plugins.permissions import PermissionModel
    from jarvis.infrastructure.database.models import WorkflowBuilderExecution, WorkflowDefinition
    from jarvis.services.workflow_execution_service import WorkflowExecutionService

_logger = get_logger("jarvis.services.workflow_builder")

#: The `PermissionModel` identity this module declares and checks
#: against -- mirrors `HomeAutomationService`'s exact naming
#: convention. Governs CRUD on this module's own resources only; never
#: implies permission to execute a step's underlying action (see
#: module docstring).
WORKFLOW_BUILDER_PRINCIPAL = "core:workflow_builder"

#: Added to `core/plugins/sdk.py`'s `PERMISSION_SCOPES` this phase.
WORKFLOW_BUILDER_SCOPE = "workflow_builder"


class WorkflowBuilderPermissionError(ServiceError):
    """Raised by `_require_permission()` specifically -- a distinct
    subclass, matching `HomeAutomationPermissionError`'s own
    precedent, so the REST route can tell "not granted" apart from
    "not found" by exception type."""


class WorkflowNotFoundError(ServiceError):
    """A distinct subclass so the REST route can map this to 404
    specifically, matching `AutomationTriggerNotFoundError`'s own
    precedent."""


def _aware_utc(value: datetime) -> datetime:
    """SQLite round-trips a stored timestamp naive -- see
    `schedule_service._aware_utc`'s identical reasoning. This module
    keeps its own copy rather than importing a private helper across
    services."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _metadata_or_empty(raw: str | None) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def _validate_step(step: dict[str, Any]) -> dict[str, Any]:
    """Structural validation only -- mirrors
    `schedule_service._validate_step`/`home_automation_service.
    _validate_step` exactly (same error messages, same behavior); kept
    as a local copy rather than a cross-service import of a private
    helper. Does not resolve whether an `instruction` parses or a
    `tool_name` is registered (Logic Contract §8)."""
    kind = step.get("kind")
    if kind not in (WorkflowStepKind.AUTOMATION.value, WorkflowStepKind.AGENT_TOOL.value):
        raise ServiceError(
            f"Workflow step 'kind' must be {WorkflowStepKind.AUTOMATION.value!r} or "
            f"{WorkflowStepKind.AGENT_TOOL.value!r}, got {kind!r}."
        )
    if kind == WorkflowStepKind.AUTOMATION.value:
        instruction = step.get("instruction")
        if not isinstance(instruction, str) or not instruction.strip():
            raise ServiceError("An 'automation' step requires a non-empty 'instruction'.")
    else:
        tool_name = step.get("tool_name")
        if not isinstance(tool_name, str) or not tool_name.strip():
            raise ServiceError("An 'agent_tool' step requires a non-empty 'tool_name'.")
    return {
        "id": str(step.get("id") or ""),
        "kind": kind,
        "instruction": str(step.get("instruction") or ""),
        "tool_name": str(step.get("tool_name") or ""),
        "tool_args": dict(step.get("tool_args") or {}),
        "depends_on": list(step.get("depends_on") or []),
        "label": str(step.get("label") or ""),
    }


def _validate_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not steps:
        raise ServiceError("A workflow requires at least one step.")
    return [_validate_step(s) for s in steps]


class WorkflowBuilderService:
    def __init__(
        self,
        *,
        database: IDatabase,
        permissions: PermissionModel,
        workflow_executor: WorkflowExecutionService,
    ) -> None:
        self._db = database
        self._permissions = permissions
        self._workflow_executor = workflow_executor
        self._permissions.declare(WORKFLOW_BUILDER_PRINCIPAL, [WORKFLOW_BUILDER_SCOPE])

    # ------------------------------------------------------------------
    # Permission
    # ------------------------------------------------------------------
    def _require_permission(self) -> None:
        if not self._permissions.is_granted(WORKFLOW_BUILDER_PRINCIPAL, WORKFLOW_BUILDER_SCOPE):
            raise WorkflowBuilderPermissionError(
                "Workflow Builder management requires the "
                f"{WORKFLOW_BUILDER_SCOPE!r} permission to be granted for "
                f"{WORKFLOW_BUILDER_PRINCIPAL!r}. Grant it via POST "
                f"/api/v1/plugins/{WORKFLOW_BUILDER_PRINCIPAL}/permissions/"
                f"{WORKFLOW_BUILDER_SCOPE}/grant."
            )

    # ------------------------------------------------------------------
    # Workflow CRUD
    # ------------------------------------------------------------------
    async def create_workflow(
        self,
        *,
        name: str,
        steps: list[dict[str, Any]],
        description: str = "",
    ) -> dict[str, Any]:
        self._require_permission()
        if not name.strip():
            raise ServiceError("A workflow requires a non-empty 'name'.")
        validated_steps = _validate_steps(steps)

        async with self._db.session() as sess:
            sess = cast("AsyncSession", sess)
            workflow = await WorkflowRepository(sess).add(
                name=name, description=description, steps_json=json.dumps(validated_steps)
            )
        _logger.info("Workflow {} created.", workflow.id)
        return self._workflow_payload(workflow)

    async def get_workflow(self, workflow_id: str) -> dict[str, Any]:
        self._require_permission()
        async with self._db.session() as sess:
            sess = cast("AsyncSession", sess)
            workflow = await WorkflowRepository(sess).get(workflow_id)
            if workflow is None:
                raise WorkflowNotFoundError(f"Workflow {workflow_id!r} does not exist.")
        return self._workflow_payload(workflow)

    async def list_workflows(self) -> list[dict[str, Any]]:
        self._require_permission()
        async with self._db.session() as sess:
            sess = cast("AsyncSession", sess)
            workflows = await WorkflowRepository(sess).list_all()
        return [self._workflow_payload(w) for w in workflows]

    async def update_workflow(
        self,
        workflow_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        steps: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        self._require_permission()
        if name is not None and not name.strip():
            raise ServiceError("A workflow's 'name' cannot be blank.")
        steps_json = json.dumps(_validate_steps(steps)) if steps is not None else None

        async with self._db.session() as sess:
            sess = cast("AsyncSession", sess)
            workflow = await WorkflowRepository(sess).update(
                workflow_id, name=name, description=description, steps_json=steps_json
            )
            if workflow is None:
                raise WorkflowNotFoundError(f"Workflow {workflow_id!r} does not exist.")
        return self._workflow_payload(workflow)

    async def delete_workflow(self, workflow_id: str) -> bool:
        self._require_permission()
        async with self._db.session() as sess:
            sess = cast("AsyncSession", sess)
            deleted = await WorkflowRepository(sess).delete(workflow_id)
        if not deleted:
            raise WorkflowNotFoundError(f"Workflow {workflow_id!r} does not exist.")
        return True

    async def list_executions(self, workflow_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        self._require_permission()
        async with self._db.session() as sess:
            sess = cast("AsyncSession", sess)
            workflow = await WorkflowRepository(sess).get(workflow_id)
            if workflow is None:
                raise WorkflowNotFoundError(f"Workflow {workflow_id!r} does not exist.")
            executions = await WorkflowBuilderExecutionRepository(sess).list_for_workflow(
                workflow_id, limit=limit
            )
        return [self._execution_payload(e) for e in executions]

    async def run_workflow(self, workflow_id: str) -> dict[str, Any]:
        """Manual run -- the only execution path (Logic Contract §9):
        no trigger exists to fire this any other way. Does not
        pre-authorize or bypass action-level permission/confirmation
        in any way; a confirm-required or permission-denied step is
        denied exactly as it would be for Scheduler/Home Automation."""
        self._require_permission()
        async with self._db.session() as sess:
            sess = cast("AsyncSession", sess)
            workflow = await WorkflowRepository(sess).get(workflow_id)
            if workflow is None:
                raise WorkflowNotFoundError(f"Workflow {workflow_id!r} does not exist.")
            steps = _metadata_or_empty(workflow.steps_json)
            execution = await WorkflowBuilderExecutionRepository(sess).add(
                workflow_id=workflow_id, status="queued"
            )

        status, error, step_results = await self._workflow_executor.run_workflow(steps)

        async with self._db.session() as sess:
            sess = cast("AsyncSession", sess)
            finished = await WorkflowBuilderExecutionRepository(sess).finish(
                execution.id,
                status=status,
                error=error,
                step_results_json=json.dumps(step_results),
                finished_at=datetime.now(UTC),
            )
        assert finished is not None
        return self._execution_payload(finished)

    # ------------------------------------------------------------------
    # Payload builders
    # ------------------------------------------------------------------
    def _workflow_payload(self, workflow: WorkflowDefinition) -> dict[str, Any]:
        return {
            "id": workflow.id,
            "name": workflow.name,
            "description": workflow.description,
            "steps": _metadata_or_empty(workflow.steps_json),
            "created_at": _aware_utc(workflow.created_at).isoformat(),
        }

    def _execution_payload(self, execution: WorkflowBuilderExecution) -> dict[str, Any]:
        return {
            "id": execution.id,
            "workflow_id": execution.workflow_id,
            "source": execution.source,
            "status": execution.status,
            "started_at": _aware_utc(execution.started_at).isoformat(),
            "finished_at": (
                _aware_utc(execution.finished_at).isoformat() if execution.finished_at else None
            ),
            "error": execution.error,
            "step_results": _metadata_or_empty(execution.step_results_json),
        }
