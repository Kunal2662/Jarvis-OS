"""Schedule service -- Milestone 7 Phase 6 (Scheduler MVP).

The single, DI-registered orchestration entry point for the Scheduler,
mirroring how ``AutomationService`` fronts the automation engine's
internal layers (``features/scheduler/``). See
``docs/M7_SCHEDULER_LOGIC_CONTRACT.md`` for the full design -- this
docstring only summarizes the two load-bearing decisions:

**Confirmation policy (§2, Policy A): always deny.** Every due step is
dispatched through the exact same call path any other caller already
uses -- ``AutomationService.run_command`` for ``AUTOMATION`` steps, the
same authorize-then-invoke sequence ``agents/nodes/permission_
validator.py``/``tool_executor.py`` already use for ``AGENT_TOOL``
steps -- with no ``confirm`` callback supplied. Both existing gates
(``PermissionGate``, ``AgentPermissionGate``) already fail-safe to a
denial with no callback; this service adds **zero** new authorization
code and cannot introduce a bypass, because it introduces no new
execution path, only a new unattended *caller* of the same existing
ones.

**Time-based triggers only (§3).** No EventBus subscription of any
kind exists in this module -- confirmed by its own import list, which
never imports ``EventBus.subscribe`` or any device/connectivity event
type. Event-triggered workflows are out of scope, blocked on a future,
separately-scoped EventBus capability this module does not attempt to
approximate.

**Permission separation (§12, §15 -- the most important design rule in
this file):** ``SCHEDULER_PRINCIPAL``/``SCHEDULER_SCOPE`` gate CRUD on
Schedule/WorkflowDefinition/WorkflowExecution rows only. They never
grant permission to execute a scheduled step's own underlying action --
that is independently, separately re-evaluated at execution time by
whichever existing gate already governs that step kind, every time,
with no caching.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from jarvis.agents.permission import AgentPermissionGate
from jarvis.agents.tools import build_tool_registry
from jarvis.core.exceptions import ServiceError
from jarvis.core.logging.logger import get_logger
from jarvis.domain.workflow.models import ScheduleKind, WorkflowStepKind
from jarvis.features.scheduler.timing import (
    compute_next_fire,
    validate_cron_expression,
    validate_interval_seconds,
    validate_timezone,
)
from jarvis.infrastructure.database.repositories.schedule_repository import (
    ScheduleRepository,
    WorkflowExecutionRepository,
    WorkflowRepository,
)

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

    from jarvis.core.config.settings import Settings
    from jarvis.core.interfaces.database import IDatabase
    from jarvis.core.plugins.permissions import PermissionModel
    from jarvis.infrastructure.database.models import Schedule
    from jarvis.services.automation_service import AutomationService
    from sqlalchemy.ext.asyncio import AsyncSession

_logger = get_logger("jarvis.services.schedule_service")

#: The `PermissionModel` identity this module declares and checks
#: against -- one fixed principal, mirroring every M12 service's exact
#: naming convention. Governs CRUD on Scheduler's own resources only;
#: never implies permission to execute a step's underlying action (see
#: module docstring).
SCHEDULER_PRINCIPAL = "core:scheduler"

#: A new scope (added to `core/plugins/sdk.py`'s `PERMISSION_SCOPES`
#: this phase) -- none of the ten pre-existing scopes fit "schedule
#: CRUD" (Logic Contract §12).
SCHEDULER_SCOPE = "scheduler"

#: Statuses that mean "this execution is not going to run/finish
#: differently" -- used by the duplicate-fire-prevention check
#: (`WorkflowExecutionRepository.has_non_terminal` checks the inverse:
#: queued/running).
_TERMINAL_STATUSES = frozenset(
    {"succeeded", "partially_failed", "failed", "cancelled", "skipped", "denied"}
)


class SchedulerPermissionError(ServiceError):
    """Raised by `_require_permission()` specifically -- a distinct
    subclass, not a bare `ServiceError`, so `routes/schedules.py` can
    tell "not granted" apart from "not found" by exception type, the
    same `SensorPermissionError`/`SmartHomeMemoryPermissionError`
    precedent every M12 module with a dedicated route already uses."""


class ScheduleNotFoundError(ServiceError):
    """A distinct subclass so the REST route can map this to 404
    specifically, the same way `SnapshotNotFoundError` already lets
    `routes/smart_home_memory.py` distinguish "not found" from a plain
    validation `ServiceError` (400)."""


def _aware_utc(value: datetime) -> datetime:
    """SQLite has no native timezone storage -- every timestamp in this
    codebase is written via UTC-aware helpers, but SQLAlchemy reads one
    back *naive* on this backend (verified directly this session). A
    naive value read from this schema is therefore always known to
    already represent UTC wall-clock time; this just re-attaches the
    tag so Python-side arithmetic (as opposed to the SQL-side `<=`
    comparison `list_due` already does correctly) doesn't raise."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _metadata_or_empty(raw: str | None) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def _validate_step(step: dict[str, Any]) -> dict[str, Any]:
    """Structural validation only -- Scheduler is not the workflow
    authoring surface (Logic Contract §5); it does not resolve whether
    an `instruction` parses or a `tool_name` is registered."""
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


