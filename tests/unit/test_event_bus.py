"""Tests for ``jarvis.core.events.event_bus.EventBus`` (Milestone 5.5,
section 4). No dedicated test file existed before this one -- the 71%
coverage it had was purely incidental from other tests exercising it
in passing.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from jarvis.core.events.event_bus import EventBus
from jarvis.core.events.events import Event


@dataclass(frozen=True, slots=True)
class _PingEvent(Event):
    who: str = "world"


@dataclass(frozen=True, slots=True)
class _SpecificPingEvent(_PingEvent):
    """Subclass -- exercises the MRO-walking dispatch in publish()."""


@pytest.mark.asyncio
async def test_publish_delivers_to_subscribed_handler() -> None:
    bus = EventBus()
    received = []

    async def handler(evt: _PingEvent) -> None:
        received.append(evt.who)

    bus.subscribe(_PingEvent, handler)
    await bus.publish(_PingEvent(who="jarvis"))

    assert received == ["jarvis"]


@pytest.mark.asyncio
async def test_publish_delivers_to_multiple_handlers_in_registration_order() -> None:
    bus = EventBus()
    order = []

    async def first(evt):
        order.append("first")

    async def second(evt):
        order.append("second")

    bus.subscribe(_PingEvent, first)
    bus.subscribe(_PingEvent, second)
    await bus.publish(_PingEvent())

    assert order == ["first", "second"]


@pytest.mark.asyncio
async def test_publish_supports_sync_handlers() -> None:
    bus = EventBus()
    received = []

    def sync_handler(evt: _PingEvent) -> None:  # not async
        received.append(evt.who)

    bus.subscribe(_PingEvent, sync_handler)
    await bus.publish(_PingEvent(who="sync"))

    assert received == ["sync"]


@pytest.mark.asyncio
async def test_subscribe_to_base_type_receives_subclass_events() -> None:
    """The MRO-walking dispatch: a handler subscribed to the base event
    type must also receive instances of a subclass."""
    bus = EventBus()
    received = []

    async def handler(evt: _PingEvent) -> None:
        received.append(type(evt).__name__)

    bus.subscribe(_PingEvent, handler)
    await bus.publish(_SpecificPingEvent())

    assert received == ["_SpecificPingEvent"]


@pytest.mark.asyncio
async def test_unsubscribe_stops_delivery() -> None:
    bus = EventBus()
    received = []

    async def handler(evt):
        received.append(1)

    unsubscribe = bus.subscribe(_PingEvent, handler)
    await bus.publish(_PingEvent())
    unsubscribe()
    await bus.publish(_PingEvent())

    assert received == [1]  # only the first publish was delivered


def test_unsubscribe_twice_does_not_raise() -> None:
    """Real edge case: a caller unsubscribing twice (e.g. once in a
    cleanup handler and once in an error path) must not crash."""
    bus = EventBus()

    async def handler(evt):
        pass

    unsubscribe = bus.subscribe(_PingEvent, handler)
    unsubscribe()
    unsubscribe()  # must not raise


@pytest.mark.asyncio
async def test_failing_handler_does_not_crash_publish_or_block_other_handlers() -> None:
    """Failure injection (explicitly requested): a subscriber that
    raises must not crash publish(), and must not prevent other
    subscribers from still receiving the event."""
    bus = EventBus()
    received = []

    async def failing_handler(evt):
        raise RuntimeError("simulated handler failure")

    async def healthy_handler(evt):
        received.append("healthy ran")

    bus.subscribe(_PingEvent, failing_handler)
    bus.subscribe(_PingEvent, healthy_handler)

    await bus.publish(_PingEvent())  # must not raise

    assert received == ["healthy ran"]


@pytest.mark.asyncio
async def test_failing_sync_handler_does_not_crash_publish() -> None:
    bus = EventBus()
    received = []

    def failing_sync_handler(evt):
        raise ValueError("simulated sync failure")

    async def healthy_handler(evt):
        received.append("healthy ran")

    bus.subscribe(_PingEvent, failing_sync_handler)
    bus.subscribe(_PingEvent, healthy_handler)

    await bus.publish(_PingEvent())

    assert received == ["healthy ran"]


@pytest.mark.asyncio
async def test_publish_with_no_subscribers_does_not_raise() -> None:
    bus = EventBus()
    await bus.publish(_PingEvent())  # no subscribers at all -- must be a no-op


@pytest.mark.asyncio
async def test_publish_nowait_with_running_loop_schedules_delivery() -> None:
    """publish_nowait()'s fast path: a loop is already running (the
    normal case -- called from within async app code)."""
    bus = EventBus()
    received = []

    async def handler(evt):
        received.append(evt.who)

    bus.subscribe(_PingEvent, handler)
    bus.publish_nowait(_PingEvent(who="nowait"))

    # Fire-and-forget -- give the scheduled task a tick to actually run.
    await asyncio.sleep(0.05)
    assert received == ["nowait"]


def test_publish_nowait_with_no_running_loop_falls_back_to_asyncio_run() -> None:
    """publish_nowait()'s fallback path: called from fully synchronous
    code with no event loop running at all (e.g. a signal handler, a
    plain script). Must still deliver the event, not silently drop it."""
    bus = EventBus()
    received = []

    async def handler(evt):
        received.append(evt.who)

    bus.subscribe(_PingEvent, handler)
    bus.publish_nowait(_PingEvent(who="sync-context"))  # no running loop here

    assert received == ["sync-context"]
