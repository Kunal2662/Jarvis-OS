"""Milestone 7, Phase 2 -- parallel execution tests for ActionExecutor.

Exercises the new wave-based scheduler (dependency-graph batching via the
pre-existing, unchanged ``Step.depends_on`` / ``_dependencies_met`` model,
dispatched with ``gather_with_concurrency``) added on top of
``ActionExecutor.run_plan``. Uses a controllable fake ``BaseAction``
(matching the pattern already established in
``test_automation_executor.py``'s ``_HangingAction``) rather than mocking
the thing under test, so timing assertions reflect real ``asyncio``
concurrency, not a mocked shortcut.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import pytest

from jarvis.core.config.settings import AutomationSettings, Settings
from jarvis.domain.automation.models import ActionType, ExecutionPlan, Step, StepStatus
from jarvis.features.automation.executor import ActionExecutor
from jarvis.features.automation.undo import UndoManager
from jarvis.infrastructure.automation.actions.base import ActionContext, BaseAction
from tests.fakes.fake_os_automation import FakeOSAutomation


class _Tracker:
    """Shared, lock-protected counters so tests can assert real
    concurrency (or its deliberate absence) without depending on exact
    timings beyond a generous margin."""

    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.in_flight = 0
        self.max_in_flight = 0
        self.starts: list[float] = []
        self.ends: list[float] = []
        self.undone_order: list[str] = []

    async def enter(self) -> None:
        async with self.lock:
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
        self.starts.append(time.monotonic())

    async def exit(self) -> None:
        self.ends.append(time.monotonic())
        async with self.lock:
            self.in_flight -= 1


class _DelayAction(BaseAction):
    """Sleeps ``delay`` seconds, records concurrency via a shared
    :class:`_Tracker`, and optionally fails -- lets tests assert timing
    and rollback without touching the real filesystem/OS actions.

    ``label``, if set, is threaded through ``undo_args`` so
    :meth:`undo` can record *which* step was reversed and in what
    order, even though several instances of this class run
    concurrently and share no other identity.
    """

    reversible = True

    def __init__(self, *, delay: float, fail: bool = False, label: str = "") -> None:
        self.delay = delay
        self.fail = fail
        self.label = label

    async def run(self, ctx: ActionContext, args: dict[str, Any]) -> dict[str, Any]:
        tracker: _Tracker = args["tracker"]
        await tracker.enter()
        try:
            await asyncio.sleep(self.delay)
            if self.fail:
                raise RuntimeError("synthetic failure")
            return {"undo_args": {"tracker": tracker, "label": self.label}}
        finally:
            await tracker.exit()

    async def undo(self, ctx: ActionContext, undo_args: dict[str, Any]) -> None:
        tracker: _Tracker | None = undo_args.get("tracker")
        if tracker is not None:
            tracker.undone_order.append(undo_args.get("label", ""))


@pytest.fixture()
def ctx(tmp_path: Path) -> ActionContext:
    settings = Settings(data_dir=tmp_path)
    return ActionContext(settings=settings, os_automation=FakeOSAutomation())


def _plan(*steps: Step) -> ExecutionPlan:
    plan = ExecutionPlan(raw_text="test")
    plan.steps = list(steps)
    return plan


# ---------------------------------------------------------------------------
# Wave scheduling / parallelism
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_independent_steps_run_concurrently_not_sequentially(
    ctx: ActionContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    tracker = _Tracker()
    delay = 0.15
    monkeypatch.setattr(
        "jarvis.features.automation.executor.get_action",
        lambda action_type: _DelayAction(delay=delay),
    )
    steps = [Step(action=ActionType.SCREENSHOT, args={"tracker": tracker}) for _ in range(3)]
    executor = ActionExecutor(ctx=ctx, undo=UndoManager())

    started = time.monotonic()
    result = await executor.run_plan(_plan(*steps))
    elapsed = time.monotonic() - started

    assert result.succeeded
    # Sequential would take >= 3 * delay (0.45s); real concurrency stays
    # close to one delay period. Generous margin to avoid CI flakiness.
    assert elapsed < delay * 2
    assert tracker.max_in_flight == 3


@pytest.mark.asyncio
async def test_dependent_steps_run_in_separate_sequential_waves(
    ctx: ActionContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    tracker = _Tracker()
    delay = 0.1
    monkeypatch.setattr(
        "jarvis.features.automation.executor.get_action",
        lambda action_type: _DelayAction(delay=delay),
    )
    step1 = Step(action=ActionType.SCREENSHOT, args={"tracker": tracker})
    step2 = Step(action=ActionType.SCREENSHOT, args={"tracker": tracker}, depends_on=[step1.id])
    executor = ActionExecutor(ctx=ctx, undo=UndoManager())

    result = await executor.run_plan(_plan(step1, step2))

    assert result.succeeded
    # A real dependency link must still force separate waves -- never
    # more than one of these two in flight at the same time.
    assert tracker.max_in_flight == 1
    assert tracker.starts[1] >= tracker.ends[0]


@pytest.mark.asyncio
async def test_diamond_dependency_graph_produces_correct_waves(
    ctx: ActionContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A (independent) and B (independent) both run in wave 1; C, which
    depends on both, must not start until *both* have finished --
    proving multi-dependency (not just single-predecessor) waves work."""
    tracker = _Tracker()
    monkeypatch.setattr(
        "jarvis.features.automation.executor.get_action",
        lambda action_type: _DelayAction(delay=0.05),
    )
    step_a = Step(action=ActionType.SCREENSHOT, args={"tracker": tracker})
    step_b = Step(action=ActionType.SCREENSHOT, args={"tracker": tracker})
    step_c = Step(
        action=ActionType.SCREENSHOT,
        args={"tracker": tracker},
        depends_on=[step_a.id, step_b.id],
    )
    executor = ActionExecutor(ctx=ctx, undo=UndoManager())

    result = await executor.run_plan(_plan(step_a, step_b, step_c))

    assert result.succeeded
    assert tracker.max_in_flight == 2  # A and B overlapped; C waited
    assert tracker.starts[2] >= tracker.ends[0]
    assert tracker.starts[2] >= tracker.ends[1]


