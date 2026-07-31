"""Async / event-loop utilities."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Coroutine
from typing import Any, TypeVar

from jarvis.core.logging.logger import get_logger

_T = TypeVar("_T")
_logger = get_logger("jarvis.utils.async_utils")


def run_sync(coro: Awaitable[_T]) -> _T:
    """Run *coro* to completion from synchronous code (no running loop)."""
    return asyncio.run(coro)  # type: ignore[arg-type]


async def gather_with_concurrency(limit: int, *coros: Awaitable[_T]) -> list[_T]:
    """``asyncio.gather`` with a concurrency cap."""
    semaphore = asyncio.Semaphore(limit)

    async def _wrap(c: Awaitable[_T]) -> _T:
        async with semaphore:
            return await c

    return await asyncio.gather(*(_wrap(c) for c in coros))


# ---------------------------------------------------------------------------
# fire_and_forget -- audit finding (Milestones 0-5 completion audit)
# ---------------------------------------------------------------------------
# Every bare ``asyncio.ensure_future(coro)`` call whose return value isn't
# stored anywhere is a real bug, not just a style nit -- CPython's asyncio
# event loop tracks running tasks in a *weak* set, so a task with no other
# strong reference can be garbage-collected before it finishes, silently
# killing it mid-execution. This was present at 55 call sites across the Qt
# controller/dialog/view layer (every fire-and-forget button click,
# streaming start, settings write, ...) -- exactly what the
# "Task was destroyed but it is pending!" warnings seen throughout this
# project's own test runs were reporting.
#
# ``fire_and_forget()`` fixes it in one place: keep a strong reference in a
# module-level set until the task completes, then discard it via a
# done-callback so the set never grows unbounded. Drop-in replacement for
# ``asyncio.ensure_future`` -- same return value (the created ``Task``), same
# "don't block, don't await" call-site semantics, just no longer susceptible
# to premature GC.
_background_tasks: set[asyncio.Task[Any]] = set()


def fire_and_forget(coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
    """Schedule *coro* on the currently-running event loop, keeping a
    strong reference so it can't be garbage-collected before it finishes.
    Requires a running loop (unlike ``ui.async_utils.fire_and_forget``,
    which additionally tolerates being called before the qasync loop has
    started) -- every call site this replaced was already only ever
    invoked from a running Qt slot/coroutine, so that's never been a gap
    in practice.

    Returns the created ``Task`` in case the caller wants to keep their
    own reference too (e.g. to cancel it later) -- assigning the result
    remains fine and encouraged; this only fixes the case where nobody
    does.
    """
    task = asyncio.ensure_future(coro)
    _background_tasks.add(task)
    task.add_done_callback(_on_task_done)
    return task


def _on_task_done(task: asyncio.Task[Any]) -> None:
    _background_tasks.discard(task)
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        _logger.warning("Background fire-and-forget task failed: {}", exc)


def background_task_count() -> int:
    """Number of currently in-flight fire-and-forget tasks -- exposed for
    diagnostics/tests, not meant to drive application logic."""
    return len(_background_tasks)
