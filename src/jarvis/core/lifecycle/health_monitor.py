"""``HealthMonitor`` -- lightweight, periodic runtime health snapshot
(Milestone 9 Task Group B). Reads process CPU/RAM via ``psutil``
(already a project dependency, see ``pyproject.toml``), asks
:class:`~jarvis.core.lifecycle.service_manager.ServiceManager` which
services are active/failed and how many restarts have happened this
run, and publishes :class:`~jarvis.core.events.events.HealthUpdatedEvent`
on every poll tick -- the WebSocket relay's ``health.updated`` payload
is this same dict, not a reinvented shape.

**Lightweight and non-blocking**, per this task group's own requirement:
``psutil.Process.cpu_percent(interval=None)`` and ``memory_info()`` are
both cheap, non-blocking calls (no ``time.sleep``, no disk I/O); the
poll loop is a plain ``asyncio`` task on the existing event loop, not a
thread.

**Future expansion (GPU, plugins, network, ...).** Rather than stub out
metrics nothing collects yet, :meth:`register_collector` lets a later
milestone add a named async collector without editing this class --
each collector's return value is merged into the snapshot under its own
key. No collectors are registered today.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

import psutil

from jarvis.core.events.events import HealthUpdatedEvent
from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.lifecycle.service_manager import ServiceManager

_logger = get_logger("jarvis.core.lifecycle.health_monitor")

HealthCollector = Callable[[], Awaitable[dict[str, Any]]]

DEFAULT_POLL_INTERVAL_SECONDS = 15.0


class HealthMonitor:
    def __init__(
        self,
        service_manager: ServiceManager,
        event_bus: EventBus,
        *,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    ) -> None:
        self._service_manager = service_manager
        self._event_bus = event_bus
        self._interval = poll_interval_seconds
        self._process = psutil.Process()
        # Establishes the psutil baseline -- its own first call always
        # returns a meaningless 0.0/None; every call from here on
        # compares against this baseline instead of blocking to measure
        # an interval.
        self._process.cpu_percent(interval=None)
        self._startup_duration_ms: float | None = None
        self._extra_collectors: dict[str, HealthCollector] = {}
        self._task: asyncio.Task[None] | None = None

    def mark_ready(self, startup_duration_ms: float) -> None:
        """Called once by Runtime Integration (Task Group B) after
        ``RuntimeManager.startup()`` completes -- this class has no
        other way to know when the startup sequence it didn't run
        itself actually finished."""
        self._startup_duration_ms = startup_duration_ms

    def register_collector(self, name: str, collector: HealthCollector) -> None:
        self._extra_collectors[name] = collector

    async def snapshot(self) -> dict[str, Any]:
        """One cheap, on-demand read -- safe to call directly (Developer
        Mode diagnostics, a REST refresh) without waiting for the next
        poll tick."""
        cpu_percent = self._process.cpu_percent(interval=None)
        memory_rss_bytes = self._process.memory_info().rss
        uptime_seconds = time.time() - self._process.create_time()

        service_snapshot = self._service_manager.snapshot()
        active_services = [s.name for s in service_snapshot if s.state == "running"]
        failed_services = [s.name for s in service_snapshot if s.state == "failed"]

        result: dict[str, Any] = {
            "cpu_percent": cpu_percent,
            "memory_rss_bytes": memory_rss_bytes,
            "uptime_seconds": uptime_seconds,
            "startup_duration_ms": self._startup_duration_ms,
            "active_services": active_services,
            "failed_services": failed_services,
            "restart_count": self._service_manager.restart_count,
            "status": "degraded" if failed_services else "healthy",
        }
        for name, collector in self._extra_collectors.items():
            try:
                result[name] = await collector()
            except Exception as err:
                result[name] = {"error": str(err)}
        return result

    async def poll_once(self) -> dict[str, Any]:
        snap = await self.snapshot()
        await self._event_bus.publish(HealthUpdatedEvent(snapshot=snap))
        return snap

    async def start(self) -> None:
        """Begin the periodic poll loop. Idempotent."""
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Cancel the poll loop. Idempotent, safe to call even if
        :meth:`start` was never called."""
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await self.poll_once()
            except Exception:
                _logger.exception("Health poll tick failed.")
            await asyncio.sleep(self._interval)
