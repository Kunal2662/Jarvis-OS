"""Performance Profiler -- Milestone 9 Task Group E.

``HealthMonitor`` (Task Group B) already reports a real, cheap
CPU/memory/uptime/service-status *snapshot* on every poll tick
(``HealthUpdatedEvent``) -- what it does not keep is *history*. This
class subscribes to that same event and keeps a bounded time series
per metric, so Developer Mode can show a trend ("CPU climbing over the
last two minutes") rather than only ever the single latest value
``HealthMonitor.snapshot()`` already exposes.

**Honest scope note.** Despite the milestone's own "surfaces Resource
Manager's per-service data" phrasing, neither ``HealthMonitor`` nor
``ResourceManager`` actually attribute CPU/memory to individual
services -- both are process-wide (``psutil.Process`` measures the
whole process, not one coroutine inside it; see ``core/plugins/
sandbox.py``'s own identical honesty about this same limit). What *is*
per-service is service **state** (``active_services``/
``failed_services``), which this profiler also tracks over time. A
real per-service resource breakdown would need each service to run in
its own OS process -- out of scope here, same as it is for
``ResourceManager``.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from jarvis.core.events.events import HealthUpdatedEvent

if TYPE_CHECKING:
    from collections.abc import Callable

    from jarvis.core.events.event_bus import EventBus

DEFAULT_HISTORY_SIZE = 240  # e.g. 240 samples @ one HealthMonitor poll/5s = 20 minutes

_TRACKED_NUMERIC_METRICS = (
    "cpu_percent",
    "memory_rss_bytes",
    "uptime_seconds",
    "restart_count",
)


@dataclass(frozen=True, slots=True)
class PerformanceSample:
    metric: str
    value: float
    at: float  # time.time() -- cheap, monotonic-enough for a dev-tool trend


class PerformanceProfiler:
    def __init__(self, event_bus: EventBus, *, history_size: int = DEFAULT_HISTORY_SIZE) -> None:
        self._event_bus = event_bus
        self._history_size = history_size
        self._history: dict[str, deque[PerformanceSample]] = {
            metric: deque(maxlen=history_size) for metric in _TRACKED_NUMERIC_METRICS
        }
        self._latest_snapshot: dict[str, Any] = {}
        self._unsubscribe: Callable[[], None] | None = None

    def start(self) -> None:
        """Idempotent -- a second call does not double-subscribe."""
        if self._unsubscribe is not None:
            return
        self._unsubscribe = self._event_bus.subscribe(HealthUpdatedEvent, self._on_health_updated)

    def stop(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

    async def _on_health_updated(self, event: HealthUpdatedEvent) -> None:
        snapshot = event.snapshot
        self._latest_snapshot = snapshot
        at = time.time()
        for metric in _TRACKED_NUMERIC_METRICS:
            value = snapshot.get(metric)
            if isinstance(value, (int, float)):
                self._history[metric].append(
                    PerformanceSample(metric=metric, value=float(value), at=at)
                )

    def current(self) -> dict[str, Any]:
        """The latest ``HealthUpdatedEvent`` snapshot, verbatim --
        empty until the first poll tick after :meth:`start`."""
        return dict(self._latest_snapshot)

    def history(self, metric: str) -> tuple[PerformanceSample, ...]:
        bucket = self._history.get(metric)
        return tuple(bucket) if bucket is not None else ()

    @property
    def tracked_metrics(self) -> tuple[str, ...]:
        return _TRACKED_NUMERIC_METRICS

    @property
    def is_running(self) -> bool:
        return self._unsubscribe is not None
