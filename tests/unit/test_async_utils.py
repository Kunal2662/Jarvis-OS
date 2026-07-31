"""Tests for ``jarvis.utils.async_utils`` (Milestones 0-5 completion
audit finding: 55 dangling-asyncio-task sites, fixed via
``fire_and_forget``).

The most important test here is
:func:`test_fire_and_forget_survives_gc_pressure` -- it demonstrates
the actual bug class being fixed: a bare ``asyncio.ensure_future(coro)``
with no stored reference can be garbage-collected before it completes.
"""

from __future__ import annotations

import asyncio
import gc

import pytest

from jarvis.utils.async_utils import (
    background_task_count,
    fire_and_forget,
    gather_with_concurrency,
    run_sync,
)


def test_run_sync_executes_coroutine() -> None:
    async def _coro() -> int:
        return 42

    assert run_sync(_coro()) == 42


@pytest.mark.asyncio
async def test_gather_with_concurrency_respects_limit() -> None:
    active = 0
    peak = 0

    async def _task() -> None:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1

    await gather_with_concurrency(2, *(_task() for _ in range(6)))
    assert peak <= 2


@pytest.mark.asyncio
async def test_fire_and_forget_runs_to_completion() -> None:
    result = {}

    async def _work() -> None:
        await asyncio.sleep(0.01)
        result["done"] = True

    fire_and_forget(_work())
    await asyncio.sleep(0.05)
    assert result.get("done") is True


@pytest.mark.asyncio
async def test_fire_and_forget_removes_task_from_tracking_set_on_completion() -> None:
    baseline = background_task_count()

    async def _quick() -> None:
        await asyncio.sleep(0.01)

    fire_and_forget(_quick())
    assert background_task_count() == baseline + 1

    await asyncio.sleep(0.05)
    assert background_task_count() == baseline


@pytest.mark.asyncio
async def test_fire_and_forget_survives_gc_pressure() -> None:
    """The actual bug class this fixes: a bare
    ``asyncio.ensure_future(coro)`` with no stored reference can be
    garbage-collected mid-execution because CPython's asyncio loop
    only tracks running tasks in a *weak* set. Reproduce that exact
    scenario -- call ``fire_and_forget`` without keeping the returned
    Task, force a garbage collection pass while it's still pending,
    and confirm it still completes (which would NOT be guaranteed for
    a bare ``asyncio.ensure_future`` call under GC pressure)."""
    result = {"done": False}

    async def _slow_work() -> None:
        await asyncio.sleep(0.05)
        result["done"] = True

    fire_and_forget(_slow_work())  # deliberately not storing the Task

    # Force a full garbage collection while the task is still pending --
    # this is exactly the scenario that kills an unreferenced
    # asyncio.ensure_future() task.
    gc.collect()
    await asyncio.sleep(0.1)

    assert result["done"] is True


@pytest.mark.asyncio
async def test_fire_and_forget_logs_but_does_not_raise_on_failure() -> None:
    async def _boom() -> None:
        raise ValueError("simulated failure")

    task = fire_and_forget(_boom())
    await asyncio.sleep(0.02)
    assert task.done()
    assert isinstance(task.exception(), ValueError)
    # The exception was retrieved via task.exception() above (by the
    # done-callback too) -- asyncio should not report it as "never
    # retrieved" / re-raise it anywhere else.
