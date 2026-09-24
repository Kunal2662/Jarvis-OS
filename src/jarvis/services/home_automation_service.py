"""Home Automation service -- M7 (event-based triggers).

The single, DI-registered orchestration entry point for event-triggered
automation, mirroring how ``ScheduleService`` fronts time-triggered
automation. See ``docs/M7_HOME_AUTOMATION_LOGIC_CONTRACT.md`` for the
full design -- this docstring only summarizes the load-bearing
decisions:

**Confirmation policy (§18, Policy A): always deny.** Every dispatched
step is executed through the shared
:class:`~jarvis.services.workflow_execution_service.WorkflowExecutionService`
-- the identical call path ``ScheduleService`` already uses -- with no
``confirm`` callback supplied anywhere in this module. Both existing
gates (``PermissionGate``, ``AgentPermissionGate``) already fail-safe
to a denial with no callback; this service adds **zero** new
authorization code.

**Event source, not a second EventBus (§4/§25).** Subscribes to the
existing ``EventBus`` for ``DeviceStateChangedEvent`` only -- no new
transport, no connector coupling, no MQTT/Home-Assistant-native event
handling.

**Dispatch does not block the event publisher.** The event handler
does the (cheap) trigger-matching query synchronously, then schedules
each matched trigger's actual dispatch as a background
``asyncio.Task`` -- so ``SmartHomeService.report_device_state()``'s
own ``EventBus.publish()`` call (and therefore whatever REST/agent
caller triggered the underlying refresh) is never blocked waiting for
a workflow to finish running. Manual runs (``run_automation``) are the
one exception: dispatched synchronously, since a manual caller
reasonably expects to wait for the result.

**Permission separation (§17 -- the most important design rule in this
file, mirroring ``ScheduleService``'s own):**
``HOME_AUTOMATION_PRINCIPAL``/``HOME_AUTOMATION_SCOPE`` gate CRUD on
AutomationTrigger/AutomationExecution rows only. They never grant
permission to execute a triggered step's own underlying action -- that
is independently, separately re-evaluated at execution time by
whichever existing gate already governs that step kind, every time,
with no caching.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from jarvis.core.events.events import DeviceStateChangedEvent
from jarvis.core.exceptions import ServiceError
from jarvis.core.logging.logger import get_logger
from jarvis.domain.workflow.models import WorkflowStepKind
from jarvis.infrastructure.database.repositories.automation_repository import (
    AutomationExecutionRepository,
    AutomationTriggerRepository,
)
from jarvis.infrastructure.database.repositories.schedule_repository import WorkflowRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from jarvis.core.config.settings import Settings
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.interfaces.database import IDatabase
    from jarvis.core.plugins.permissions import PermissionModel
    from jarvis.infrastructure.database.models import AutomationExecution, AutomationTrigger
    from jarvis.services.workflow_execution_service import WorkflowExecutionService

_logger = get_logger("jarvis.services.home_automation")

#: The `PermissionModel` identity this module declares and checks
#: against -- mirrors `ScheduleService`'s exact naming convention.
#: Governs CRUD on this module's own resources only; never implies
#: permission to execute a triggered step's underlying action (see
#: module docstring).
HOME_AUTOMATION_PRINCIPAL = "core:home_automation"

#: Added to `core/plugins/sdk.py`'s `PERMISSION_SCOPES` this phase.
HOME_AUTOMATION_SCOPE = "home_automation"

_TERMINAL_STATUSES = frozenset(
    {"succeeded", "partially_failed", "failed", "cancelled", "skipped", "denied"}
)


class HomeAutomationPermissionError(ServiceError):
    """Raised by `_require_permission()` specifically -- a distinct
    subclass, matching `SchedulerPermissionError`'s own precedent, so
    the REST route can tell "not granted" apart from "not found" by
    exception type."""


class AutomationTriggerNotFoundError(ServiceError):
    """A distinct subclass so the REST route can map this to 404
    specifically, matching `ScheduleNotFoundError`'s own precedent."""


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
    `schedule_service._validate_step` exactly (same error messages,
    same behavior); kept as a local copy rather than a cross-service
    import of a private helper. Home Automation is not a workflow
    authoring surface either -- it does not resolve whether an
    `instruction` parses or a `tool_name` is registered."""
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


class HomeAutomationService:
    def __init__(
        self,
        *,
        database: IDatabase,
        permissions: PermissionModel,
        settings: Settings,
        event_bus: EventBus,
        workflow_executor: WorkflowExecutionService,
    ) -> None:
        self._db = database
        self._permissions = permissions
        self._settings = settings
        self._event_bus = event_bus
        self._workflow_executor = workflow_executor
        self._permissions.declare(HOME_AUTOMATION_PRINCIPAL, [HOME_AUTOMATION_SCOPE])

        self._semaphore = asyncio.Semaphore(
            max(1, settings.home_automation.max_concurrent_executions)
        )
        self._unsubscribe: Any | None = None
        self._dispatch_tasks: set[asyncio.Task[Any]] = set()

    # ------------------------------------------------------------------
    # Permission
    # ------------------------------------------------------------------
    def _require_permission(self) -> None:
        if not self._permissions.is_granted(HOME_AUTOMATION_PRINCIPAL, HOME_AUTOMATION_SCOPE):
            raise HomeAutomationPermissionError(
                "Home Automation management requires the "
                f"{HOME_AUTOMATION_SCOPE!r} permission to be granted for "
                f"{HOME_AUTOMATION_PRINCIPAL!r}. Grant it via POST "
                f"/api/v1/plugins/{HOME_AUTOMATION_PRINCIPAL}/permissions/"
                f"{HOME_AUTOMATION_SCOPE}/grant."
            )

    # ------------------------------------------------------------------
    # Automation CRUD
    # ------------------------------------------------------------------
    async def create_automation(
        self,
        *,
        name: str,
        device_id: str,
        to_status: str,
        steps: list[dict[str, Any]],
        from_status: str = "",
        description: str = "",
        enabled: bool = True,
    ) -> dict[str, Any]:
        self._require_permission()
        if not name.strip():
            raise ServiceError("An automation requires a non-empty 'name'.")
        if not device_id.strip():
            raise ServiceError("An automation requires a non-empty 'device_id'.")
        if not to_status.strip():
            raise ServiceError("An automation requires a non-empty 'to_status'.")
        if not steps:
            raise ServiceError("An automation's workflow requires at least one step.")
        validated_steps = [_validate_step(s) for s in steps]

        async with self._db.session() as sess:
            sess = cast("AsyncSession", sess)
            workflow = await WorkflowRepository(sess).add(
                name=name, description=description, steps_json=json.dumps(validated_steps)
            )
            trigger = await AutomationTriggerRepository(sess).add(
                workflow_id=workflow.id,
                device_id=device_id,
                to_status=to_status,
                from_status=from_status,
                enabled=enabled,
            )
        _logger.info("Automation trigger {} created for workflow {}.", trigger.id, workflow.id)
        return self._trigger_payload(trigger, workflow_name=name)

    async def get_automation(self, trigger_id: str) -> dict[str, Any]:
        self._require_permission()
        async with self._db.session() as sess:
            sess = cast("AsyncSession", sess)
            trigger = await AutomationTriggerRepository(sess).get(trigger_id)
            if trigger is None:
                raise AutomationTriggerNotFoundError(f"Automation {trigger_id!r} does not exist.")
            workflow = await WorkflowRepository(sess).get(trigger.workflow_id)
            latest_execution = None
            if trigger.last_execution_id:
                latest_execution = await AutomationExecutionRepository(sess).get(
                    trigger.last_execution_id
                )
        payload = self._trigger_payload(trigger, workflow_name=workflow.name if workflow else "")
        if latest_execution is not None:
            payload["last_execution"] = self._execution_payload(latest_execution)
        return payload

    async def list_automations(self, *, enabled_only: bool = False) -> list[dict[str, Any]]:
        self._require_permission()
        async with self._db.session() as sess:
            sess = cast("AsyncSession", sess)
            triggers = await AutomationTriggerRepository(sess).list_triggers(
                enabled_only=enabled_only
            )
            workflow_repo = WorkflowRepository(sess)
            payloads = []
            for trigger in triggers:
                workflow = await workflow_repo.get(trigger.workflow_id)
                payloads.append(
                    self._trigger_payload(trigger, workflow_name=workflow.name if workflow else "")
                )
        return payloads

    async def enable_automation(self, trigger_id: str) -> dict[str, Any]:
        self._require_permission()
        async with self._db.session() as sess:
            sess = cast("AsyncSession", sess)
            trigger = await AutomationTriggerRepository(sess).set_enabled(trigger_id, enabled=True)
            if trigger is None:
                raise AutomationTriggerNotFoundError(f"Automation {trigger_id!r} does not exist.")
            workflow = await WorkflowRepository(sess).get(trigger.workflow_id)
        return self._trigger_payload(trigger, workflow_name=workflow.name if workflow else "")

    async def disable_automation(self, trigger_id: str) -> dict[str, Any]:
        self._require_permission()
        async with self._db.session() as sess:
            sess = cast("AsyncSession", sess)
            trigger = await AutomationTriggerRepository(sess).set_enabled(trigger_id, enabled=False)
            if trigger is None:
                raise AutomationTriggerNotFoundError(f"Automation {trigger_id!r} does not exist.")
            workflow = await WorkflowRepository(sess).get(trigger.workflow_id)
        return self._trigger_payload(trigger, workflow_name=workflow.name if workflow else "")

    async def delete_automation(self, trigger_id: str) -> bool:
        self._require_permission()
        async with self._db.session() as sess:
            sess = cast("AsyncSession", sess)
            trigger = await AutomationTriggerRepository(sess).get(trigger_id)
            if trigger is None:
                raise AutomationTriggerNotFoundError(f"Automation {trigger_id!r} does not exist.")
            workflow_id = trigger.workflow_id
            await AutomationTriggerRepository(sess).delete(trigger_id)
            # One dedicated WorkflowDefinition per automation (mirrors
            # Schedule's own precedent exactly) -- deleting the
            # automation deletes its own workflow row too, since
            # nothing else can reference it.
            await WorkflowRepository(sess).delete(workflow_id)
        return True

    async def list_executions(self, trigger_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        self._require_permission()
        async with self._db.session() as sess:
            sess = cast("AsyncSession", sess)
            trigger = await AutomationTriggerRepository(sess).get(trigger_id)
            if trigger is None:
                raise AutomationTriggerNotFoundError(f"Automation {trigger_id!r} does not exist.")
            executions = await AutomationExecutionRepository(sess).list_for_trigger(
                trigger_id, limit=limit
            )
        return [self._execution_payload(e) for e in executions]

    async def run_automation(self, trigger_id: str) -> dict[str, Any]:
        """Manual test execution (Logic Contract §20/§21) -- reuses the
        identical dispatch path a matched event uses, awaited
        synchronously so the caller sees the real outcome. Does not
        pre-authorize or bypass action-level permission/confirmation in
        any way; a confirm-required or permission-denied step inside
        this automation is denied exactly as it would be if
        event-triggered."""
        self._require_permission()
        async with self._db.session() as sess:
            sess = cast("AsyncSession", sess)
            trigger = await AutomationTriggerRepository(sess).get(trigger_id)
        if trigger is None:
            raise AutomationTriggerNotFoundError(f"Automation {trigger_id!r} does not exist.")
        execution = await self._dispatch(trigger_id, source="manual")
        if execution is None:
            # Already running, or inside the re-fire cooldown -- the
            # same silent-skip behavior an event-triggered match gets
            # (Logic Contract §14/§15). Report the trigger's current
            # state rather than fabricating a new execution.
            return await self.get_automation(trigger_id)
        return self._execution_payload(execution)

    # ------------------------------------------------------------------
    # Event subscription lifecycle
    # ------------------------------------------------------------------
    async def start(self) -> None:
        """Subscribe to DeviceStateChangedEvent. Idempotent."""
        if self._unsubscribe is not None:
            return
        self._unsubscribe = self._event_bus.subscribe(
            DeviceStateChangedEvent, self._on_device_state_changed
        )

    async def stop(self) -> None:
        """Unsubscribe and let any in-flight dispatch finish. Idempotent,
        safe even if never started."""
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        pending = list(self._dispatch_tasks)
        for task in pending:
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _on_device_state_changed(self, event: DeviceStateChangedEvent) -> None:
        """Matches the event against every enabled trigger for this
        device+transition, then schedules each match's dispatch as a
        background task -- deliberately not awaited here, so this
        handler (and therefore `EventBus.publish()`, and therefore
        whatever caller triggered the underlying refresh) returns
        quickly rather than blocking on workflow execution."""
        async with self._db.session() as sess:
            sess = cast("AsyncSession", sess)
            matches = await AutomationTriggerRepository(sess).list_matching(
                device_id=event.device_id,
                status=event.status,
                previous_status=event.previous_status,
            )
        for trigger in matches:
            task = asyncio.create_task(self._dispatch(trigger.id, source="event"))
            self._dispatch_tasks.add(task)
            task.add_done_callback(self._dispatch_tasks.discard)

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------
    async def _dispatch(self, trigger_id: str, *, source: str) -> AutomationExecution | None:
        async with self._db.session() as sess:
            sess = cast("AsyncSession", sess)
            trigger_repo = AutomationTriggerRepository(sess)
            execution_repo = AutomationExecutionRepository(sess)
            trigger = await trigger_repo.get(trigger_id)
            if trigger is None or not trigger.enabled:
                return None
            if await execution_repo.has_non_terminal(trigger_id):
                # Duplicate-fire prevention (Logic Contract §14) --
                # silent skip, no new row, mirroring
                # ScheduleService._dispatch's own has_non_terminal
                # early-return exactly.
                return None
            now = datetime.now(UTC)
            if trigger.last_fired_at is not None:
                elapsed = (now - _aware_utc(trigger.last_fired_at)).total_seconds()
                if elapsed < self._settings.home_automation.min_refire_interval_seconds:
                    # Loop/re-entrancy cooldown (Logic Contract §15) --
                    # same silent-skip behavior as duplicate-fire
                    # prevention above.
                    return None

            workflow = await WorkflowRepository(sess).get(trigger.workflow_id)
            steps = _metadata_or_empty(workflow.steps_json) if workflow else []
            execution = await execution_repo.add(
                automation_trigger_id=trigger_id,
                workflow_id=trigger.workflow_id,
                source=source,
                status="queued",
            )

        async with self._semaphore:
            # Re-check `enabled` fresh, right before executing --
            # mirrors ScheduleService._dispatch's own re-check-after-
            # acquiring-a-concurrency-slot pattern exactly.
            async with self._db.session() as sess:
                sess = cast("AsyncSession", sess)
                fresh = await AutomationTriggerRepository(sess).get(trigger_id)
                still_enabled = fresh is not None and fresh.enabled
            if not still_enabled:
                await self._finish_execution(
                    execution.id, status="cancelled", error=None, step_results=[]
                )
                return await self._get_execution(execution.id)

            status, error, step_results = await self._workflow_executor.run_workflow(steps)
            finished_at = datetime.now(UTC)
            await self._finish_execution(
                execution.id, status=status, error=error, step_results=step_results
            )
            async with self._db.session() as sess:
                sess = cast("AsyncSession", sess)
                await AutomationTriggerRepository(sess).record_fire(
                    trigger_id, last_fired_at=finished_at, last_execution_id=execution.id
                )
        return await self._get_execution(execution.id)

    async def _get_execution(self, execution_id: str) -> AutomationExecution | None:
        """`_finish_execution`/`record_fire` write through a separate,
        already-closed session -- the caller's own `execution` object
        would otherwise still show the stale pre-finish `status`. A
        fresh fetch is the correct fix, not reusing the original
        object."""
        async with self._db.session() as sess:
            sess = cast("AsyncSession", sess)
            return await AutomationExecutionRepository(sess).get(execution_id)

    async def _finish_execution(
        self,
        execution_id: str,
        *,
        status: str,
        error: str | None,
        step_results: list[dict[str, Any]],
    ) -> None:
        async with self._db.session() as sess:
            sess = cast("AsyncSession", sess)
            await AutomationExecutionRepository(sess).finish(
                execution_id,
                status=status,
                error=error,
                step_results_json=json.dumps(step_results),
                finished_at=datetime.now(UTC),
            )

    # ------------------------------------------------------------------
    # Payload builders
    # ------------------------------------------------------------------
    def _trigger_payload(self, trigger: AutomationTrigger, *, workflow_name: str) -> dict[str, Any]:
        return {
            "id": trigger.id,
            "workflow_id": trigger.workflow_id,
            "name": workflow_name,
            "device_id": trigger.device_id,
            "from_status": trigger.from_status,
            "to_status": trigger.to_status,
            "enabled": trigger.enabled,
            "created_at": _aware_utc(trigger.created_at).isoformat(),
            "updated_at": _aware_utc(trigger.updated_at).isoformat(),
            "last_fired_at": (
                _aware_utc(trigger.last_fired_at).isoformat() if trigger.last_fired_at else None
            ),
        }

    def _execution_payload(self, execution: AutomationExecution) -> dict[str, Any]:
        return {
            "id": execution.id,
            "automation_trigger_id": execution.automation_trigger_id,
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