@pytest.mark.asyncio
async def test_max_parallel_steps_setting_caps_concurrency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tracker = _Tracker()
    settings = Settings(data_dir=tmp_path, automation=AutomationSettings(max_parallel_steps=2))
    ctx_capped = ActionContext(settings=settings, os_automation=FakeOSAutomation())
    executor = ActionExecutor(ctx=ctx_capped, undo=UndoManager())
    assert executor._max_parallel_steps == 2

    monkeypatch.setattr(
        "jarvis.features.automation.executor.get_action",
        lambda action_type: _DelayAction(delay=0.08),
    )
    steps = [Step(action=ActionType.SCREENSHOT, args={"tracker": tracker}) for _ in range(6)]
    result = await executor.run_plan(_plan(*steps))

    assert result.succeeded
    assert tracker.max_in_flight <= 2
    # And genuinely parallel, not accidentally serialized to 1.
    assert tracker.max_in_flight == 2


@pytest.mark.asyncio
async def test_max_parallel_steps_floor_is_one(tmp_path: Path) -> None:
    """A misconfigured 0 must not deadlock gather_with_concurrency's
    semaphore -- floors to 1 (sequential), not disabled."""
    settings = Settings(data_dir=tmp_path, automation=AutomationSettings(max_parallel_steps=0))
    ctx_zero = ActionContext(settings=settings, os_automation=FakeOSAutomation())
    executor = ActionExecutor(ctx=ctx_zero, undo=UndoManager())

    assert executor._max_parallel_steps == 1


# ---------------------------------------------------------------------------
# Rollback under concurrency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_parallel_wave_failure_rolls_back_sibling_success(
    ctx: ActionContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    tracker = _Tracker()

    def _get_action(action_type: ActionType) -> BaseAction:
        # step1 succeeds, step2 fails -- both dispatched in the same wave.
        return _DelayAction(delay=0.05, fail=(action_type == ActionType.MOVE))

    monkeypatch.setattr("jarvis.features.automation.executor.get_action", _get_action)
    step1 = Step(action=ActionType.SCREENSHOT, args={"tracker": tracker})
    step2 = Step(action=ActionType.MOVE, args={"tracker": tracker})
    executor = ActionExecutor(ctx=ctx, undo=UndoManager())

    result = await executor.run_plan(_plan(step1, step2))

    assert not result.succeeded
    assert result.step_results[0].status is StepStatus.ROLLED_BACK
    assert result.step_results[1].status is StepStatus.FAILED


