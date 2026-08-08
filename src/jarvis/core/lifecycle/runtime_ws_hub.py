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

The Aug 2026 backlog pass finally closes the rest of §6's original
table: ``voice``, ``automation``, ``progress`` and ``notification``.
Every one of those events was already being published by real code --
``VoiceService``, the automation executor, ``UpdateService``, the
plugin Extension API -- and only the relay entry was missing, so no
subscriber could see them. See :data:`UNPUBLISHED_EVENT_TYPES` below
for the four event classes still absent from the relay on purpose, and
the note beneath it for why ``DebugLogCapturedEvent`` stays out.
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
    AttachmentUpdatedEvent,
    AutomationStepEvent,
    CalendarEventUpdatedEvent,
    CalendarUpdatedEvent,
    ConfigurationUpdatedEvent,
    ConnectivityStatusChangedEvent,
    CrashRecoveredEvent,
    DailyBriefingGeneratedEvent,
    DeviceUpdatedEvent,
    Event,
    FileUpdatedEvent,
    FolderUpdatedEvent,
    GoalUpdatedEvent,
    HealthUpdatedEvent,
    HomeUpdatedEvent,
    IntegrationCallCompletedEvent,
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
    NoteUpdatedEvent,
    PluginCustomEvent,
    PluginDisabledEvent,
    PluginDiscoveredEvent,
    PluginEnabledEvent,
    PluginInstalledEvent,
    PluginLoadedEvent,
    PluginLoadFailedEvent,
    PluginNotificationEvent,
    PluginPermissionDeniedEvent,
    PluginPermissionGrantedEvent,
    PluginUninstalledEvent,
    PluginUnloadedEvent,
    PluginUpdatedEvent,
    ProjectUpdatedEvent,
    ReminderUpdatedEvent,
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
    TaskUpdatedEvent,
    UpdatePhaseEvent,
    VoiceStateChangedEvent,
    WorkspaceAssistCompletedEvent,
    WorkspaceKnowledgeLinkedEvent,
    WorkspaceUpdatedEvent,
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
    # Aug 2026 backlog pass -- the four categories §6's table has
    # documented since before any of these managers existed, and which
    # §15 tracked as open Task Group B work. Every one of these events
    # was already being published by real code; only the relay entry was
    # missing, so a subscriber had no way to see them.
    VoiceStateChangedEvent: "voice.state_changed",
    AutomationStepEvent: "automation.step",
    UpdatePhaseEvent: "progress.update_phase",
    PluginNotificationEvent: "notification.plugin",
    PluginCustomEvent: "plugin.custom",
    # Milestone 11 Task Group A -- Workspace Foundation. One relay name
    # per entity, each carrying an `action` field for its transitions,
    # the shape `memory.updated`/`goal.updated`/`mcp.provider_changed`
    # already established.
    WorkspaceUpdatedEvent: "workspace.updated",
    ProjectUpdatedEvent: "project.updated",
    NoteUpdatedEvent: "note.updated",
    # Milestone 11 Task Group B -- Productivity Core. Same one-name-
    # per-entity-with-an-action-field shape. `task.updated` is
    # distinct from Task Group C's `task.started`/`completed`/
    # `failed`, which are the Background Task Manager's runtime
    # tasks -- a different noun that unfortunately shares a word.
    TaskUpdatedEvent: "task.updated",
    CalendarUpdatedEvent: "calendar.updated",
    CalendarEventUpdatedEvent: "calendar.event_updated",
    ReminderUpdatedEvent: "reminder.updated",
    # Milestone 11 Task Group C -- File Platform. Same shape again. The
    # `file.*` category is new to the relay; `folder` and `attachment`
    # are its siblings rather than sub-names of it, because a subscriber
    # watching a tree view cares about folders and not file contents.
    FileUpdatedEvent: "file.updated",
    FolderUpdatedEvent: "folder.updated",
    AttachmentUpdatedEvent: "attachment.updated",
    # Milestone 11 Task Group D -- AI Workspace. Both stay under the
    # existing `workspace` category rather than opening an `ai` one: a
    # subscriber watching a workspace wants to know when its knowledge
    # links change and when the assistant has run, and a separate
    # category would make that two subscriptions to the same board.
    WorkspaceKnowledgeLinkedEvent: "workspace.knowledge_linked",
    WorkspaceAssistCompletedEvent: "workspace.assisted",
    # Milestone 11 Task Group E -- Integration Platform. One name, for
    # the audit trail of outbound vendor calls. Integration *lifecycle*
    # is deliberately absent from this block: an integration is an MCP
    # provider, so it already relays through `mcp.provider_changed` and
    # `mcp.auth_changed` rather than through a second set of names for
    # the same transitions.
    IntegrationCallCompletedEvent: "integration.call_completed",
    # Milestone 12 Task Group A -- Smart Home Core. Same one-name-
    # per-entity-with-an-action-field shape M11's Workspace/Project/
    # Note relay entries already established. Zone/Room/DeviceGroup
    # publish no event of their own in this task group and so have no
    # relay entry -- a Home or a Device is what a dashboard actually
    # watches; a room rename has no real-time subscriber yet.
    HomeUpdatedEvent: "home.updated",
    DeviceUpdatedEvent: "device.updated",
    # Milestone 12 Task Group B -- Connectivity Layer.
    ConnectivityStatusChangedEvent: "connectivity.status_changed",
}

