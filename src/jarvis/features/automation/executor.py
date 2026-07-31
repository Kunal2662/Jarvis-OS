"""Execution engine -- runs an ExecutionPlan wave by wave (Milestone 7,
Phase 2: dependency-independent steps within a wave run concurrently).

The plan's steps are grouped into "waves" using the same dependency graph
the planner already builds (``Step.depends_on`` / ``_dependencies_met``,
both pre-existing and unchanged): a wave is every not-yet-run step whose
dependencies have all succeeded so far. Within one wave, every step is
first validated and authorized *serially* -- so at most one confirmation
prompt is ever in flight at a time -- then every approved step in that
wave runs concurrently, capped at
``AutomationSettings.max_parallel_steps`` via
:func:`jarvis.utils.async_utils.gather_with_concurrency`. Waves run one
after another until the plan is exhausted, a wave can't make progress
(dependency deadlock), or a step fails/is denied.

On a step *failure*, every step that already succeeded *in this plan
run* is rolled back in reverse (wave, then in-wave plan order) --
deterministic regardless of real completion timing, since
``asyncio.gather`` preserves input order in its results -- and every
step that hadn't run yet is marked SKIPPED. On a step *denial* the same
skip happens but -- matching the pre-parallel behaviour this preserves
exactly -- prior successes are **not** rolled back; only a genuine
failure triggers rollback.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from jarvis.core.exceptions import AutomationPermissionDeniedError
from jarvis.core.logging.logger import get_logger
from jarvis.domain.automation.models import (
    ExecutionPlan,
    Intent,
    PlanResult,
    Step,
    StepResult,
    StepStatus,
    UndoRecord,
)
from jarvis.features.automation.permission import ConfirmationCallback, PermissionGate
from jarvis.features.automation.validator import SafetyValidator
from jarvis.infrastructure.automation.actions.registry import get_action
from jarvis.utils.async_utils import gather_with_concurrency

if TYPE_CHECKING:
    from jarvis.core.events.event_bus import EventBus
    from jarvis.features.automation.history import HistoryService
    from jarvis.features.automation.undo import UndoManager
    from jarvis.infrastructure.automation.actions.base import ActionContext

_logger = get_logger("jarvis.features.automation.executor")


@dataclass(slots=True)
class _StepOutcome:
    result: StepResult
    undo_record: UndoRecord | None = None


class ActionExecutor:
    def __init__(
        self,
        *,
        ctx: ActionContext,
        validator: SafetyValidator | None = None,
        permission: PermissionGate | None = None,
        undo: UndoManager | None = None,
        history: HistoryService | None = None,
        event_bus: EventBus | None = None,
        retry_backoff_seconds: float = 1.5,
        default_step_timeout_seconds: float = 120.0,
    ) -> None:
        self._ctx = ctx
        self._validator = validator or SafetyValidator()
        self._permission = permission or PermissionGate()
        self._undo = undo
        self._history = history
        self._event_bus = event_bus
        self._retry_backoff = retry_backoff_seconds
        # Audit fix: safety-net timeout applied to every step that
        # doesn't specify its own (see Step.timeout_seconds). 120s is
        # generous enough not to interfere with action types that
        # already enforce their own tighter inner timeout (e.g. shell
        # commands at 30s by default) while still guaranteeing that a
        # genuinely hung action type (no existing internal timeout) is
        # eventually cancelled instead of blocking the plan forever.
        self._default_step_timeout = default_step_timeout_seconds
        # Milestone 7, Phase 2: ceiling on concurrent steps within one
        # wave. floor of 1 -- a misconfigured 0 would make
        # gather_with_concurrency's semaphore deadlock every wave forever
        # instead of just running sequentially.
        self._max_parallel_steps = max(1, ctx.settings.automation.max_parallel_steps)

    async def run_plan(
        self, plan: ExecutionPlan, *, confirm: ConfirmationCallback | None = None
    ) -> PlanResult:
        plan_result = PlanResult(plan_id=plan.id)
        completed_ok: dict[str, _StepOutcome] = {}
        remaining = list(plan.steps)
        aborted = False
        should_rollback = False

        while remaining and not aborted:
            wave = [s for s in remaining if self._dependencies_met(s, completed_ok)]
            if not wave:
                # Nothing left in `remaining` has every dependency
                # satisfied, and nothing failed to trigger `aborted` --
                # a dependency cycle or a depends_on id that doesn't
                # exist in this plan. Can never resolve; skip the rest,
                # matching the pre-parallel "unmet dependency" skip.
                self._skip_remaining(remaining, plan_result, error="Dependency did not succeed.")
                remaining = []
                break

            wave_ids = {s.id for s in wave}
            remaining = [s for s in remaining if s.id not in wave_ids]

            # Authorize serially -- at most one confirmation prompt in
            # flight at a time -- before any of this wave's approved
            # steps execute concurrently below.
            authorized: list[Step] = []
            for step in wave:
                denial = await self._authorize_step(step, confirm=confirm)
                if denial is not None:
                    plan_result.step_results.append(denial.result)
                    await self._persist(plan.id, step, denial.result)
                    # DENIED aborts the remaining plan but -- matching
                    # the pre-parallel behaviour -- does not itself
                    # trigger a rollback of prior successes.
                    aborted = True
                else:
                    authorized.append(step)

            if not authorized:
                continue

            outcomes = await gather_with_concurrency(
                self._max_parallel_steps,
                *(self._execute_step(step) for step in authorized),
            )
            for step, outcome in zip(authorized, outcomes, strict=True):
                plan_result.step_results.append(outcome.result)
                await self._persist(plan.id, step, outcome.result)

                if outcome.result.status == StepStatus.SUCCEEDED:
                    completed_ok[step.id] = outcome
                    if outcome.undo_record is not None and self._undo is not None:
                        self._undo.push(outcome.undo_record)
                elif outcome.result.status == StepStatus.FAILED:
                    _logger.error(
                        "Step {} ({}) failed: {} -- rolling back {} prior step(s).",
                        step.id,
                        step.action.value,
                        outcome.result.error,
                        len(completed_ok),
                    )
                    aborted = True
                    should_rollback = True

        if should_rollback:
            await self._rollback(completed_ok)
        if aborted:
            self._skip_remaining(remaining, plan_result, error=None)

        return plan_result

    # ------------------------------------------------------------------
    def _dependencies_met(self, step: Step, completed_ok: dict[str, _StepOutcome]) -> bool:
        return all(dep_id in completed_ok for dep_id in step.depends_on)

    def _skip_remaining(
        self, steps: list[Step], plan_result: PlanResult, *, error: str | None
    ) -> None:
        for step in steps:
            step.status = StepStatus.SKIPPED
            plan_result.step_results.append(
                StepResult(step.id, step.action, StepStatus.SKIPPED, error=error)
            )

    async def _authorize_step(
        self, step: Step, *, confirm: ConfirmationCallback | None
    ) -> _StepOutcome | None:
        """Validate + authorize *step*. Returns a terminal DENIED outcome
        if declined; ``None`` if the step may proceed to
        :meth:`_execute_step`. Split out from the old combined
        ``_run_step`` so every step in a wave is authorized -- and any
        confirmation prompt shown -- one at a time (see module
        docstring), before any of the wave's approved steps execute
        concurrently."""
        intent = Intent(action=step.action, target=step.args.get("target"), arguments=step.args)
        issues = self._validator.validate(intent)

        try:
            await self._permission.authorize(intent, issues, confirm=confirm)
        except AutomationPermissionDeniedError as err:
            return _StepOutcome(StepResult(step.id, step.action, StepStatus.DENIED, error=str(err)))
        return None

    async def _execute_step(self, step: Step) -> _StepOutcome:
        """Run *step* (with retries), already validated and authorized by
        :meth:`_authorize_step`. Safe to run concurrently with sibling
        steps in the same wave -- touches only ``step`` and the shared,
        read-mostly ``ActionContext``."""
        action = get_action(step.action)
        attempts = 0
        last_error: str | None = None
        started = time.monotonic()

        while attempts <= step.max_retries:
            attempts += 1
            try:
                timeout = step.timeout_seconds or self._default_step_timeout
                output = await asyncio.wait_for(action.run(self._ctx, step.args), timeout=timeout)
                duration_ms = (time.monotonic() - started) * 1000
                undo_record = None
                if action.reversible and isinstance(output, dict) and "undo_args" in output:
                    undo_record = UndoRecord(
                        step_id=step.id, action=step.action, undo_args=output["undo_args"]
                    )
                await self._publish_step_event(step, StepStatus.SUCCEEDED)
                return _StepOutcome(
                    StepResult(
                        step.id,
                        step.action,
                        StepStatus.SUCCEEDED,
                        output=output,
                        duration_ms=duration_ms,
                        attempts=attempts,
                    ),
                    undo_record,
                )
            except TimeoutError:
                last_error = f"Step timed out after {timeout:.0f}s"
                _logger.warning(
                    "Step {} ({}) attempt {}/{} timed out after {:.0f}s",
                    step.id,
                    step.action.value,
                    attempts,
                    step.max_retries + 1,
                    timeout,
                )
                if attempts <= step.max_retries:
                    await asyncio.sleep(self._retry_backoff * attempts)
            except Exception as err:
                last_error = str(err)
                _logger.warning(
                    "Step {} ({}) attempt {}/{} failed: {}",
                    step.id,
                    step.action.value,
                    attempts,
                    step.max_retries + 1,
                    last_error,
                )
                if attempts <= step.max_retries:
                    await asyncio.sleep(self._retry_backoff * attempts)

        duration_ms = (time.monotonic() - started) * 1000
        await self._publish_step_event(step, StepStatus.FAILED)
        return _StepOutcome(
            StepResult(
                step.id,
                step.action,
                StepStatus.FAILED,
                error=last_error,
                duration_ms=duration_ms,
                attempts=attempts,
            )
        )

    async def _rollback(self, completed_ok: dict[str, _StepOutcome]) -> None:
        for outcome in reversed(list(completed_ok.values())):
            if outcome.undo_record is None:
                continue
            action = get_action(outcome.undo_record.action)
            try:
                await action.undo(self._ctx, outcome.undo_record.undo_args)
                outcome.result.status = StepStatus.ROLLED_BACK
            except Exception as err:
                _logger.error("Rollback failed for step {}: {}", outcome.result.step_id, err)

    async def _persist(self, plan_id: str, step: Step, result: StepResult) -> None:
        if self._history is None:
            return
        try:
            await self._history.record(
                plan_id=plan_id,
                step_id=step.id,
                result=result,
                target=step.args.get("target"),
                args=step.args,
            )
        except Exception as err:
            _logger.error("Failed to persist history for step {}: {}", step.id, err)

    async def _publish_step_event(self, step: Step, status: StepStatus) -> None:
        if self._event_bus is None:
            return
        from jarvis.core.events.events import AutomationStepEvent

        await self._event_bus.publish(
            AutomationStepEvent(step_id=step.id, action=step.action.value, status=status.value)
        )
