"""Unit tests for ``jarvis.core.lifecycle.background_task_manager.
BackgroundTaskManager`` (Milestone 9 Task Group C)."""

from __future__ import annotations

import asyncio

import pytest


def _manager(**kwargs):
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.lifecycle.background_task_manager import BackgroundTaskManager

    bus = EventBus()
    return BackgroundTaskManager(bus, **kwargs), bus


@pytest.mark.asyncio
async def test_submitted_task_completes_and_publishes_events() -> None:
    from jarvis.core.events.events import TaskCompletedEvent, TaskStartedEvent
    from jarvis.core.lifecycle.background_task_manager import TaskState

    manager, bus = _manager()
    started: list[TaskStartedEvent] = []
    completed: list[TaskCompletedEvent] = []
    bus.subscribe(TaskStartedEvent, started.append)
    bus.subscribe(TaskCompletedEvent, completed.append)

    ran = []

    async def _work() -> None:
        ran.append(1)

    task_id = manager.submit("my-task", _work)
    await manager.stop()

    assert ran == [1]
    info = manager.get(task_id)
    assert info is not None
    assert info.state == TaskState.COMPLETED
    assert info.name == "my-task"
    assert len(started) == 1
    assert len(completed) == 1
    assert completed[0].task_id == task_id


@pytest.mark.asyncio
async def test_failed_task_is_isolated_and_publishes_task_failed_event() -> None:
    from jarvis.core.events.events import TaskFailedEvent
    from jarvis.core.lifecycle.background_task_manager import TaskState

    manager, bus = _manager()
    failed: list[TaskFailedEvent] = []
    bus.subscribe(TaskFailedEvent, failed.append)

    async def _boom() -> None:
        raise RuntimeError("kaboom")

    ok_ran = []

    async def _ok() -> None:
        ok_ran.append(1)

    bad_id = manager.submit("bad", _boom)
    ok_id = manager.submit("ok", _ok)
    await manager.stop()

    assert ok_ran == [1]
    ok_info = manager.get(ok_id)
    bad_info = manager.get(bad_id)
    assert ok_info is not None and ok_info.state == TaskState.COMPLETED
    assert bad_info is not None and bad_info.state == TaskState.FAILED
    assert "kaboom" in bad_info.error
    assert len(failed) == 1
    assert failed[0].task_id == bad_id


@pytest.mark.asyncio
async def test_concurrency_is_bounded() -> None:
    manager, _ = _manager(max_concurrency=2)
    active = 0
    max_active = 0
    release = asyncio.Event()

    async def _slow() -> None:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await release.wait()
        active -= 1

    for _ in range(5):
        manager.submit("slow", _slow)
    await asyncio.sleep(0.05)  # let the first 2 acquire the semaphore

    assert max_active == 2
    release.set()
    await manager.stop()


@pytest.mark.asyncio
async def test_cancel_pending_task() -> None:
    from jarvis.core.lifecycle.background_task_manager import TaskState

    manager, _ = _manager(max_concurrency=1)
    blocker = asyncio.Event()

    async def _blocks() -> None:
        await blocker.wait()

    async def _never_runs() -> None:
        pytest.fail("should never run -- cancelled before its turn")

    manager.submit("blocker", _blocks)
    queued_id = manager.submit("queued", _never_runs)

    cancelled = manager.cancel(queued_id)
    assert cancelled is True

    # `cancel()` only schedules the cancellation -- `stop()`'s own
    # `gather()` over every non-done task is what reliably waits for
    # `CancelledError` to actually be delivered and handled, so check
    # the resulting state only after it returns.
    blocker.set()
    await manager.stop()

    queued_info = manager.get(queued_id)
    assert queued_info is not None and queued_info.state == TaskState.CANCELLED


@pytest.mark.asyncio
async def test_cancel_unknown_task_returns_false() -> None:
    manager, _ = _manager()
    assert manager.cancel("does-not-exist") is False
    await manager.stop()


@pytest.mark.asyncio
async def test_stop_is_safe_with_nothing_submitted() -> None:
    manager, _ = _manager()
    await manager.stop()  # must not raise


@pytest.mark.asyncio
async def test_tasks_property_lists_every_submission() -> None:
    manager, _ = _manager(max_concurrency=1)
    blocker = asyncio.Event()

    async def _blocks() -> None:
        await blocker.wait()

    a = manager.submit("a", _blocks)
    b = manager.submit("b", _blocks)

    ids = {info.task_id for info in manager.tasks}
    assert ids == {a, b}

    blocker.set()
    await manager.stop()