#: Declared but never published, so deliberately absent from the relay
#: above -- adding them would ship dead entries that no subscriber could
#: ever receive. Each belongs to a milestone that has not built its
#: publisher yet: ``WorkflowStepEvent`` and ``ScheduledJobFiredEvent``
#: to M7 (Phases 4-6), ``VisionProviderStatusEvent`` to M6's remainder,
#: ``PluginCrashedEvent`` to the supervisor M9 Task Group C deferred.
#: Listed by name so the omission reads as a decision rather than an
#: oversight the next audit re-discovers.
#:
#: ``IntegrationConnectionTestEvent``, ``IntegrationSwitchEvent``,
#: ``IntegrationFailoverEvent`` and ``IntegrationDiscoveryEvent`` are a
#: different case from the other four -- all four *are* published (by
#: ``IntegrationService`` on every M11 Connection Test / Runtime Switch
#: / Failover attempt / Discovery sweep, Task Groups B, E and F) -- but
#: relaying them is a separate, deliberately deferred decision: wiring
#: a new relayed event also means regenerating the frontend WS contract
#: and its four pinned tests (``export_ws_contract.py``,
#: ``event-contract.generated.json``, ``types.ts``'s
#: ``RELAYED_EVENTS``, the contract test), which is a frontend-touching
#: change outside those task groups' backend-only scope. Internal
#: subscribers (audit, a future observability consumer) can still
#: receive them from the event bus today.
UNPUBLISHED_EVENT_TYPES: tuple[str, ...] = (
    "WorkflowStepEvent",
    "ScheduledJobFiredEvent",
    "VisionProviderStatusEvent",
    "PluginCrashedEvent",
    "IntegrationConnectionTestEvent",
    "IntegrationSwitchEvent",
    "IntegrationFailoverEvent",
    "IntegrationDiscoveryEvent",
)

#: ``DebugLogCapturedEvent`` is published (by ``DebugConsole``) and is
#: still not relayed, which is a separate decision from the above: it
#: fires once per *log line*. This hub has no per-category subscription
#: -- every connection receives every relayed event, and each one also
#: enters the bounded replay buffer -- so relaying it would drown every
#: other event in the buffer and push a frame per log line to every
#: client. The console's own bounded buffer, queried over
#: ``/api/v1/devtools/logs``, is the surface for that data. Revisit if
#: this hub ever grows per-category subscriptions.


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
