"""Unit tests for ``jarvis.core.lifecycle.runtime_ws_hub`` (Milestone 9
Task Group B) -- the relay logic itself, independent of the FastAPI
transport (see ``tests/unit/test_runtime_ws_route.py`` for the actual
``@router.websocket`` handler)."""

from __future__ import annotations

import pytest

from jarvis.core.lifecycle.runtime_ws_hub import (
    EVENT_TYPE_NAMES,
    RuntimeWebSocketHub,
    _RelayBuffer,
    envelope,
)


class _FakeConnection:
    def __init__(self, *, fail: bool = False) -> None:
        self.received: list[dict] = []
        self._fail = fail

    async def send_json(self, data: dict) -> None:
        if self._fail:
            raise RuntimeError("connection closed")
        self.received.append(data)


def _hub():
    from jarvis.core.events.event_bus import EventBus

    class _FakeSessionManager:
        def __init__(self) -> None:
            self._valid: set[str] = set()

        def issue(self, token: str) -> None:
            self._valid.add(token)

        def get(self, token: str):
            return object() if token in self._valid else None

    bus = EventBus()
    session_manager = _FakeSessionManager()
    return RuntimeWebSocketHub(bus, session_manager), bus, session_manager


# --- Event -> envelope mapping ------------------------------------------------


def test_every_documented_event_type_is_mapped() -> None:
    names = set(EVENT_TYPE_NAMES.values())
    assert names == {
        "runtime.started",
        "runtime.ready",
        "runtime.stopping",
        "runtime.shutdown",
        "service.started",
        "service.stopped",
        "service.failed",
        "configuration.updated",
        "session.created",
        "session.closed",
        "health.updated",
    }


def test_envelope_shape() -> None:
    from jarvis.core.events.events import ServiceStartedEvent

    event = ServiceStartedEvent(service="chat")
    env = envelope("service.started", event)

    assert env["type"] == "service.started"
    assert env["id"] == event.id
    assert env["occurred_at"] == event.occurred_at.isoformat()
    assert env["payload"] == {"service": "chat"}  # base Event fields excluded


# --- Relay ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_started_hub_relays_mapped_events_to_connections() -> None:
    from jarvis.core.events.events import ServiceStartedEvent

    hub, bus, _ = _hub()
    hub.start()
    connection = _FakeConnection()
    hub.connect(connection)

    await bus.publish(ServiceStartedEvent(service="chat"))

    assert len(connection.received) == 1
    assert connection.received[0]["type"] == "service.started"


@pytest.mark.asyncio
async def test_unmapped_events_are_not_relayed() -> None:
    from jarvis.core.events.events import VoiceStateChangedEvent

    hub, bus, _ = _hub()
    hub.start()
    connection = _FakeConnection()
    hub.connect(connection)

    await bus.publish(VoiceStateChangedEvent(state="listening"))

    assert connection.received == []


@pytest.mark.asyncio
async def test_stopped_hub_does_not_relay() -> None:
    from jarvis.core.events.events import ServiceStartedEvent

    hub, bus, _ = _hub()
    hub.start()
    hub.stop()
    connection = _FakeConnection()
    hub.connect(connection)

    await bus.publish(ServiceStartedEvent(service="chat"))
    assert connection.received == []


@pytest.mark.asyncio
async def test_broadcast_failure_on_one_connection_does_not_block_others() -> None:
    from jarvis.core.events.events import ServiceStartedEvent

    hub, bus, _ = _hub()
    hub.start()
    dead = _FakeConnection(fail=True)
    alive = _FakeConnection()
    hub.connect(dead)
    hub.connect(alive)

    await bus.publish(ServiceStartedEvent(service="chat"))

    assert len(alive.received) == 1
    # A failed send silently discards the dead connection.
    await bus.publish(ServiceStartedEvent(service="chat"))
    assert len(alive.received) == 2


def test_disconnect_removes_connection() -> None:
    hub, _, _ = _hub()
    connection = _FakeConnection()
    hub.connect(connection)
    hub.disconnect(connection)
    hub.disconnect(connection)  # idempotent, no error


# --- Authentication --------------------------------------------------------


@pytest.mark.asyncio
async def test_authenticate_rejects_missing_and_unknown_token() -> None:
    hub, _, _ = _hub()
    assert await hub.authenticate(None) is False
    assert await hub.authenticate("") is False
    assert await hub.authenticate("bogus") is False


@pytest.mark.asyncio
async def test_authenticate_accepts_valid_session_token() -> None:
    hub, _, session_manager = _hub()
    session_manager.issue("real-token")
    assert await hub.authenticate("real-token") is True


# --- Replay buffer -----------------------------------------------------------


def test_replay_buffer_returns_events_after_last_id() -> None:
    buf = _RelayBuffer(window_seconds=60)
    buf.append({"id": "1"})
    buf.append({"id": "2"})
    buf.append({"id": "3"})

    result = buf.replay_since("1")
    assert [e["id"] for e in result] == ["2", "3"]


def test_replay_buffer_unknown_id_returns_none() -> None:
    buf = _RelayBuffer(window_seconds=60)
    buf.append({"id": "1"})
    assert buf.replay_since("never-seen") is None


def test_replay_buffer_prunes_outside_window() -> None:
    import time

    buf = _RelayBuffer(window_seconds=0.05)
    buf.append({"id": "1"})
    time.sleep(0.1)
    buf.append({"id": "2"})

    assert buf.replay_since("1") is None  # "1" fell outside the window


@pytest.mark.asyncio
async def test_hub_replay_serves_missed_events() -> None:
    """A client processed event A (its ``last_id``), then dropped off
    before event B was relayed -- reconnecting and resuming from A must
    hand back exactly B, the one it missed."""
    from jarvis.core.events.events import ServiceStartedEvent, ServiceStoppedEvent

    hub, bus, _ = _hub()
    hub.start()

    peek = _FakeConnection()
    hub.connect(peek)
    await bus.publish(ServiceStartedEvent(service="chat"))  # event A -- the client's last_id
    a_id = peek.received[0]["id"]
    hub.disconnect(peek)

    await bus.publish(ServiceStoppedEvent(service="chat"))  # event B, missed by the client

    reconnecting = _FakeConnection()
    served = await hub.replay(reconnecting, a_id)

    assert served is True
    assert len(reconnecting.received) == 1
    assert reconnecting.received[0]["type"] == "service.stopped"


@pytest.mark.asyncio
async def test_hub_replay_returns_false_outside_window() -> None:
    hub, _, _ = _hub()
    connection = _FakeConnection()
    served = await hub.replay(connection, "never-seen")
    assert served is False
