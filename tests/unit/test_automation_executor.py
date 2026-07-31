"""Integration-flavoured unit tests for :class:`ActionExecutor`.

Uses the real filesystem actions (create/delete/move folder) against
``tmp_path`` so undo/rollback are exercised end to end without mocking
the thing under test.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from jarvis.core.config.settings import Settings
from jarvis.domain.automation.models import ActionType, ExecutionPlan, Step, StepStatus
from jarvis.features.automation.executor import ActionExecutor
from jarvis.features.automation.permission import PermissionGate
from jarvis.features.automation.undo import UndoManager
from jarvis.infrastructure.automation.actions.base import ActionContext
from tests.fakes.fake_os_automation import FakeOSAutomation


@pytest.fixture()
def ctx(tmp_path: Path) -> ActionContext:
    settings = Settings(data_dir=tmp_path)
    return ActionContext(settings=settings, os_automation=FakeOSAutomation())


async def _always_confirm(message: str) -> bool:
    return True


@pytest.mark.asyncio
async def test_single_step_plan_succeeds(ctx: ActionContext, tmp_path: Path) -> None:
    plan = ExecutionPlan(
        raw_text="create folder",
        steps=[Step(action=ActionType.CREATE_FOLDER, args={"target": str(tmp_path / "Work")})],
    )
    executor = ActionExecutor(ctx=ctx, undo=UndoManager())
    result = await executor.run_plan(plan)

    assert result.succeeded
    assert (tmp_path / "Work").is_dir()


@pytest.mark.asyncio
async def test_failed_step_rolls_back_prior_successful_steps(
    ctx: ActionContext, tmp_path: Path
) -> None:
    work_dir = tmp_path / "Work"
    plan = ExecutionPlan(
        raw_text="create then explode",
        steps=[
            Step(action=ActionType.CREATE_FOLDER, args={"target": str(work_dir)}),
            Step(
                action=ActionType.MOVE,
                args={"source": str(tmp_path / "nope.txt"), "destination": str(work_dir)},
            ),
        ],
    )
    undo = UndoManager()
    executor = ActionExecutor(ctx=ctx, undo=undo)
    result = await executor.run_plan(plan)

    assert not result.succeeded
    assert result.step_results[0].status is StepStatus.ROLLED_BACK
    assert result.step_results[1].status is StepStatus.FAILED
    assert not work_dir.exists()


@pytest.mark.asyncio
async def test_dependency_skip_when_earlier_step_fails(ctx: ActionContext, tmp_path: Path) -> None:
    plan = ExecutionPlan(raw_text="chain")
    step1 = Step(
        action=ActionType.MOVE,
        args={"source": str(tmp_path / "missing.txt"), "destination": str(tmp_path)},
    )
    step2 = Step(
        action=ActionType.CREATE_FOLDER,
        args={"target": str(tmp_path / "ShouldNotRun")},
        depends_on=[step1.id],
    )
    plan.steps = [step1, step2]

    executor = ActionExecutor(ctx=ctx, undo=UndoManager())
    result = await executor.run_plan(plan)

    assert result.step_results[0].status is StepStatus.FAILED
    assert result.step_results[1].status is StepStatus.SKIPPED
    assert not (tmp_path / "ShouldNotRun").exists()


@pytest.mark.asyncio
async def test_dangerous_delete_is_denied_without_confirmation(
    ctx: ActionContext, tmp_path: Path
) -> None:
    plan = ExecutionPlan(
        raw_text="delete folder",
        steps=[Step(action=ActionType.DELETE_FOLDER, args={"target": str(tmp_path)})],
    )
    executor = ActionExecutor(
        ctx=ctx,
        permission=PermissionGate(auto_deny_when_unconfirmable=True),
        undo=UndoManager(),
    )
    result = await executor.run_plan(plan)
    assert result.step_results[0].status is StepStatus.DENIED


@pytest.mark.asyncio
async def test_dangerous_delete_proceeds_when_confirmed(ctx: ActionContext, tmp_path: Path) -> None:
    target = tmp_path / "DeleteMe"
    target.mkdir()
    plan = ExecutionPlan(
        raw_text="delete folder",
        steps=[Step(action=ActionType.DELETE_FOLDER, args={"target": str(target)})],
    )
    executor = ActionExecutor(ctx=ctx, undo=UndoManager())
    result = await executor.run_plan(plan, confirm=_always_confirm)

    assert result.succeeded
    assert not target.exists()


@pytest.mark.asyncio
async def test_retries_before_failing(ctx: ActionContext, tmp_path: Path) -> None:
    plan = ExecutionPlan(
        raw_text="move missing with retries",
        steps=[
            Step(
                action=ActionType.MOVE,
                args={"source": str(tmp_path / "still_missing.txt"), "destination": str(tmp_path)},
                max_retries=2,
            )
        ],
    )
    executor = ActionExecutor(ctx=ctx, undo=UndoManager(), retry_backoff_seconds=0.01)
    result = await executor.run_plan(plan)

    assert result.step_results[0].status is StepStatus.FAILED
    assert result.step_results[0].attempts == 3


@pytest.mark.asyncio
async def test_step_timeout_cancels_hung_action(
    ctx: ActionContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Audit fix (Milestones 0-5 completion audit): previously, no
    executor-level timeout existed at all -- an action type with no
    internal timeout of its own (unlike e.g. shell commands, which
    enforce their own 30s timeout) could hang the whole plan forever.
    Simulate a hung action directly (rather than actually sleeping
    ``default_step_timeout_seconds``) by monkeypatching the action
    registry so this test runs fast."""
    from jarvis.infrastructure.automation.actions.base import BaseAction

    class _HangingAction(BaseAction):
        reversible = False

        async def run(self, context: ActionContext, args: dict) -> dict:
            await asyncio.sleep(10)  # would hang forever without the timeout guard
            return {}

        async def undo(self, context: ActionContext, undo_args: dict) -> None:
            return None

    monkeypatch.setattr(
        "jarvis.features.automation.executor.get_action",
        lambda action_type: _HangingAction(),
    )

    plan = ExecutionPlan(
        raw_text="hang",
        steps=[Step(action=ActionType.SCREENSHOT, timeout_seconds=0.05)],
    )
    executor = ActionExecutor(ctx=ctx, undo=UndoManager(), retry_backoff_seconds=0.01)

    result = await asyncio.wait_for(executor.run_plan(plan), timeout=5)

    assert result.step_results[0].status is StepStatus.FAILED
    assert "timed out" in result.step_results[0].error.lower()
    assert result.step_results[0].error != ""  # not the blank TimeoutError() string


@pytest.mark.asyncio
async def test_step_timeout_defaults_to_executor_setting(
    ctx: ActionContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A Step with no explicit timeout_seconds (the common case -- every
    existing caller before this fix) uses the executor's default rather
    than being unbounded."""
    from jarvis.infrastructure.automation.actions.base import BaseAction

    class _HangingAction(BaseAction):
        reversible = False

        async def run(self, context: ActionContext, args: dict) -> dict:
            await asyncio.sleep(10)
            return {}

        async def undo(self, context: ActionContext, undo_args: dict) -> None:
            return None

    monkeypatch.setattr(
        "jarvis.features.automation.executor.get_action",
        lambda action_type: _HangingAction(),
    )

    plan = ExecutionPlan(raw_text="hang", steps=[Step(action=ActionType.SCREENSHOT)])
    executor = ActionExecutor(
        ctx=ctx, undo=UndoManager(), retry_backoff_seconds=0.01, default_step_timeout_seconds=0.05
    )

    result = await asyncio.wait_for(executor.run_plan(plan), timeout=5)

    assert result.step_results[0].status is StepStatus.FAILED
    assert "timed out" in result.step_results[0].error.lower()
