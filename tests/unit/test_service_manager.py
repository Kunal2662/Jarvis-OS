"""Unit tests for ``jarvis.core.lifecycle.service_manager.ServiceManager``
(Milestone 9 Task Group B)."""

from __future__ import annotations

import pytest

from jarvis.core.interfaces.service import HealthStatus, ServiceStatus


class _FakeService:
    """A minimal, fully-controllable ``IService`` -- records call order
    onto a shared list so tests can assert cross-service sequencing."""

    def __init__(self, name: str, order: list[str], *, fail_start: bool = False) -> None:
        self.name = name
        self._order = order
        self._fail_start = fail_start
        self.healthy = True
        self.start_calls = 0

    async def initialize(self) -> None:
        self._order.append(f"{self.name}.initialize")

    async def start(self) -> None:
        self.start_calls += 1
        self._order.append(f"{self.name}.start")
        if self._fail_start:
            raise RuntimeError(f"{self.name} failed to start")

    async def stop(self) -> None:
        self._order.append(f"{self.name}.stop")

    async def health(self) -> HealthStatus:
        return HealthStatus(healthy=self.healthy, detail="" if self.healthy else "unhealthy")

    async def status(self) -> ServiceStatus:
        return ServiceStatus(name=self.name, state="ready")

    async def shutdown(self) -> None:
        self._order.append(f"{self.name}.shutdown")


def _manager():
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.lifecycle.service_manager import ServiceManager

    return ServiceManager(EventBus())


# --- Registration ------------------------------------------------------------


def test_register_and_lookup() -> None:
    manager = _manager()
    order: list[str] = []
    manager.register("a", _FakeService("a", order))

    assert manager.is_registered("a") is True
    assert manager.is_registered("b") is False
    assert manager.registered_names == ("a",)


def test_register_replaces_not_duplicates() -> None:
    manager = _manager()
    order: list[str] = []
    manager.register("a", _FakeService("a", order), priority=10)
    manager.register("a", _FakeService("a", order), priority=99)

    assert manager.registered_names == ("a",)


# --- Dependency / startup ordering -------------------------------------------


@pytest.mark.asyncio
async def test_dependencies_start_before_dependents() -> None:
    from jarvis.core.lifecycle.service_manager import ServiceState

    manager = _manager()
    order: list[str] = []
    # Registered out of dependency order on purpose -- ordering must come
    # from the dependency graph, not registration order.
    manager.register("chat", _FakeService("chat", order), dependencies=("conversation",))
    manager.register("conversation", _FakeService("conversation", order))

    await manager.start_all()

    assert order.index("conversation.start") < order.index("chat.start")
    assert manager.get_state("conversation") == ServiceState.RUNNING
    assert manager.get_state("chat") == ServiceState.RUNNING


@pytest.mark.asyncio
async def test_same_priority_preserves_registration_order() -> None:
    manager = _manager()
    order: list[str] = []
    manager.register("a", _FakeService("a", order), priority=10)
    manager.register("b", _FakeService("b", order), priority=10)
    manager.register("c", _FakeService("c", order), priority=10)

    await manager.start_all()
    assert order == [
        "a.initialize",
        "a.start",
        "b.initialize",
        "b.start",
        "c.initialize",
        "c.start",
    ]


def test_circular_dependency_raises() -> None:
    manager = _manager()
    order: list[str] = []
    manager.register("a", _FakeService("a", order), dependencies=("b",))
    manager.register("b", _FakeService("b", order), dependencies=("a",))

    with pytest.raises(ValueError, match="Circular or missing"):
        manager.snapshot()


# --- Failure isolation --------------------------------------------------------


@pytest.mark.asyncio
async def test_independent_service_failure_does_not_block_others() -> None:
    from jarvis.core.lifecycle.service_manager import ServiceState

    manager = _manager()
    order: list[str] = []
    manager.register("ok_1", _FakeService("ok_1", order), priority=0)
    manager.register("fails", _FakeService("fails", order, fail_start=True), priority=10)
    manager.register("ok_2", _FakeService("ok_2", order), priority=20)

    await manager.start_all()

    assert manager.get_state("ok_1") == ServiceState.RUNNING
    assert manager.get_state("fails") == ServiceState.FAILED
    assert manager.get_state("ok_2") == ServiceState.RUNNING


