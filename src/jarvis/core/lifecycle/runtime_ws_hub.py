"""``RuntimeWebSocketHub`` -- the relay ``docs/ARCHITECTURE.md`` section
6 describes: one ``EventBus`` subscription forwarding every mapped
event to every connected WebSocket, not a second, parallel event
system (Milestone 9 Task Group B).

Lives in ``core/lifecycle`` alongside its sibling managers
(``ServiceManager``, ``SessionManager``, ``ConfigurationManager``,
``HealthMonitor``) rather than in ``infrastructure/api/routes`` --
this project's layered architecture (§2) treats the WebSocket
*handler* as a thin transport shim over Core Runtime logic, the same
relationship FastAPI routers already have with services. See
``infrastructure/api/routes/runtime_ws.py`` for the actual
``@router.websocket`` handler, which owns only the accept/receive loop
and delegates everything else here.

Relays the eleven events Task Group B's five subsystems publish:
``runtime.started/ready/stopping/shutdown``,
``service.started/stopped/failed``, ``configuration.updated``,
``session.created/closed``, ``health.updated``, plus five more Task
Group C's Reliability module adds: ``runtime.crash_recovered``,
``task.started/completed/failed``, ``resource.budget_exceeded`` -- the
category table §6 documents (``voice``/``ai``/``automation``/
``memory``/``progress``/``notification``/``runtime.
module_state_changed``) predates all of these managers existing;
:data:`EVENT_TYPE_NAMES` below is where a future milestone adds its own
categories to the relay, the same way these two task groups did. Milestone
10 (AI Orchestrator) adds one more: ``agent.step``, real-time Agent Trace
visibility over this same relay rather than a second, parallel channel --
the backend half of M10 AC2's "real streaming over M8's WebSocket layer"
requirement (the token-level half is ``/api/v1/agent/stream``'s SSE
response, since per-token events over this hub would mean one WS frame per
LLM token -- see ``docs/MASTER_ROADMAP.md``'s M10 changelog addendum).
Milestone 10A (Universal Search & Knowledge Platform) finally realizes
the ``memory`` category §6's table has documented since before any of
these managers existed (``memory.updated``, ``memory.recalled``), plus a
new ``knowledge`` category (``knowledge.entity_updated``,
``knowledge.correction_applied``). Milestone 10B (Intelligence Layer)
adds ``goal`` (``goal.updated`` -- one relay name, an ``action`` payload
field distinguishes created/progress_updated/completed/deleted, the
same shape ``memory.updated`` already established) and ``briefing``
(``briefing.generated``). Milestone 10.5 Task Group A (MCP &
Integration Platform) adds ``mcp``
(``mcp.connection_changed`` -- again one relay name with a ``state``
payload field, ``mcp.capabilities_changed``, ``mcp.permission_denied``).
"""

from __future__ import annotations

import dataclasses
import time
from collections import deque
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol

from jarvis.core.events.events import (
    AgentStepEvent,
    AppReadyEvent,
    ConfigurationUpdatedEvent,
    CrashRecoveredEvent,
    DailyBriefingGeneratedEvent,
    Event,
    GoalUpdatedEvent,
    HealthUpdatedEvent,
    KnowledgeCorrectionAppliedEvent,
    KnowledgeEntityUpdatedEvent,
    MCPAuthStateChangedEvent,
    MCPCapabilitiesChangedEvent,
    MCPConnectionChangedEvent,
    MCPHandshakeCompletedEvent,
    MCPHeartbeatEvent,
    MCPNegotiationCompletedEvent,
    MCPPermissionDeniedEvent,
    MCPProviderStateChangedEvent,
    MCPTransportFailedEvent,
    MemoryRecalledEvent,
    MemoryUpdatedEvent,
    PluginDisabledEvent,
    PluginDiscoveredEvent,
    PluginEnabledEvent,
    PluginInstalledEvent,
    PluginLoadedEvent,
    PluginLoadFailedEvent,
    PluginPermissionDeniedEvent,
    PluginPermissionGrantedEvent,
    PluginUninstalledEvent,
    PluginUnloadedEvent,
    PluginUpdatedEvent,
    ResourceBudgetExceededEvent,
    RuntimeShutdownCompleteEvent,
    RuntimeStartedEvent,
    ServiceFailedEvent,
    ServiceStartedEvent,
    ServiceStoppedEvent,
    SessionClosedEvent,
    SessionCreatedEvent,
    ShutdownRequestedEvent,
    TaskCompletedEvent,
    TaskFailedEvent,
    TaskStartedEvent,
)

