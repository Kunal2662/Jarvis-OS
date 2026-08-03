"""Unit tests for ``jarvis.core.lifecycle.resource_manager.
ResourceManager`` (Milestone 9 Task Group C)."""

from __future__ import annotations

import pytest


def _manager():
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.lifecycle.resource_manager import ResourceManager

    bus = EventBus()
    return ResourceManager(bus), bus


def test_register_and_list_budgets() -> None:
    manager, _ = _manager()
    manager.register_budget("cpu", "cpu_percent", 90.0)
    manager.register_budget("memory", "memory_rss_bytes", 4096.0)

    assert {b.resource for b in manager.budgets} == {"cpu", "memory"}


def test_unregister_budget() -> None:
    manager, _ = _manager()
    manager.register_budget("cpu", "cpu_percent", 90.0)
    manager.unregister_budget("cpu")

    assert manager.budgets == ()
    assert manager.is_exceeded("cpu") is False


@pytest.mark.asyncio
async def test_within_budget_does_not_publish() -> None:
    from jarvis.core.events.events import HealthUpdatedEvent, ResourceBudgetExceededEvent

    manager, bus = _manager()
    manager.register_budget("cpu", "cpu_percent", 90.0)
    manager.start()

    published: list[ResourceBudgetExceededEvent] = []
    bus.subscribe(ResourceBudgetExceededEvent, published.append)

    await bus.publish(HealthUpdatedEvent(snapshot={"cpu_percent": 10.0}))

    assert published == []
    assert manager.is_exceeded("cpu") is False
    manager.stop()


@pytest.mark.asyncio
async def test_exceeding_budget_publishes_event_once_per_transition() -> None:
    from jarvis.core.events.events import HealthUpdatedEvent, ResourceBudgetExceededEvent

    manager, bus = _manager()
    manager.register_budget("cpu", "cpu_percent", 90.0)
    manager.start()

    published: list[ResourceBudgetExceededEvent] = []
    bus.subscribe(ResourceBudgetExceededEvent, published.append)

    await bus.publish(HealthUpdatedEvent(snapshot={"cpu_percent": 95.0}))
    assert manager.is_exceeded("cpu") is True
    assert len(published) == 1
    assert published[0].resource == "cpu"
    assert published[0].used == 95.0
    assert published[0].budget == 90.0

    # Staying over budget on a later tick must not re-publish.
    await bus.publish(HealthUpdatedEvent(snapshot={"cpu_percent": 96.0}))
    assert len(published) == 1

    # Dropping back under budget clears the exceeded flag.
    await bus.publish(HealthUpdatedEvent(snapshot={"cpu_percent": 10.0}))
    assert manager.is_exceeded("cpu") is False

    # Crossing again re-publishes -- a fresh transition.
    await bus.publish(HealthUpdatedEvent(snapshot={"cpu_percent": 95.0}))
    assert len(published) == 2
    manager.stop()


@pytest.mark.asyncio
async def test_missing_snapshot_key_is_ignored_not_fatal() -> None:
    from jarvis.core.events.events import HealthUpdatedEvent

    manager, bus = _manager()
    manager.register_budget("gpu", "gpu_percent", 90.0)  # no collector publishes this yet
    manager.start()

    await bus.publish(HealthUpdatedEvent(snapshot={"cpu_percent": 10.0}))  # no "gpu_percent" key

    assert manager.is_exceeded("gpu") is False
    manager.stop()


@pytest.mark.asyncio
async def test_stopped_manager_does_not_react() -> None:
    from jarvis.core.events.events import HealthUpdatedEvent, ResourceBudgetExceededEvent

    manager, bus = _manager()
    manager.register_budget("cpu", "cpu_percent", 90.0)
    manager.start()
    manager.stop()

    published: list[ResourceBudgetExceededEvent] = []
    bus.subscribe(ResourceBudgetExceededEvent, published.append)

    await bus.publish(HealthUpdatedEvent(snapshot={"cpu_percent": 99.0}))

    assert published == []
