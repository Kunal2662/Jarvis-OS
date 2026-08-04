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
        # Task Group B
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
        # Task Group C
        "runtime.crash_recovered",
        "task.started",
        "task.completed",
        "task.failed",
        "resource.budget_exceeded",
        # Task Group D
        "plugin.discovered",
        "plugin.loaded",
        "plugin.load_failed",
        "plugin.unloaded",
        "plugin.enabled",
        "plugin.disabled",
        "plugin.installed",
        "plugin.uninstalled",
        "plugin.updated",
        "plugin.permission_granted",
        "plugin.permission_denied",
        # Milestone 10
        "agent.step",
        # Milestone 10A
        "memory.updated",
        "memory.recalled",
        "knowledge.entity_updated",
        "knowledge.correction_applied",
        # Milestone 10B
        "goal.updated",
        "briefing.generated",
        # Milestone 10.5 Task Group A
        "mcp.connection_changed",
        "mcp.capabilities_changed",
        "mcp.permission_denied",
        # Milestone 10.5 Task Group B
        "mcp.handshake_completed",
        "mcp.negotiation_completed",
        "mcp.transport_failed",
        "mcp.heartbeat",
        # Milestone 10.5 Task Group C
        "mcp.provider_changed",
        # Milestone 10.5 Task Group D
        "mcp.auth_changed",
        # Aug 2026 backlog pass -- §6's original category table, finally
        # relayed. These events were already published; only the relay
        # entry was missing.
        "voice.state_changed",
        "automation.step",
        "progress.update_phase",
        "notification.plugin",
        "plugin.custom",
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
    """``VoiceStateChangedEvent`` used to be the example here; the Aug
    2026 backlog pass mapped it, so this now uses one that is still
    deliberately unmapped -- ``DebugLogCapturedEvent`` fires once per
    log line, and this hub broadcasts to every connection with no
    per-category subscription."""
    from jarvis.core.events.events import DebugLogCapturedEvent

    hub, bus, _ = _hub()
    hub.start()
    connection = _FakeConnection()
    hub.connect(connection)

    await bus.publish(DebugLogCapturedEvent(level="INFO", logger="test"))

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


# --- Relay coverage (Aug 2026 backlog pass) -------------------------------------


def test_previously_unrelayed_published_events_now_reach_subscribers() -> None:
    """§15 tracked "extend §6's category table to voice/automation/
    progress/notification" as open Task Group B work. Every one of these
    events was already published by real code -- only the relay entry
    was missing, so no subscriber could ever see them."""
    from jarvis.core.events.events import (
        AutomationStepEvent,
        PluginCustomEvent,
        PluginNotificationEvent,
        UpdatePhaseEvent,
        VoiceStateChangedEvent,
    )

    assert EVENT_TYPE_NAMES[VoiceStateChangedEvent] == "voice.state_changed"
    assert EVENT_TYPE_NAMES[AutomationStepEvent] == "automation.step"
    assert EVENT_TYPE_NAMES[UpdatePhaseEvent] == "progress.update_phase"
    assert EVENT_TYPE_NAMES[PluginNotificationEvent] == "notification.plugin"
    assert EVENT_TYPE_NAMES[PluginCustomEvent] == "plugin.custom"


@pytest.mark.asyncio
async def test_a_voice_state_change_is_broadcast_end_to_end() -> None:
    """Through the real bus and the real hub, not by reading the map."""
    from jarvis.core.events.events import VoiceStateChangedEvent

    hub, bus, _ = _hub()
    hub.start()
    connection = _FakeConnection()
    hub.connect(connection)

    await bus.publish(VoiceStateChangedEvent(state="listening", detail="wake word"))

    assert [e["type"] for e in connection.received] == ["voice.state_changed"]
    assert connection.received[0]["payload"]["state"] == "listening"
    hub.stop()


def test_every_relayed_name_is_unique() -> None:
    """Two event classes sharing a relay name would make a subscriber
    unable to tell them apart."""
    assert len(set(EVENT_TYPE_NAMES.values())) == len(EVENT_TYPE_NAMES)


def test_only_unpublished_events_are_absent_from_the_relay() -> None:
    """Guards the omission list: an event class that gains a publisher
    must also gain a relay entry, or this test names it."""
    import inspect

    from jarvis.core.events import events as events_module
    from jarvis.core.lifecycle.runtime_ws_hub import UNPUBLISHED_EVENT_TYPES

    all_events = {
        obj
        for obj in vars(events_module).values()
        if inspect.isclass(obj)
        and issubclass(obj, events_module.Event)
        and obj is not events_module.Event
    }
    absent = {cls.__name__ for cls in all_events - set(EVENT_TYPE_NAMES)}

    # DebugLogCapturedEvent is published but deliberately not relayed --
    # it fires once per log line, and this hub broadcasts to every
    # connection with no per-category subscription.
    assert absent == {*UNPUBLISHED_EVENT_TYPES, "DebugLogCapturedEvent"}