if TYPE_CHECKING:
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.lifecycle.session_manager import SessionManager

REPLAY_BUFFER_SECONDS = 60.0

# <category>.<event> per ARCHITECTURE.md §6's event-naming rule.
EVENT_TYPE_NAMES: dict[type[Event], str] = {
    RuntimeStartedEvent: "runtime.started",
    AppReadyEvent: "runtime.ready",
    ShutdownRequestedEvent: "runtime.stopping",
    RuntimeShutdownCompleteEvent: "runtime.shutdown",
    CrashRecoveredEvent: "runtime.crash_recovered",
    ServiceStartedEvent: "service.started",
    ServiceStoppedEvent: "service.stopped",
    ServiceFailedEvent: "service.failed",
    ConfigurationUpdatedEvent: "configuration.updated",
    SessionCreatedEvent: "session.created",
    SessionClosedEvent: "session.closed",
    HealthUpdatedEvent: "health.updated",
    TaskStartedEvent: "task.started",
    TaskCompletedEvent: "task.completed",
    TaskFailedEvent: "task.failed",
    ResourceBudgetExceededEvent: "resource.budget_exceeded",
    PluginDiscoveredEvent: "plugin.discovered",
    PluginLoadedEvent: "plugin.loaded",
    PluginLoadFailedEvent: "plugin.load_failed",
    PluginUnloadedEvent: "plugin.unloaded",
    PluginEnabledEvent: "plugin.enabled",
    PluginDisabledEvent: "plugin.disabled",
    PluginInstalledEvent: "plugin.installed",
    PluginUninstalledEvent: "plugin.uninstalled",
    PluginUpdatedEvent: "plugin.updated",
    PluginPermissionGrantedEvent: "plugin.permission_granted",
    PluginPermissionDeniedEvent: "plugin.permission_denied",
    AgentStepEvent: "agent.step",
    GoalUpdatedEvent: "goal.updated",
    DailyBriefingGeneratedEvent: "briefing.generated",
    # Milestone 10.5 Task Group A
    MCPConnectionChangedEvent: "mcp.connection_changed",
    MCPCapabilitiesChangedEvent: "mcp.capabilities_changed",
    MCPPermissionDeniedEvent: "mcp.permission_denied",
    # Milestone 10.5 Task Group B
    MCPHandshakeCompletedEvent: "mcp.handshake_completed",
    MCPNegotiationCompletedEvent: "mcp.negotiation_completed",
    MCPTransportFailedEvent: "mcp.transport_failed",
    MCPHeartbeatEvent: "mcp.heartbeat",
    # Milestone 10.5 Task Group C
    MCPProviderStateChangedEvent: "mcp.provider_changed",
    # Milestone 10.5 Task Group D
    MCPAuthStateChangedEvent: "mcp.auth_changed",
    MemoryUpdatedEvent: "memory.updated",
    MemoryRecalledEvent: "memory.recalled",
    KnowledgeEntityUpdatedEvent: "knowledge.entity_updated",
    KnowledgeCorrectionAppliedEvent: "knowledge.correction_applied",
}

_BASE_FIELD_NAMES = {f.name for f in dataclasses.fields(Event)}


