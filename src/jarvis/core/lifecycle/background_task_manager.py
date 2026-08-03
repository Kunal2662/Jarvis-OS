"""``BackgroundTaskManager`` -- a supervised task queue for long-running,
non-request work (Milestone 9 Task Group C, Reliability module).

Distinct from M7's ``ActionExecutor`` (user-triggered automation
plans, not background runtime maintenance) and from the frontend's
``stores/background-tasks.store.ts`` (a display-only store with no
real queue behind it -- see ``MASTER_ROADMAP.md``'s M8 Deferred
Backlog). This is the real backend queue that store's future UI
eventually reads from over the Runtime WebSocket API's new ``task.*``
events (``core/lifecycle/runtime_ws_hub.py``).

Bounded concurrency (``asyncio.Semaphore``) plus per-task fault
isolation -- one task's exception never crashes the manager or any
other task, the same guarantee every other M9 lifecycle component
(``RuntimeManager``, ``ServiceManager``) already makes.
"""

from __future__ import annotations

import asyncio
import enum
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from jarvis.core.events.events import TaskCompletedEvent, TaskFailedEvent, TaskStartedEvent
from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.core.events.event_bus import EventBus

_logger = get_logger("jarvis.core.lifecycle.background_task_manager")

DEFAULT_MAX_CONCURRENCY = 4

TaskFactory = Callable[[], Awaitable[Any]]


class TaskState(enum.StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class TaskInfo:
    task_id: str
    name: str
    state: TaskState
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str = ""


@dataclass(slots=True)
class _Entry:
    task_id: str
    name: str
    factory: TaskFactory
    state: TaskState
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str = ""
    asyncio_task: asyncio.Task[None] | None = None

    def as_info(self) -> TaskInfo:
        return TaskInfo(
            self.task_id,
            self.name,
            self.state,
            self.created_at,
            self.started_at,
            self.finished_at,
            self.error,
        )


class BackgroundTaskManager:
    def __init__(
        self, event_bus: EventBus, *, max_concurrency: int = DEFAULT_MAX_CONCURRENCY
    ) -> None:
        self._event_bus = event_bus
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._entries: dict[str, _Entry] = {}

    async def start(self) -> None:
        """No-op today -- kept for symmetry with every other M9
        lifecycle component's ``start()``/``stop()`` shape, and as the
        real place a future "resume persisted queue" step would go."""

    def submit(self, name: str, factory: TaskFactory) -> str:
        """Queue *factory* (a zero-arg callable returning an
        awaitable) for supervised execution. Returns a task id
        immediately -- execution begins as soon as a concurrency slot
        is free."""
        task_id = uuid.uuid4().hex
        entry = _Entry(
            task_id=task_id,
            name=name,
            factory=factory,
            state=TaskState.PENDING,
            created_at=datetime.now(UTC),
        )
        self._entries[task_id] = entry
        entry.asyncio_task = asyncio.ensure_future(self._run(entry))
        # A task cancelled before its coroutine ever gets a first
        # scheduling turn never executes a single line of its own body
        # -- including `_run()`'s own `except CancelledError` handler
        # (Python throws into an unstarted coroutine without entering
        # it at all). This done-callback is the fallback that still
        # marks it CANCELLED in that case; it's a no-op whenever `_run`
        # already updated the state itself.
        entry.asyncio_task.add_done_callback(self._make_done_callback(entry))
        return task_id

    @staticmethod
    def _make_done_callback(entry: _Entry) -> Callable[[asyncio.Task[None]], None]:
        def _on_done(task: asyncio.Task[None]) -> None:
            if task.cancelled() and entry.state in (TaskState.PENDING, TaskState.RUNNING):
                entry.state = TaskState.CANCELLED
                entry.finished_at = datetime.now(UTC)

        return _on_done

    async def _run(self, entry: _Entry) -> None:
        # The outer try/except wraps semaphore acquisition too, not just
        # `factory()` -- cancelling a still-PENDING task (blocked
        # waiting for a free concurrency slot) raises CancelledError at
        # the `async with` itself, before the inner try/except below
        # would ever see it. Without this outer layer such a task
        # silently stayed PENDING forever instead of becoming CANCELLED.
        try:
            async with self._semaphore:
                entry.state = TaskState.RUNNING
                entry.started_at = datetime.now(UTC)
                _logger.info("Background task {!r} ({}) started.", entry.name, entry.task_id)
                await self._event_bus.publish(
                    TaskStartedEvent(task_id=entry.task_id, name=entry.name)
                )
                started = time.monotonic()
                try:
                    await entry.factory()
                except Exception as err:
                    entry.state = TaskState.FAILED
                    entry.error = str(err)
                    entry.finished_at = datetime.now(UTC)
                    _logger.exception(
                        "Background task {!r} ({}) failed.", entry.name, entry.task_id
                    )
                    await self._event_bus.publish(
                        TaskFailedEvent(task_id=entry.task_id, name=entry.name, detail=str(err))
                    )
                    return

                entry.state = TaskState.COMPLETED
                entry.finished_at = datetime.now(UTC)
                duration_ms = (time.monotonic() - started) * 1000
                _logger.info(
                    "Background task {!r} ({}) completed ({:.0f}ms).",
                    entry.name,
                    entry.task_id,
                    duration_ms,
                )
                await self._event_bus.publish(
                    TaskCompletedEvent(
                        task_id=entry.task_id, name=entry.name, duration_ms=duration_ms
                    )
                )
        except asyncio.CancelledError:
            entry.state = TaskState.CANCELLED
            entry.finished_at = datetime.now(UTC)
            raise

    def get(self, task_id: str) -> TaskInfo | None:
        entry = self._entries.get(task_id)
        return None if entry is None else entry.as_info()

    @property
    def tasks(self) -> tuple[TaskInfo, ...]:
        return tuple(entry.as_info() for entry in self._entries.values())

    def cancel(self, task_id: str) -> bool:
        """Request cancellation of a pending or running task. Returns
        ``False`` for an unknown id or one already in a terminal
        state -- never raises."""
        entry = self._entries.get(task_id)
        if entry is None or entry.asyncio_task is None:
            return False
        if entry.state not in (TaskState.PENDING, TaskState.RUNNING):
            return False
        entry.asyncio_task.cancel()
        return True

    async def stop(self) -> None:
        """Wait for every task still running (or being cancelled) to
        actually finish -- graceful drain, not an abrupt kill. Safe to
        call even if nothing was ever submitted."""
        pending = [
            entry.asyncio_task
            for entry in self._entries.values()
            if entry.asyncio_task is not None and not entry.asyncio_task.done()
        ]
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
