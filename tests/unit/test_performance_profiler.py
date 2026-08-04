"""Unit tests for ``jarvis.core.devtools.performance_profiler``
(Milestone 9 Task Group E)."""

from __future__ import annotations

import pytest

from jarvis.core.devtools.performance_profiler import PerformanceProfiler
from jarvis.core.events.event_bus import EventBus
from jarvis.core.events.events import HealthUpdatedEvent


def _snapshot(**overrides):
    base = {
        "cpu_percent": 5.0,
        "memory_rss_bytes": 100_000_000,
        "uptime_seconds": 12.0,
        "startup_duration_ms": 250.0,
        "active_services": ["chat"],
        "failed_services": [],
        "restart_count": 0,
        "status": "healthy",
    }
    base.update(overrides)
    return base


def test_not_running_until_started():
    profiler = PerformanceProfiler(EventBus())
    assert profiler.is_running is False


def test_current_empty_before_any_tick():
    profiler = PerformanceProfiler(EventBus())
    assert profiler.current() == {}


@pytest.mark.asyncio
async def test_start_records_history_on_health_updated():
    bus = EventBus()
    profiler = PerformanceProfiler(bus)
    profiler.start()

    await bus.publish(HealthUpdatedEvent(snapshot=_snapshot(cpu_percent=10.0)))

    assert profiler.current()["cpu_percent"] == 10.0
    history = profiler.history("cpu_percent")
    assert len(history) == 1
    assert history[0].value == 10.0
    profiler.stop()


@pytest.mark.asyncio
async def test_multiple_ticks_accumulate_history():
    bus = EventBus()
    profiler = PerformanceProfiler(bus)
    profiler.start()

    for value in (1.0, 2.0, 3.0):
        await bus.publish(HealthUpdatedEvent(snapshot=_snapshot(cpu_percent=value)))

    history = profiler.history("cpu_percent")
    assert [s.value for s in history] == [1.0, 2.0, 3.0]
    profiler.stop()


@pytest.mark.asyncio
async def test_history_bounded_by_history_size():
    bus = EventBus()
    profiler = PerformanceProfiler(bus, history_size=2)
    profiler.start()

    for value in (1.0, 2.0, 3.0):
        await bus.publish(HealthUpdatedEvent(snapshot=_snapshot(cpu_percent=value)))

    history = profiler.history("cpu_percent")
    assert [s.value for s in history] == [2.0, 3.0]
    profiler.stop()


@pytest.mark.asyncio
async def test_stop_unsubscribes():
    bus = EventBus()
    profiler = PerformanceProfiler(bus)
    profiler.start()
    profiler.stop()
    assert profiler.is_running is False

    await bus.publish(HealthUpdatedEvent(snapshot=_snapshot(cpu_percent=99.0)))

    assert profiler.history("cpu_percent") == ()


def test_history_unknown_metric_returns_empty():
    profiler = PerformanceProfiler(EventBus())
    assert profiler.history("no_such_metric") == ()


@pytest.mark.asyncio
async def test_non_numeric_fields_are_not_tracked_as_history():
    bus = EventBus()
    profiler = PerformanceProfiler(bus)
    profiler.start()
    await bus.publish(HealthUpdatedEvent(snapshot=_snapshot()))
    assert "active_services" not in profiler.tracked_metrics
    profiler.stop()


def test_start_is_idempotent():
    bus = EventBus()
    profiler = PerformanceProfiler(bus)
    profiler.start()
    profiler.start()
    assert profiler.is_running is True
    profiler.stop()
    assert profiler.is_running is False
