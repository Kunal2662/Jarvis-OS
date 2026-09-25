"""Unit tests for ``jarvis.core.devtools.device_event_log`` (Milestone
12 Developer Tools, Event Viewer Slice). Mirrors ``test_debug_console.py``'s
own structure -- the sibling capture component this one is structurally
parallel to."""

from __future__ import annotations

import pytest

from jarvis.core.devtools.device_event_log import DeviceEventLog
from jarvis.core.events.event_bus import EventBus
from jarvis.core.events.events import DeviceCommandExecutedEvent


def test_not_running_until_started():
    log = DeviceEventLog(EventBus())
    assert log.is_running is False


@pytest.mark.asyncio
async def test_start_is_idempotent():
    bus = EventBus()
    log = DeviceEventLog(bus)
    log.start()
    log.start()  # second call must not attach a duplicate subscription
    await bus.publish(DeviceCommandExecutedEvent(device_id="d1", command="lock", success=True))

    assert len(log) == 1


@pytest.mark.asyncio
async def test_capture_and_query():
    bus = EventBus()
    log = DeviceEventLog(bus)
    log.start()

    await bus.publish(
        DeviceCommandExecutedEvent(device_id="d1", command="lock", success=True, detail="")
    )

    entries = log.entries()
    assert len(entries) == 1
    assert entries[0].device_id == "d1"
    assert entries[0].command == "lock"
    assert entries[0].success is True


@pytest.mark.asyncio
async def test_filter_by_device_id():
    bus = EventBus()
    log = DeviceEventLog(bus)
    log.start()

    await bus.publish(DeviceCommandExecutedEvent(device_id="d1", command="lock", success=True))
    await bus.publish(DeviceCommandExecutedEvent(device_id="d2", command="unlock", success=True))

    entries = log.entries(device_id="d1")
    assert len(entries) == 1
    assert entries[0].device_id == "d1"


@pytest.mark.asyncio
async def test_stop_detaches_subscription():
    bus = EventBus()
    log = DeviceEventLog(bus)
    log.start()
    log.stop()

    assert log.is_running is False
    await bus.publish(DeviceCommandExecutedEvent(device_id="d1", command="lock", success=True))
    assert len(log) == 0


@pytest.mark.asyncio
async def test_max_entries_bounds_buffer():
    bus = EventBus()
    log = DeviceEventLog(bus, max_entries=3)
    log.start()

    for i in range(10):
        await bus.publish(
            DeviceCommandExecutedEvent(device_id=f"d{i}", command="lock", success=True)
        )

    assert len(log) == 3
    ids = {e.device_id for e in log.entries()}
    assert ids == {"d7", "d8", "d9"}


@pytest.mark.asyncio
async def test_entries_are_most_recent_first():
    bus = EventBus()
    log = DeviceEventLog(bus)
    log.start()

    await bus.publish(DeviceCommandExecutedEvent(device_id="d1", command="lock", success=True))
    await bus.publish(DeviceCommandExecutedEvent(device_id="d2", command="unlock", success=True))

    entries = log.entries()
    assert [e.device_id for e in entries] == ["d2", "d1"]


@pytest.mark.asyncio
async def test_limit_is_respected():
    bus = EventBus()
    log = DeviceEventLog(bus)
    log.start()

    for i in range(5):
        await bus.publish(
            DeviceCommandExecutedEvent(device_id=f"d{i}", command="lock", success=True)
        )

    entries = log.entries(limit=2)
    assert len(entries) == 2
    assert entries[0].device_id == "d4"


@pytest.mark.asyncio
async def test_clear_empties_buffer():
    bus = EventBus()
    log = DeviceEventLog(bus)
    log.start()
    await bus.publish(DeviceCommandExecutedEvent(device_id="d1", command="lock", success=True))

    log.clear()

    assert len(log) == 0


def test_entries_never_raises_on_empty_buffer():
    log = DeviceEventLog(EventBus())
    assert log.entries() == ()
    assert log.entries(device_id="no-such-device") == ()