@pytest.mark.asyncio
async def test_denial_aborts_without_rolling_back_prior_success(
    ctx: ActionContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Matches the pre-parallel behaviour exactly: a DENIED step aborts
    the remaining plan but -- unlike a FAILED step -- does not roll back
    steps that already succeeded."""
    tracker = _Tracker()
    monkeypatch.setattr(
        "jarvis.features.automation.executor.get_action",
        lambda action_type: _DelayAction(delay=0.02),
    )
    step1 = Step(action=ActionType.SCREENSHOT, args={"tracker": tracker})
    step2 = Step(
        action=ActionType.DELETE_FOLDER,
        args={"tracker": tracker, "target": "irrelevant"},
        depends_on=[step1.id],
    )
    executor = ActionExecutor(ctx=ctx, undo=UndoManager())

    # No confirm callback -> auto-denied (PermissionGate default).
    result = await executor.run_plan(_plan(step1, step2))

    assert result.step_results[0].status is StepStatus.SUCCEEDED
    assert result.step_results[1].status is StepStatus.DENIED


@pytest.mark.asyncio
async def test_deterministic_rollback_order_is_reverse_of_wave_and_plan_order(
    ctx: ActionContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Three independent steps succeed in wave 1 (dispatched concurrently
    with *different* delays, so real completion order is reversed from
    plan order), a fourth fails in wave 2 -- rollback must still happen
    in a fixed, reproducible order (reverse of each step's position in
    the original plan), not whatever order asyncio happened to finish
    them in."""
    tracker = _Tracker()
    # Deliberately finish in the OPPOSITE order from plan order (C
    # fastest, A slowest) -- if rollback order were driven by real
    # completion time rather than plan position, this would catch it.
    delays = {"a": 0.09, "b": 0.06, "c": 0.03}

    def _get_action(action_type: ActionType) -> BaseAction:
        if action_type == ActionType.MOVE:
            return _DelayAction(delay=0.01, fail=True)
        label = {
            ActionType.SCREENSHOT: "a",
            ActionType.CLIPBOARD_COPY: "b",
            ActionType.OPEN_EXPLORER: "c",
        }[action_type]
        return _DelayAction(delay=delays[label], label=label)

    monkeypatch.setattr("jarvis.features.automation.executor.get_action", _get_action)

    step_a = Step(action=ActionType.SCREENSHOT, args={"tracker": tracker})
    step_b = Step(action=ActionType.CLIPBOARD_COPY, args={"tracker": tracker})
    step_c = Step(action=ActionType.OPEN_EXPLORER, args={"tracker": tracker})
    fail_step = Step(
        action=ActionType.MOVE,
        args={"tracker": tracker},
        depends_on=[step_a.id, step_b.id, step_c.id],
    )
    executor = ActionExecutor(ctx=ctx, undo=UndoManager())

    result = await executor.run_plan(_plan(step_a, step_b, step_c, fail_step))

    assert not result.succeeded
    assert result.step_results[0].status is StepStatus.ROLLED_BACK
    assert result.step_results[1].status is StepStatus.ROLLED_BACK
    assert result.step_results[2].status is StepStatus.ROLLED_BACK
    # Real completion order (shortest delay first) is c, b, a --
    # rollback undoing in *that* order would give ["a", "b", "c"]
    # (undo the last-to-finish first). Deterministic plan-order
    # rollback instead gives reverse-of-plan-order: ["c", "b", "a"].
    # Asserting the latter proves rollback follows plan position, not
    # real async completion timing.
    assert tracker.undone_order == ["c", "b", "a"]


# ---------------------------------------------------------------------------
# Dependency graph edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unresolvable_dependency_is_skipped_not_hung(ctx: ActionContext) -> None:
    step = Step(
        action=ActionType.CREATE_FOLDER,
        args={"target": "irrelevant"},
        depends_on=["step-id-that-does-not-exist-in-this-plan"],
    )
    executor = ActionExecutor(ctx=ctx, undo=UndoManager())

    result = await asyncio.wait_for(executor.run_plan(_plan(step)), timeout=5)

    assert result.step_results[0].status is StepStatus.SKIPPED
    assert result.step_results[0].error == "Dependency did not succeed."


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_permission_confirmations_within_a_wave_are_serialized(
    ctx: ActionContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two independent steps in the same wave both require confirmation
    -- the confirmation prompts must never overlap, even though the
    steps themselves are eligible to execute in parallel afterward."""
    monkeypatch.setattr(
        "jarvis.features.automation.executor.get_action",
        lambda action_type: _DelayAction(delay=0.01),
    )
    confirm_tracker = _Tracker()

    async def _tracking_confirm(message: str) -> bool:
        await confirm_tracker.enter()
        await asyncio.sleep(0.05)
        await confirm_tracker.exit()
        return True

    step1 = Step(action=ActionType.DELETE_FOLDER, args={"target": "a", "tracker": _Tracker()})
    step2 = Step(action=ActionType.DELETE_FOLDER, args={"target": "b", "tracker": _Tracker()})
    executor = ActionExecutor(ctx=ctx, undo=UndoManager())

    result = await executor.run_plan(_plan(step1, step2), confirm=_tracking_confirm)

    assert result.succeeded
    assert confirm_tracker.max_in_flight == 1


@pytest.mark.asyncio
async def test_dangerous_delete_still_denied_without_confirmation_in_parallel_executor(
    ctx: ActionContext,
) -> None:
    """Regression guard: the pre-existing single-step denial behaviour
    (test_automation_executor.py) must survive the wave rewrite too."""
    plan = _plan(Step(action=ActionType.DELETE_FOLDER, args={"target": "x"}))
    executor = ActionExecutor(ctx=ctx, undo=UndoManager())

    result = await executor.run_plan(plan)

    assert result.step_results[0].status is StepStatus.DENIED