class ScheduleService:
    def __init__(
        self,
        *,
        database: IDatabase,
        permissions: PermissionModel,
        settings: Settings,
        automation: AutomationService | None = None,
        memory: Any | None = None,
        browser: Any | None = None,
        chat: Any | None = None,
        voice: Any | None = None,
        system: Any | None = None,
        vision: Any | None = None,
        knowledge: Any | None = None,
        intelligence: Any | None = None,
        workspace_assistant: Any | None = None,
        integrations: Any | None = None,
        smart_lighting: Any | None = None,
        smart_lock: Any | None = None,
        sensors: Any | None = None,
        smart_switch: Any | None = None,
        appliances: Any | None = None,
        thermostats: Any | None = None,
        vacuum_humidifier: Any | None = None,
        media_players: Any | None = None,
        water_heaters: Any | None = None,
        security: Any | None = None,
        siren: Any | None = None,
        alarm_control_panels: Any | None = None,
        smart_home_memory: Any | None = None,
    ) -> None:
        self._db = database
        self._permissions = permissions
        self._settings = settings
        self._automation = automation
        # Every one of these is only ever used to build this service's
        # own tool registry (below) for AGENT_TOOL-kind steps -- the
        # identical optional-service list `AgentOrchestrator`/
        # `container.py`'s own `_build_agent_orchestrator` already
        # assembles, reused verbatim rather than a narrower subset, so
        # a workflow step can reach any tool chat/voice already can.
        self._tool_services: dict[str, Any] = {
            "memory": memory,
            "browser": browser,
            "chat": chat,
            "voice": voice,
            "system": system,
            "vision": vision,
            "knowledge": knowledge,
            "intelligence": intelligence,
            "workspace_assistant": workspace_assistant,
            "integrations": integrations,
            "smart_lighting": smart_lighting,
            "smart_lock": smart_lock,
            "sensors": sensors,
            "smart_switch": smart_switch,
            "appliances": appliances,
            "thermostats": thermostats,
            "vacuum_humidifier": vacuum_humidifier,
            "media_players": media_players,
            "water_heaters": water_heaters,
            "security": security,
            "siren": siren,
            "alarm_control_panels": alarm_control_panels,
            "smart_home_memory": smart_home_memory,
            "automation": automation,
        }
        self._permissions.declare(SCHEDULER_PRINCIPAL, [SCHEDULER_SCOPE])

        self._tools_by_name: dict[str, BaseTool] | None = None
        self._gate: AgentPermissionGate | None = None
        self._semaphore = asyncio.Semaphore(max(1, settings.scheduler.max_concurrent_jobs))
        self._poll_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Permission
    # ------------------------------------------------------------------
    def _require_permission(self) -> None:
        if not self._permissions.is_granted(SCHEDULER_PRINCIPAL, SCHEDULER_SCOPE):
            raise SchedulerPermissionError(
                "Schedule management requires the "
                f"{SCHEDULER_SCOPE!r} permission to be granted for "
                f"{SCHEDULER_PRINCIPAL!r}. Grant it via POST "
                f"/api/v1/plugins/{SCHEDULER_PRINCIPAL}/permissions/"
                f"{SCHEDULER_SCOPE}/grant."
            )

    # ------------------------------------------------------------------
    # Agent-tool execution path (AGENT_TOOL-kind steps only)
    # ------------------------------------------------------------------
    def _ensure_tools_ready(self) -> None:
        """Lazily builds this service's own tool registry and its own
        `AgentPermissionGate` instance -- mirrors `AgentOrchestrator.
        start()`'s identical lazy-build pattern exactly (same
        `build_tool_registry` function, same `AgentPermissionGate`
        class, same `settings.agent.confirm_required_tools` source). A
        second *instance*, not a second *implementation* -- see module
        docstring."""
        if self._tools_by_name is not None and self._gate is not None:
            return
        tools = build_tool_registry(**self._tool_services)
        self._tools_by_name = {t.name: t for t in tools}
        self._gate = AgentPermissionGate(
            confirm_required_tools=self._settings.agent.confirm_required_tools,
        )

    def _confirm_required_tool_names(self) -> frozenset[str]:
        return self._settings.agent.confirm_required_tools

    # ------------------------------------------------------------------
    # Schedule CRUD
    # ------------------------------------------------------------------
    async def create_schedule(
        self,
        *,
        name: str,
        steps: list[dict[str, Any]],
        kind: str,
        description: str = "",
        interval_seconds: float = 0.0,
        cron_expression: str = "",
        timezone: str | None = None,
        enabled: bool = True,
    ) -> dict[str, Any]:
        self._require_permission()
        if not name.strip():
            raise ServiceError("A schedule requires a non-empty 'name'.")
        if not steps:
            raise ServiceError("A schedule's workflow requires at least one step.")
        validated_steps = [_validate_step(s) for s in steps]

        if kind not in (ScheduleKind.INTERVAL.value, ScheduleKind.CRON.value):
            raise ServiceError(
                f"'kind' must be {ScheduleKind.INTERVAL.value!r} or "
                f"{ScheduleKind.CRON.value!r}, got {kind!r}."
            )
        if kind == ScheduleKind.INTERVAL.value:
            validate_interval_seconds(interval_seconds)
        else:
            validate_cron_expression(cron_expression)
        resolved_timezone = timezone or self._settings.scheduler.default_timezone
        validate_timezone(resolved_timezone)

        # Best-effort, non-blocking scan (Logic Contract §2) -- accurate
        # for AGENT_TOOL steps (an O(1) name lookup against the same
        # settings source the live gate itself reads); AUTOMATION steps
        # are natural-language instructions this service does not parse
        # (that would mean reaching into `TaskPlanner` internals
        # `AutomationService` does not expose -- a second execution
        # path this contract explicitly forbids), so they are not
        # covered by this informational flag. The live gate at
        # execution time is always the real, complete source of truth
        # for both step kinds regardless of this flag's coverage.
        confirm_required_names = self._confirm_required_tool_names()
        contains_confirm_required_steps = any(
            s["kind"] == WorkflowStepKind.AGENT_TOOL.value
            and s["tool_name"] in confirm_required_names
            for s in validated_steps
        )

        now = datetime.now(UTC)
        next_fire_at = compute_next_fire(
            kind=kind,
            after=now,
            interval_seconds=interval_seconds,
            cron_expression=cron_expression,
            timezone=resolved_timezone,
        )

        async with self._db.session() as sess:
            sess = cast("AsyncSession", sess)
            workflow = await WorkflowRepository(sess).add(
                name=name, description=description, steps_json=json.dumps(validated_steps)
            )
            schedule = await ScheduleRepository(sess).add(
                workflow_id=workflow.id,
                kind=kind,
                interval_seconds=interval_seconds,
                cron_expression=cron_expression,
                timezone=resolved_timezone,
                next_fire_at=next_fire_at,
                enabled=enabled,
            )
        _logger.info("Schedule {} created for workflow {}.", schedule.id, workflow.id)
        return self._schedule_payload(
            schedule,
            workflow_name=name,
            contains_confirm_required_steps=contains_confirm_required_steps,
        )

    async def get_schedule(self, schedule_id: str) -> dict[str, Any]:
        self._require_permission()
        async with self._db.session() as sess:
            sess = cast("AsyncSession", sess)
            schedule = await ScheduleRepository(sess).get(schedule_id)
            if schedule is None:
                raise ScheduleNotFoundError(f"Schedule {schedule_id!r} does not exist.")
            workflow = await WorkflowRepository(sess).get(schedule.workflow_id)
            latest_execution = None
            if schedule.last_execution_id:
                latest_execution = await WorkflowExecutionRepository(sess).get(
                    schedule.last_execution_id
                )
        payload = self._schedule_payload(
            schedule,
            workflow_name=workflow.name if workflow else "",
            contains_confirm_required_steps=None,
        )
        if latest_execution is not None:
            payload["last_execution"] = self._execution_payload(latest_execution)
        return payload

    async def list_schedules(self, *, enabled_only: bool = False) -> list[dict[str, Any]]:
        self._require_permission()
        async with self._db.session() as sess:
            sess = cast("AsyncSession", sess)
            schedules = await ScheduleRepository(sess).list_schedules(enabled_only=enabled_only)
            workflow_repo = WorkflowRepository(sess)
            payloads = []
            for schedule in schedules:
                workflow = await workflow_repo.get(schedule.workflow_id)
                payloads.append(
                    self._schedule_payload(
                        schedule,
                        workflow_name=workflow.name if workflow else "",
                        contains_confirm_required_steps=None,
                    )
                )
        return payloads

    async def enable_schedule(self, schedule_id: str) -> dict[str, Any]:
        self._require_permission()
        async with self._db.session() as sess:
            sess = cast("AsyncSession", sess)
            schedule = await ScheduleRepository(sess).set_enabled(schedule_id, enabled=True)
            if schedule is None:
                raise ScheduleNotFoundError(f"Schedule {schedule_id!r} does not exist.")
            workflow = await WorkflowRepository(sess).get(schedule.workflow_id)
        return self._schedule_payload(
            schedule,
            workflow_name=workflow.name if workflow else "",
            contains_confirm_required_steps=None,
        )

    async def disable_schedule(self, schedule_id: str) -> dict[str, Any]:
        self._require_permission()
        async with self._db.session() as sess:
            sess = cast("AsyncSession", sess)
            schedule = await ScheduleRepository(sess).set_enabled(schedule_id, enabled=False)
            if schedule is None:
                raise ScheduleNotFoundError(f"Schedule {schedule_id!r} does not exist.")
            workflow = await WorkflowRepository(sess).get(schedule.workflow_id)
        return self._schedule_payload(
            schedule,
            workflow_name=workflow.name if workflow else "",
            contains_confirm_required_steps=None,
        )

    async def delete_schedule(self, schedule_id: str) -> bool:
        self._require_permission()
        async with self._db.session() as sess:
            sess = cast("AsyncSession", sess)
            schedule = await ScheduleRepository(sess).get(schedule_id)
            if schedule is None:
                raise ScheduleNotFoundError(f"Schedule {schedule_id!r} does not exist.")
            workflow_id = schedule.workflow_id
            await ScheduleRepository(sess).delete(schedule_id)
            # One dedicated WorkflowDefinition per schedule (Logic
            # Contract §5) -- deleting the schedule deletes its own
            # workflow row too, since nothing else can reference it.
            await WorkflowRepository(sess).delete(workflow_id)
        return True

    async def list_executions(self, schedule_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        self._require_permission()
        async with self._db.session() as sess:
            sess = cast("AsyncSession", sess)
            schedule = await ScheduleRepository(sess).get(schedule_id)
            if schedule is None:
                raise ScheduleNotFoundError(f"Schedule {schedule_id!r} does not exist.")
            executions = await WorkflowExecutionRepository(sess).list_for_schedule(
                schedule_id, limit=limit
            )
        return [self._execution_payload(e) for e in executions]

    # ------------------------------------------------------------------
    # Payload builders
    # ------------------------------------------------------------------
    def _schedule_payload(
        self,
        schedule: Schedule,
        *,
        workflow_name: str,
        contains_confirm_required_steps: bool | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": schedule.id,
            "workflow_id": schedule.workflow_id,
            "name": workflow_name,
            "kind": schedule.kind,
            "interval_seconds": schedule.interval_seconds,
            "cron_expression": schedule.cron_expression,
            "timezone": schedule.timezone,
            "enabled": schedule.enabled,
            "created_at": _aware_utc(schedule.created_at).isoformat(),
            "updated_at": _aware_utc(schedule.updated_at).isoformat(),
            "next_fire_at": (
                _aware_utc(schedule.next_fire_at).isoformat() if schedule.next_fire_at else None
            ),
            "last_fired_at": (
                _aware_utc(schedule.last_fired_at).isoformat() if schedule.last_fired_at else None
            ),
        }
        if contains_confirm_required_steps is not None:
            payload["contains_confirm_required_steps"] = contains_confirm_required_steps
        return payload

    def _execution_payload(self, execution: Any) -> dict[str, Any]:
        return {
            "id": execution.id,
            "schedule_id": execution.schedule_id,
            "workflow_id": execution.workflow_id,
            "status": execution.status,
            "started_at": _aware_utc(execution.started_at).isoformat(),
            "finished_at": (
                _aware_utc(execution.finished_at).isoformat() if execution.finished_at else None
            ),
            "error": execution.error,
            "step_results": _metadata_or_empty(execution.step_results_json),
        }

    # ------------------------------------------------------------------
    # Firing loop (lifecycle-managed -- see app.py's scheduler hooks)
    # ------------------------------------------------------------------
    async def start(self) -> None:
        """Begin the periodic poll loop. Idempotent."""
        if not self._settings.scheduler.enabled:
            _logger.info("Scheduler disabled via settings; poll loop not started.")
            return
        if self._poll_task is not None:
            return
        self._poll_task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Cancel the poll loop. Idempotent, safe even if never started."""
        if self._poll_task is None:
            return
        self._poll_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._poll_task
        self._poll_task = None

    async def _loop(self) -> None:
        interval = self._settings.scheduler.poll_interval_seconds
        while True:
            try:
                await self.tick()
            except Exception:
                _logger.exception("Scheduler poll tick failed.")
            await asyncio.sleep(interval)

    async def tick(self) -> None:
        """One poll cycle: find every due, enabled schedule and dispatch
        it (or skip it under the misfire/duplicate-fire rules). Awaits
        full completion of everything it dispatches before returning --
        a deliberate MVP simplification (Logic Contract §10) that keeps
        the concurrency model simple and correct at the cost of not
        being maximally responsive under many-simultaneous-schedules
        load, acceptable at `max_concurrent_jobs`'s small default."""
        now = datetime.now(UTC)
        async with self._db.session() as sess:
            sess = cast("AsyncSession", sess)
            due = await ScheduleRepository(sess).list_due(now=now)
            due_ids = [s.id for s in due]

        await asyncio.gather(*(self._dispatch(schedule_id, now) for schedule_id in due_ids))

    async def _dispatch(self, schedule_id: str, now: datetime) -> None:
        async with self._db.session() as sess:
            sess = cast("AsyncSession", sess)
            schedule_repo = ScheduleRepository(sess)
            execution_repo = WorkflowExecutionRepository(sess)
            schedule = await schedule_repo.get(schedule_id)
            if schedule is None or not schedule.enabled:
                return
            if await execution_repo.has_non_terminal(schedule_id):
                # Duplicate-fire prevention (Logic Contract §10): leave
                # next_fire_at untouched -- it stays due and is
                # re-evaluated next tick, once the in-flight run ends.
                return

            grace = self._settings.scheduler.misfire_grace_period_seconds
            scheduled_next_fire = (
                _aware_utc(schedule.next_fire_at) if schedule.next_fire_at else now
            )
            overdue_seconds = (now - scheduled_next_fire).total_seconds()
            workflow = await WorkflowRepository(sess).get(schedule.workflow_id)

            if overdue_seconds > grace:
                # Bounded-grace-period misfire policy (Logic Contract
                # §9): skip, never catch up, resume from `now` so a
                # long outage produces exactly one skip record, not one
                # per missed period.
                execution = await execution_repo.add(
                    schedule_id=schedule.id, workflow_id=schedule.workflow_id, status="skipped"
                )
                new_next_fire = compute_next_fire(
                    kind=schedule.kind,
                    after=now,
                    interval_seconds=schedule.interval_seconds,
                    cron_expression=schedule.cron_expression,
                    timezone=schedule.timezone,
                )
                await execution_repo.finish(
                    execution.id,
                    status="skipped",
                    error=(
                        f"Misfire: schedule was due at {scheduled_next_fire.isoformat()}, more "
                        f"than {grace:.0f}s ago; skipped, not caught up."
                    ),
                    step_results_json="[]",
                    finished_at=now,
                )
                await schedule_repo.record_fire(
                    schedule.id,
                    next_fire_at=new_next_fire,
                    # A skip is never a real fire -- `last_fired_at`
                    # stays exactly as it was (possibly still `None`,
                    # for a schedule that has never actually fired).
                    last_fired_at=(
                        _aware_utc(schedule.last_fired_at) if schedule.last_fired_at else None
                    ),
                    last_execution_id=execution.id,
                )
                return

            execution = await execution_repo.add(
                schedule_id=schedule.id, workflow_id=schedule.workflow_id, status="queued"
            )
            fire_reference = scheduled_next_fire
            steps = _metadata_or_empty(workflow.steps_json) if workflow else []

        async with self._semaphore:
            # Re-check `enabled` fresh, right before executing -- the
            # narrow, real "cancelled" case (Logic Contract §6): a
            # still-queued execution whose schedule was disabled
            # between being queued and reaching a concurrency slot.
            async with self._db.session() as sess:
                sess = cast("AsyncSession", sess)
                fresh = await ScheduleRepository(sess).get(schedule_id)
                still_enabled = fresh is not None and fresh.enabled
            if not still_enabled:
                await self._finish_execution(
                    execution.id, status="cancelled", error=None, step_results=[]
                )
                return

            status, error, step_results = await self._run_workflow(steps)
            finished_at = datetime.now(UTC)
            await self._finish_execution(
                execution.id, status=status, error=error, step_results=step_results
            )

            new_next_fire = compute_next_fire(
                kind=schedule.kind,
                after=fire_reference,
                interval_seconds=schedule.interval_seconds,
                cron_expression=schedule.cron_expression,
                timezone=schedule.timezone,
            )
            async with self._db.session() as sess:
                sess = cast("AsyncSession", sess)
                await ScheduleRepository(sess).record_fire(
                    schedule_id,
                    next_fire_at=new_next_fire,
                    last_fired_at=finished_at,
                    last_execution_id=execution.id,
                )

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
            await WorkflowExecutionRepository(sess).finish(
                execution_id,
                status=status,
                error=error,
                step_results_json=json.dumps(step_results),
                finished_at=datetime.now(UTC),
            )

    async def _run_workflow(
        self, steps: list[dict[str, Any]]
    ) -> tuple[str, str | None, list[dict[str, Any]]]:
        """Executes *steps* sequentially (Logic Contract §6: `depends_on`
        -based parallel dispatch is Phase 3 scope, deferred -- a flat
        linear list is executed in list order). Returns the workflow-
        level status, an optional top-level error summary, and the
        per-step result list."""
        results: list[dict[str, Any]] = []
        for step in steps:
            started = asyncio.get_event_loop().time()
            step_status, step_error = await self._run_step(step)
            duration_ms = (asyncio.get_event_loop().time() - started) * 1000
            results.append(
                {
                    "step_id": step.get("id", ""),
                    "status": step_status,
                    "error": step_error,
                    "duration_ms": duration_ms,
                }
            )

        succeeded = sum(1 for r in results if r["status"] == "succeeded")
        denied = sum(1 for r in results if r["status"] == "denied")
        failed = sum(1 for r in results if r["status"] == "failed")
        total = len(results)

        if succeeded == total:
            return "succeeded", None, results
        if succeeded == 0 and failed == 0 and denied == total:
            return "denied", "Every step in this workflow was denied.", results
        if succeeded == 0:
            return "failed", "No step in this workflow succeeded.", results
        return "partially_failed", "Some steps in this workflow did not succeed.", results

    async def _run_step(self, step: dict[str, Any]) -> tuple[str, str | None]:
        if step.get("kind") == WorkflowStepKind.AUTOMATION.value:
            return await self._run_automation_step(step)
        return await self._run_agent_tool_step(step)

    async def _run_automation_step(self, step: dict[str, Any]) -> tuple[str, str | None]:
        if self._automation is None:
            return "failed", "Automation service is not available."
        # No `confirm` supplied -- Policy A (module docstring). Any
        # confirm-required action inside this instruction is denied by
        # `PermissionGate` itself, internally, and surfaces as a
        # `StepStatus.DENIED` entry in `PlanResult.step_results` --
        # `AutomationPermissionDeniedError` never propagates out of
        # `run_command` (verified directly against `ActionExecutor.
        # _authorize_step` this session).
        result = await self._automation.run_command(step.get("instruction", ""))
        if result.plan_id == "disabled":
            return "failed", "Automation is disabled (AutomationSettings.enabled=False)."
        if result.succeeded:
            return "succeeded", None
        denied_statuses = {r.status.value for r in result.step_results}
        if denied_statuses and denied_statuses <= {"denied"}:
            errors = "; ".join(r.error or "" for r in result.step_results if r.error)
            return "denied", errors or "Denied: confirmation required."
        errors = "; ".join(r.error or "" for r in result.step_results if r.error)
        return "failed", errors or "Automation instruction failed."

    async def _run_agent_tool_step(self, step: dict[str, Any]) -> tuple[str, str | None]:
        self._ensure_tools_ready()
        assert self._tools_by_name is not None
        assert self._gate is not None

        tool_name = step.get("tool_name", "")
        tool_args = step.get("tool_args") or {}
        tool = self._tools_by_name.get(tool_name)
        if tool is None:
            return "failed", f"Unknown tool: {tool_name!r}."

        # No `confirm` supplied -- Policy A. `authorize()` never raises;
        # it returns a plain (allowed, reason) pair (verified directly
        # against `agents/permission.py` this session).
        allowed, reason = await self._gate.authorize(tool_name, tool_args, confirm=None)
        if not allowed:
            return "denied", f"Denied: {reason}"

        try:
            await tool.ainvoke(tool_args)
        except Exception as err:  # a step failure must not crash the loop
            _logger.warning("Scheduled tool {!r} failed: {}", tool_name, err)
            return "failed", str(err)
        return "succeeded", None