@pytest.mark.asyncio
async def test_dependent_of_failed_service_is_skipped_not_started() -> None:
    from jarvis.core.lifecycle.service_manager import ServiceState

    manager = _manager()
    order: list[str] = []
    manager.register("base", _FakeService("base", order, fail_start=True))
    manager.register("dependent", _FakeService("dependent", order), dependencies=("base",))

    await manager.start_all()

    assert manager.get_state("base") == ServiceState.FAILED
    assert manager.get_state("dependent") == ServiceState.FAILED
    assert "dependent.start" not in order  # never actually started


@pytest.mark.asyncio
async def test_failed_service_publishes_service_failed_event() -> None:
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.events.events import ServiceFailedEvent
    from jarvis.core.lifecycle.service_manager import ServiceManager

    bus = EventBus()
    published: list[ServiceFailedEvent] = []
    bus.subscribe(ServiceFailedEvent, published.append)
    manager = ServiceManager(bus)

    order: list[str] = []
    manager.register("fails", _FakeService("fails", order, fail_start=True))

    await manager.start_all()

    assert len(published) == 1
    assert published[0].service == "fails"


@pytest.mark.asyncio
async def test_start_all_is_idempotent() -> None:
    manager = _manager()
    order: list[str] = []
    manager.register("a", _FakeService("a", order))

    await manager.start_all()
    await manager.start_all()

    assert order.count("a.start") == 1


# --- Shutdown ordering --------------------------------------------------------


@pytest.mark.asyncio
async def test_stop_all_runs_in_reverse_dependency_order() -> None:
    manager = _manager()
    order: list[str] = []
    manager.register("conversation", _FakeService("conversation", order))
    manager.register("chat", _FakeService("chat", order), dependencies=("conversation",))

    await manager.start_all()
    order.clear()
    await manager.stop_all()

    assert order.index("chat.stop") < order.index("conversation.stop")


# --- Restart -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_restart_stops_then_starts_and_increments_counter() -> None:
    from jarvis.core.lifecycle.service_manager import ServiceState

    manager = _manager()
    order: list[str] = []
    service = _FakeService("a", order)
    manager.register("a", service)

    await manager.start_all()
    order.clear()
    await manager.restart("a")

    assert order == ["a.stop", "a.start"]
    assert manager.get_state("a") == ServiceState.RUNNING
    assert manager.restart_count == 1
    assert service.start_calls == 2


@pytest.mark.asyncio
async def test_restart_does_not_cascade_to_dependents() -> None:
    manager = _manager()
    order: list[str] = []
    manager.register("conversation", _FakeService("conversation", order))
    manager.register("chat", _FakeService("chat", order), dependencies=("conversation",))

    await manager.start_all()
    order.clear()
    await manager.restart("conversation")

    assert "chat.stop" not in order
    assert "chat.start" not in order


@pytest.mark.asyncio
async def test_restart_failure_marks_failed_and_publishes_event() -> None:
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.events.events import ServiceFailedEvent
    from jarvis.core.lifecycle.service_manager import ServiceManager, ServiceState

    bus = EventBus()
    published: list[ServiceFailedEvent] = []
    bus.subscribe(ServiceFailedEvent, published.append)
    manager = ServiceManager(bus)

    order: list[str] = []
    service = _FakeService("a", order)
    manager.register("a", service)
    await manager.start_all()

    service._fail_start = True
    with pytest.raises(RuntimeError):
        await manager.restart("a")

    assert manager.get_state("a") == ServiceState.FAILED
    assert any(e.service == "a" for e in published)


# --- Health --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_poll_health_reports_unhealthy_and_marks_failed() -> None:
    from jarvis.core.lifecycle.service_manager import ServiceState

    manager = _manager()
    order: list[str] = []
    service = _FakeService("a", order)
    manager.register("a", service)
    await manager.start_all()

    service.healthy = False
    health = await manager.poll_health()

    assert health["a"].healthy is False
    assert manager.get_state("a") == ServiceState.FAILED


@pytest.mark.asyncio
async def test_poll_health_skips_non_running_services() -> None:
    manager = _manager()
    order: list[str] = []
    manager.register("a", _FakeService("a", order))
    # Never started.

    health = await manager.poll_health()
    assert health == {}
