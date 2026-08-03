"""Unit tests for ``jarvis.core.lifecycle.health_monitor.HealthMonitor``
(Milestone 9 Task Group B)."""

from __future__ import annotations

import asyncio

import pytest

from jarvis.core.interfaces.service import HealthStatus, ServiceStatus


class _FakeService:
    def __init__(self) -> None:
        self.healthy = True

    async def initialize(self) -> None:
        pass

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def health(self) -> HealthStatus:
        return HealthStatus(healthy=self.healthy)

    async def status(self) -> ServiceStatus:
        return ServiceStatus(name="fake", state="ready")

    async def shutdown(self) -> None:
        pass


def _service_manager_and_bus():
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.lifecycle.service_manager import ServiceManager

    bus = EventBus()
    return ServiceManager(bus), bus


@pytest.mark.asyncio
async def test_snapshot_reports_active_and_failed_services() -> None:
    from jarvis.core.lifecycle.health_monitor import HealthMonitor

    service_manager, bus = _service_manager_and_bus()
    ok = _FakeService()
    failing = _FakeService()
    service_manager.register("ok", ok)
    service_manager.register("failing", failing)
    await service_manager.start_all()

    monitor = HealthMonitor(service_manager, bus)
    failing.healthy = False
    await service_manager.poll_health()  # marks "failing" FAILED, as HealthMonitor itself will see

    snap = await monitor.snapshot()

    assert snap["active_services"] == ["ok"]
    assert snap["failed_services"] == ["failing"]
    assert snap["status"] == "degraded"
    assert isinstance(snap["cpu_percent"], float)
    assert snap["memory_rss_bytes"] > 0
    assert snap["uptime_seconds"] > 0
    assert snap["restart_count"] == 0


@pytest.mark.asyncio
async def test_snapshot_status_healthy_when_nothing_failed() -> None:
    from jarvis.core.lifecycle.health_monitor import HealthMonitor

    service_manager, bus = _service_manager_and_bus()
    service_manager.register("ok", _FakeService())
    await service_manager.start_all()

    monitor = HealthMonitor(service_manager, bus)
    snap = await monitor.snapshot()

    assert snap["status"] == "healthy"
    assert snap["failed_services"] == []


@pytest.mark.asyncio
async def test_mark_ready_populates_startup_duration() -> None:
    from jarvis.core.lifecycle.health_monitor import HealthMonitor

    service_manager, bus = _service_manager_and_bus()
    monitor = HealthMonitor(service_manager, bus)

    assert (await monitor.snapshot())["startup_duration_ms"] is None
    monitor.mark_ready(123.4)
    assert (await monitor.snapshot())["startup_duration_ms"] == 123.4


@pytest.mark.asyncio
async def test_restart_count_reflects_service_manager() -> None:
    from jarvis.core.lifecycle.health_monitor import HealthMonitor

    service_manager, bus = _service_manager_and_bus()
    service_manager.register("ok", _FakeService())
    await service_manager.start_all()
    await service_manager.restart("ok")

    monitor = HealthMonitor(service_manager, bus)
    snap = await monitor.snapshot()
    assert snap["restart_count"] == 1


@pytest.mark.asyncio
async def test_register_collector_extends_snapshot() -> None:
    from jarvis.core.lifecycle.health_monitor import HealthMonitor

    service_manager, bus = _service_manager_and_bus()
    monitor = HealthMonitor(service_manager, bus)

    async def _fake_gpu() -> dict:
        return {"utilization_percent": 42}

    monitor.register_collector("gpu", _fake_gpu)
    snap = await monitor.snapshot()
    assert snap["gpu"] == {"utilization_percent": 42}


@pytest.mark.asyncio
async def test_collector_failure_is_isolated() -> None:
    from jarvis.core.lifecycle.health_monitor import HealthMonitor

    service_manager, bus = _service_manager_and_bus()
    monitor = HealthMonitor(service_manager, bus)

    async def _broken() -> dict:
        raise RuntimeError("boom")

    monitor.register_collector("broken", _broken)
    snap = await monitor.snapshot()
    assert "error" in snap["broken"]
    assert snap["status"] in ("healthy", "degraded")  # snapshot still completed


@pytest.mark.asyncio
async def test_poll_once_publishes_health_updated_event() -> None:
    from jarvis.core.events.events import HealthUpdatedEvent
    from jarvis.core.lifecycle.health_monitor import HealthMonitor

    service_manager, bus = _service_manager_and_bus()
    published: list[HealthUpdatedEvent] = []
    bus.subscribe(HealthUpdatedEvent, published.append)
    monitor = HealthMonitor(service_manager, bus)

    snap = await monitor.poll_once()

    assert len(published) == 1
    assert published[0].snapshot == snap


@pytest.mark.asyncio
async def test_start_and_stop_poll_loop_is_idempotent_and_cancellable() -> None:
    from jarvis.core.lifecycle.health_monitor import HealthMonitor

    service_manager, bus = _service_manager_and_bus()
    monitor = HealthMonitor(service_manager, bus, poll_interval_seconds=1000)

    await monitor.start()
    await monitor.start()  # idempotent, no second task
    await asyncio.sleep(0)  # let the loop task actually start running
    await monitor.stop()
    await monitor.stop()  # idempotent, no error on double-stop