class _SendsJson(Protocol):
    """What the hub needs from a connection -- satisfied by
    ``starlette.websockets.WebSocket`` without importing FastAPI/
    Starlette into ``core`` (see ``docs/ARCHITECTURE.md``'s layering
    rule: `core` never imports "up" from `infrastructure`/`ui`)."""

    async def send_json(self, data: Any) -> None: ...


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    return value


def _event_payload(event: Event) -> dict[str, Any]:
    return {
        f.name: _json_safe(getattr(event, f.name))
        for f in dataclasses.fields(event)
        if f.name not in _BASE_FIELD_NAMES
    }


def envelope(type_name: str, event: Event) -> dict[str, Any]:
    return {
        "type": type_name,
        "id": event.id,
        "occurred_at": event.occurred_at.isoformat(),
        "payload": _event_payload(event),
    }


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class _RelayBuffer:
    """Bounded (60s) ring buffer of already-relayed envelopes -- backs
    the ``resume``/``last_id`` reconnect flow (§6). Global, not
    per-connection: every connected client sees the same relayed
    events, so one shared buffer correctly serves whichever client
    reconnects."""

    def __init__(self, window_seconds: float = REPLAY_BUFFER_SECONDS) -> None:
        self._window = window_seconds
        self._entries: deque[tuple[float, dict[str, Any]]] = deque()

    def append(self, env: dict[str, Any]) -> None:
        self._prune()
        self._entries.append((time.monotonic(), env))

    def replay_since(self, last_id: str) -> list[dict[str, Any]] | None:
        """``None`` means *outside the window* -- the caller must fall
        back to a REST refetch (§6), never silently return an empty
        list (which would mean "nothing changed", a different thing)."""
        self._prune()
        ids = [env["id"] for _, env in self._entries]
        if last_id not in ids:
            return None
        idx = ids.index(last_id)
        return [env for _, env in list(self._entries)[idx + 1 :]]

    def _prune(self) -> None:
        cutoff = time.monotonic() - self._window
        while self._entries and self._entries[0][0] < cutoff:
            self._entries.popleft()


class RuntimeWebSocketHub:
    """Constructed once as a DI Singleton (``core/di/container.py``),
    not per-connection. ``start()``/``stop()`` are called by Runtime
    Integration (Task Group B's sixth subsystem), mirroring how every
    other manager in this task group is wired -- this class does not
    self-start."""

    def __init__(self, event_bus: EventBus, session_manager: SessionManager) -> None:
        self._event_bus = event_bus
        self._session_manager = session_manager
        self._connections: set[_SendsJson] = set()
        self._buffer = _RelayBuffer()
        self._unsubscribe: Any = None

    def start(self) -> None:
        if self._unsubscribe is not None:
            return
        self._unsubscribe = self._event_bus.subscribe(Event, self._on_event)

    def stop(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

    async def _on_event(self, event: Event) -> None:
        type_name = EVENT_TYPE_NAMES.get(type(event))
        if type_name is None:
            return
        env = envelope(type_name, event)
        self._buffer.append(env)
        await self._broadcast(env)

    async def _broadcast(self, env: dict[str, Any]) -> None:
        dead: list[_SendsJson] = []
        for connection in list(self._connections):
            try:
                await connection.send_json(env)
            except Exception:
                dead.append(connection)
        for connection in dead:
            self._connections.discard(connection)

    def connect(self, connection: _SendsJson) -> None:
        self._connections.add(connection)

    def disconnect(self, connection: _SendsJson) -> None:
        self._connections.discard(connection)

    async def replay(self, connection: _SendsJson, last_id: str) -> bool:
        """Returns ``True`` once replay actually served the request;
        ``False`` means the caller must fall back to a REST refetch."""
        envelopes = self._buffer.replay_since(last_id)
        if envelopes is None:
            return False
        for env in envelopes:
            await connection.send_json(env)
        return True

    async def authenticate(self, token: str | None) -> bool:
        if not token:
            return False
        return self._session_manager.get(token) is not None
