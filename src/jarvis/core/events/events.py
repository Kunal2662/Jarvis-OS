"""Domain events published on the in-process :class:`EventBus`.

Concrete event types will be added by feature milestones. All events must
inherit from :class:`Event` so subscribers can filter by type.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class Event:
    """Base class for every event published on the bus."""

    id: str = field(default_factory=lambda: uuid4().hex)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


# --- Application Lifecycle (Milestone 9, Runtime Core) ----------------------
@dataclass(frozen=True, slots=True)
class RuntimeStartedEvent(Event):
    """Published by :meth:`~jarvis.core.lifecycle.runtime_manager.RuntimeManager.startup`
    at the very start of the startup sequence, before any registered
    startup hook runs (Task Group B) -- relayed over WebSocket as
    ``runtime.started``, the counterpart to :class:`AppReadyEvent`'s
    ``runtime.ready``."""


@dataclass(frozen=True, slots=True)
class AppReadyEvent(Event):
    """Published by :class:`~jarvis.app.ApplicationBootstrapper` once every
    registered ``RuntimeManager`` startup hook has run (``_run_gui``)."""


@dataclass(frozen=True, slots=True)
class ShutdownRequestedEvent(Event):
    """Published by :meth:`~jarvis.ui.main_window.MainWindow._graceful_quit`
    before ``RuntimeManager.shutdown()`` releases any real resource."""


@dataclass(frozen=True, slots=True)
class RuntimeShutdownCompleteEvent(Event):
    """Published by :meth:`~jarvis.core.lifecycle.runtime_manager.RuntimeManager.shutdown`
    once every registered shutdown hook has run (Task Group B) --
    relayed over WebSocket as ``runtime.shutdown``. The WebSocket
    connection itself is normally already closing by this point; this
    exists for any local subscriber (Developer Mode) still listening."""


# --- Service Manager (Milestone 9 Task Group B) ------------------------------
@dataclass(frozen=True, slots=True)
class ServiceStartedEvent(Event):
    """Published by :class:`~jarvis.core.lifecycle.service_manager.ServiceManager`
    once a registered service's ``start()`` returns without raising."""

    service: str = ""


@dataclass(frozen=True, slots=True)
class ServiceStoppedEvent(Event):
    """Published once a registered service's ``stop()`` returns."""

    service: str = ""


@dataclass(frozen=True, slots=True)
class ServiceFailedEvent(Event):
    """Published when a registered service's ``initialize()``/``start()``
    raises, or its polled ``health()`` reports unhealthy. The failure is
    isolated to that one service -- `ServiceManager` continues starting
    or polling every other registered service."""

    service: str = ""
    detail: str = ""


# --- Session Manager (Milestone 9 Task Group B) ------------------------------
@dataclass(frozen=True, slots=True)
class SessionCreatedEvent(Event):
    """Published by :class:`~jarvis.core.lifecycle.session_manager.SessionManager`
    when a new runtime session is created (a fresh WebSocket connection,
    or recovery of a persisted session after restart)."""

    session_id: str = ""
    recovered: bool = False


@dataclass(frozen=True, slots=True)
class SessionClosedEvent(Event):
    """Published when a runtime session is explicitly closed or expires."""

    session_id: str = ""


# --- Configuration Manager (Milestone 9 Task Group B) ------------------------
@dataclass(frozen=True, slots=True)
class ConfigurationUpdatedEvent(Event):
    """Published by :class:`~jarvis.core.lifecycle.configuration_manager.ConfigurationManager`
    after a live reload actually changes at least one safe-to-reload
    field. ``keys`` lists the dotted setting paths that changed --
    never the values themselves, since some (API keys) are secrets."""

    keys: tuple[str, ...] = ()


# --- Runtime Health Monitor (Milestone 9 Task Group B) -----------------------
@dataclass(frozen=True, slots=True)
class HealthUpdatedEvent(Event):
    """Published by :class:`~jarvis.core.lifecycle.health_monitor.HealthMonitor`
    on every poll tick. ``snapshot`` mirrors
    :meth:`HealthMonitor.snapshot`'s own return shape field-for-field --
    the WebSocket payload is that dict, not a reinvented shape."""

    snapshot: dict[str, Any] = field(default_factory=dict)


# --- Background Task Manager (Milestone 9 Task Group C) ----------------------
@dataclass(frozen=True, slots=True)
class TaskStartedEvent(Event):
    """Published by :class:`~jarvis.core.lifecycle.background_task_manager.
    BackgroundTaskManager` when a queued task begins running."""

    task_id: str = ""
    name: str = ""


@dataclass(frozen=True, slots=True)
class TaskCompletedEvent(Event):
    """Published when a background task's factory returns without
    raising."""

    task_id: str = ""
    name: str = ""
    duration_ms: float = 0.0


@dataclass(frozen=True, slots=True)
class TaskFailedEvent(Event):
    """Published when a background task's factory raises. The failure
    is isolated to that one task -- the manager keeps running every
    other queued/in-flight task."""

    task_id: str = ""
    name: str = ""
    detail: str = ""


# --- Crash Recovery (Milestone 9 Task Group C) --------------------------------
@dataclass(frozen=True, slots=True)
class CrashRecoveredEvent(Event):
    """Published by :class:`~jarvis.core.lifecycle.crash_recovery.
    CrashRecoveryManager` when startup finds the previous run's
    on-disk marker still reading "dirty" -- the previous process never
    reached a clean shutdown."""

    previous_boot_at: str = ""


# --- Resource Manager (Milestone 9 Task Group C) ------------------------------
@dataclass(frozen=True, slots=True)
class ResourceBudgetExceededEvent(Event):
    """Published by :class:`~jarvis.core.lifecycle.resource_manager.
    ResourceManager` the moment a tracked resource crosses its
    configured budget (not on every subsequent tick it stays over)."""

    resource: str = ""
    used: float = 0.0
    budget: float = 0.0


@dataclass(frozen=True, slots=True)
class VoiceStateChangedEvent(Event):
    """Fired whenever the voice pipeline's state machine transitions."""

    state: str = "idle"
    detail: str = ""


@dataclass(frozen=True, slots=True)
class AutomationStepEvent(Event):
    """Fired by the AI Automation Engine after every step attempt (Milestone 4)."""

    step_id: str = ""
    action: str = ""
    status: str = ""


@dataclass(frozen=True, slots=True)
class UpdatePhaseEvent(Event):
    """Fired by the (mock) Update Center pipeline on every phase transition
    (Milestone 5). Drives the sidebar progress indicator, the Update
    Terminal's live log feed, and AI voice announcements."""

    session_id: str = ""
    phase: str = "idle"
    progress_percent: int = 0
    message: str = ""


@dataclass(frozen=True, slots=True)
class AgentStepEvent(Event):
    """Fired by :class:`~jarvis.agents.orchestrator.AgentOrchestrator` after
    every LangGraph node transition (Milestone 5-Agents). Drives the
    Developer Mode Agent Trace panel; not persisted anywhere."""

    thread_id: str = ""
    step: int = 0
    node: str = ""
    status: str = "ok"
    detail: str = ""


# --- Universal Search & Knowledge Platform (Milestone 10A) -------------------
@dataclass(frozen=True, slots=True)
class MemoryUpdatedEvent(Event):
    """Published by :class:`~jarvis.services.memory_service.MemoryService`
    on ``remember``/``forget``/``forget_all`` -- realizes the ``memory``
    WebSocket category ``docs/ARCHITECTURE.md`` §6 documented as a target
    since Milestone 9 but nothing published until now."""

    memory_id: str = ""
    action: str = "created"  # "created" | "deleted" | "cleared"


@dataclass(frozen=True, slots=True)
class MemoryRecalledEvent(Event):
    """Published by :class:`~jarvis.services.memory_service.MemoryService`
    when :meth:`~jarvis.services.memory_service.MemoryService.recall`
    returns at least one result."""

    query: str = ""
    result_count: int = 0


@dataclass(frozen=True, slots=True)
class KnowledgeEntityUpdatedEvent(Event):
    """Published by :class:`~jarvis.services.knowledge_service.KnowledgeService`
    when entity/relationship extraction persists at least one new row."""


@dataclass(frozen=True, slots=True)
class KnowledgeCorrectionAppliedEvent(Event):
    """Published by :class:`~jarvis.services.knowledge_service.KnowledgeService`
    when a correction supersedes or creates a relationship (Milestone 10A
    Acceptance Criterion 3)."""


# --- Intelligence Layer (Milestone 10B) --------------------------------------
@dataclass(frozen=True, slots=True)
class GoalUpdatedEvent(Event):
    """Published by :class:`~jarvis.services.intelligence_service.IntelligenceService`
    on goal create/progress-update/complete/delete."""

    goal_id: str = ""
    action: str = "created"  # "created" | "progress_updated" | "completed" | "deleted"


@dataclass(frozen=True, slots=True)
class DailyBriefingGeneratedEvent(Event):
    """Published by :class:`~jarvis.services.intelligence_service.IntelligenceService`
    each time ``IntelligenceService.generate_daily_briefing`` runs. On-demand
    only today -- see that method's own docstring for why automatic
    scheduling via M7 is deferred, not built here."""


# --- MCP platform (Milestone 10.5 Task Group A) -------------------------------
@dataclass(frozen=True, slots=True)
class MCPConnectionChangedEvent(Event):
    """Published by :class:`~jarvis.core.mcp.client.MCPClientRuntime` on
    every connection state transition. One event class with a ``state``
    field rather than one class per transition -- the same shape
    ``MemoryUpdatedEvent``/``GoalUpdatedEvent`` already established."""

    server_id: str = ""
    state: str = "disconnected"  # see MCPConnectionState
    detail: str = ""


@dataclass(frozen=True, slots=True)
class MCPCapabilitiesChangedEvent(Event):
    """Published when a capability registry's contents change -- JARVIS
    exposing a new capability, or a peer's discovered set being replaced
    on (re)connect."""

    owner: str = ""
    count: int = 0


@dataclass(frozen=True, slots=True)
class MCPHandshakeCompletedEvent(Event):
    """Published once a peer and JARVIS agree on a protocol version.
    Distinct from :class:`MCPConnectionChangedEvent` -- a transport can
    be connected while the handshake is still in flight, and a failed
    handshake is a *protocol* problem, not a connectivity one."""

    server_id: str = ""
    agreed_version: str = ""
    transport_type: str = ""


@dataclass(frozen=True, slots=True)
class MCPNegotiationCompletedEvent(Event):
    """Published after capability negotiation resolves -- how many of a
    peer's offered capabilities survived permission filtering, and how
    many were dropped."""

    server_id: str = ""
    accepted: int = 0
    rejected: int = 0


@dataclass(frozen=True, slots=True)
class MCPTransportFailedEvent(Event):
    """A transport-level failure (connect refused, stream lost, peer
    process died). Separate from a permission denial or a negotiation
    rejection, both of which are the protocol working correctly."""

    server_id: str = ""
    transport_type: str = ""
    detail: str = ""


@dataclass(frozen=True, slots=True)
class MCPHeartbeatEvent(Event):
    """One liveness probe result, published per connected peer per tick
    by :class:`~jarvis.core.mcp.heartbeat.MCPHeartbeatMonitor`."""

    server_id: str = ""
    healthy: bool = True
    latency_ms: float = 0.0
    detail: str = ""


@dataclass(frozen=True, slots=True)
class MCPProviderStateChangedEvent(Event):
    """Every provider lifecycle transition -- Milestone 10.5 Task Group C.

    One event class carrying an ``action`` field rather than eight
    classes (registered/initialized/connected/disconnected/suspended/
    resumed/failed/removed), matching the shape
    ``MemoryUpdatedEvent``/``GoalUpdatedEvent``/
    ``MCPConnectionChangedEvent`` already established. ``action`` is the
    transition; ``state`` is the resting state it landed in -- the two
    differ for ``resumed``, which lands in ``connected``.
    """

    provider_id: str = ""
    action: str = "registered"  # see PROVIDER_ACTIONS
    state: str = "registered"  # see ProviderState
    detail: str = ""


@dataclass(frozen=True, slots=True)
class MCPAuthStateChangedEvent(Event):
    """Every authentication lifecycle transition -- Milestone 10.5 Task
    Group D.

    One event class carrying an ``action`` field rather than eight
    classes (authentication_started/completed/failed, token_refreshed,
    token_expired, credential_revoked, provider_authenticated,
    provider_disconnected), matching the shape
    ``MCPProviderStateChangedEvent``/``MCPConnectionChangedEvent``
    already established.

    **Carries no secret.** ``detail`` is a human-readable reason and
    ``method``/``session_state`` are metadata -- a token value never
    reaches the relay, because every subscriber (including remote
    WebSocket clients) would otherwise receive it.
    """

    provider_id: str = ""
    action: str = "authentication_started"  # see AUTH_ACTIONS
    method: str = "none"
    session_state: str = "unauthenticated"
    detail: str = ""


@dataclass(frozen=True, slots=True)
class MCPPermissionDeniedEvent(Event):
    """Published when the MCP server runtime refuses a capability
    invocation. Distinct from
    :class:`PluginPermissionDeniedEvent` (a *decision* on a plugin's
    request) -- this reports an *enforcement* at call time."""

    principal: str = ""
    capability: str = ""
    scope: str = ""


@dataclass(frozen=True, slots=True)
class VisionProviderStatusEvent(Event):
    """Reports a vision/OCR provider's health (Milestone 6, Phase 4). Not
    yet published anywhere -- no provider does real capture/OCR work, so
    there is nothing to report a status change *from*. Defined now so
    future phases can publish it without touching this file again."""

    provider: str = ""
    healthy: bool = False
    detail: str = ""


@dataclass(frozen=True, slots=True)
class WorkflowStepEvent(Event):
    """Fired after every WorkflowStep attempt (Milestone 7). Not yet
    published anywhere -- no workflow executes until Phase 4 (Workflow
    Builder) wires a WorkflowDefinition through the same execution path
    AutomationStepEvent already drives. Defined now, mirroring
    AutomationStepEvent's shape, so future phases can publish it without
    touching this file again."""

    workflow_id: str = ""
    step_id: str = ""
    status: str = ""


## --- Plugin Platform (Milestone 9 Task Group D) ------------------------------
@dataclass(frozen=True, slots=True)
class PluginDiscoveredEvent(Event):
    """Published by :class:`~jarvis.core.plugins.registry.PluginRegistry`
    when :class:`~jarvis.core.plugins.loader.PluginLoader.discover` finds
    a plugin with a valid manifest, before any attempt to load it."""

    plugin_id: str = ""


@dataclass(frozen=True, slots=True)
class PluginLoadedEvent(Event):
    """Published once a plugin's ``on_load``+``on_start`` hooks have
    both run successfully through the Sandbox."""

    plugin_id: str = ""


@dataclass(frozen=True, slots=True)
class PluginLoadFailedEvent(Event):
    """Published when a plugin fails discovery/compatibility/import/
    ``on_load``/``on_start`` -- isolated to this one plugin, matching
    every other M9 fault-isolation guarantee."""

    plugin_id: str = ""
    detail: str = ""


@dataclass(frozen=True, slots=True)
class PluginUnloadedEvent(Event):
    """Published once a plugin's ``on_stop`` has run and its module has
    been un-imported."""

    plugin_id: str = ""


@dataclass(frozen=True, slots=True)
class PluginCrashedEvent(Event):
    """Published when a loaded, running plugin raises outside of a
    normal hook call the Sandbox was already isolating (Registry-level
    detection -- e.g. a health check the Registry itself performs)."""

    plugin_id: str = ""
    detail: str = ""


@dataclass(frozen=True, slots=True)
class PluginEnabledEvent(Event):
    plugin_id: str = ""


@dataclass(frozen=True, slots=True)
class PluginDisabledEvent(Event):
    plugin_id: str = ""


@dataclass(frozen=True, slots=True)
class PluginPermissionGrantedEvent(Event):
    """Published by :class:`~jarvis.core.plugins.permissions.PermissionModel`
    when a scope is granted -- part of the Permission Model's audit
    trail (Phase 5), not only a runtime signal."""

    plugin_id: str = ""
    scope: str = ""


@dataclass(frozen=True, slots=True)
class PluginPermissionDeniedEvent(Event):
    """Published on every denied permission check -- including a check
    against a scope that was simply never granted (least-privilege
    default), not only an explicit revocation."""

    plugin_id: str = ""
    scope: str = ""


@dataclass(frozen=True, slots=True)
class PluginInstalledEvent(Event):
    plugin_id: str = ""


@dataclass(frozen=True, slots=True)
class PluginUninstalledEvent(Event):
    plugin_id: str = ""


@dataclass(frozen=True, slots=True)
class PluginUpdatedEvent(Event):
    plugin_id: str = ""
    from_version: str = ""
    to_version: str = ""


@dataclass(frozen=True, slots=True)
class PluginCustomEvent(Event):
    """A plugin's own application-level event, published through
    :class:`~jarvis.core.plugins.extension_api.PluginContext`'s event
    channel (Phase 4). Deliberately a single, namespaced wrapper type
    rather than letting a plugin construct arbitrary core ``Event``
    subclasses -- a plugin cannot forge e.g. a ``ServiceFailedEvent``
    for a service it doesn't own."""

    plugin_id: str = ""
    name: str = ""
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PluginNotificationEvent(Event):
    """Published through the Extension API's permission-gated
    ``notifications`` scope (Phase 4). No frontend surface consumes
    this yet -- the same "real event, honestly zero consumers today"
    pattern the Voice String/Live Transcript stores already establish."""

    plugin_id: str = ""
    title: str = ""
    message: str = ""


## --- Developer Platform Tools (Milestone 9 Task Group E) ---------------------
@dataclass(frozen=True, slots=True)
class DebugLogCapturedEvent(Event):
    """Published by :class:`~jarvis.core.devtools.debug_console.
    DebugConsole` for every log line captured through its own loguru
    sink -- the real-time half of "Debug Console"/"Live Logs" (the
    console's own bounded buffer, queried over REST, is the other
    half). Fire-and-forget (``EventBus.publish_nowait``) since loguru's
    ``enqueue=True`` sink runs on its own background writer thread, not
    the app's main event loop."""

    level: str = ""
    logger: str = ""
    message: str = ""
    at: str = ""


@dataclass(frozen=True, slots=True)
class ScheduledJobFiredEvent(Event):
    """Fired when the Scheduler (Milestone 7, Phase 6) dispatches a due
    job. Not yet published anywhere -- no scheduler loop exists until
    Phase 6. Defined now so future phases can publish it without
    touching this file again."""

    schedule_id: str = ""
    workflow_id: str = ""
    status: str = ""


# ---------------------------------------------------------------------------
# Milestone 11 Task Group A — Workspace Foundation
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class WorkspaceUpdatedEvent(Event):
    """Published by :class:`~jarvis.services.workspace_service.WorkspaceService`
    on workspace create/update/archive/delete.

    One event class carrying an ``action`` field rather than one class
    per transition -- the shape ``MemoryUpdatedEvent``, ``GoalUpdatedEvent``
    and ``MCPProviderStateChangedEvent`` all already use. A subscriber
    that cares about every workspace change subscribes once; one that
    cares about a single transition branches on ``action``."""

    workspace_id: str = ""
    action: str = "created"  # created|updated|archived|deleted


@dataclass(frozen=True, slots=True)
class ProjectUpdatedEvent(Event):
    """Published on project create/update/complete/delete. Carries
    ``workspace_id`` as well so a subscriber scoped to one workspace can
    filter without a lookup."""

    project_id: str = ""
    workspace_id: str = ""
    action: str = "created"  # created|updated|completed|deleted


@dataclass(frozen=True, slots=True)
class NoteUpdatedEvent(Event):
    """Published on note create/update/delete. ``project_id`` is empty
    for a note filed directly against the workspace, which is the
    normal case rather than an error -- see ``Note``'s own docstring."""

    note_id: str = ""
    workspace_id: str = ""
    project_id: str = ""
    action: str = "created"  # created|updated|deleted


# ---------------------------------------------------------------------------
# Milestone 11 Task Group B — Productivity Core
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class TaskUpdatedEvent(Event):
    """Published by :class:`~jarvis.services.task_service.TaskService` on
    task create/update/complete/delete.

    One class with an ``action`` field, not one class per transition --
    the shape ``memory.updated``/``goal.updated``/``workspace.updated``
    all use. Carries ``workspace_id`` so a subscriber scoped to one
    workspace can filter without a lookup."""

    task_id: str = ""
    workspace_id: str = ""
    project_id: str = ""
    action: str = "created"  # created|updated|completed|deleted


@dataclass(frozen=True, slots=True)
class CalendarEventUpdatedEvent(Event):
    """Published by :class:`~jarvis.services.calendar_service.CalendarService`
    on event create/update/delete.

    Named for the *calendar event* it describes; the doubled word is
    unfortunate but the alternative (``EventUpdatedEvent``) would read as
    "an event about events" next to a base class already called
    ``Event``."""

    event_id: str = ""
    calendar_id: str = ""
    workspace_id: str = ""
    action: str = "created"  # created|updated|deleted


@dataclass(frozen=True, slots=True)
class CalendarUpdatedEvent(Event):
    """Published on calendar create/update/delete -- the container, not
    its events."""

    calendar_id: str = ""
    workspace_id: str = ""
    action: str = "created"  # created|updated|deleted


@dataclass(frozen=True, slots=True)
class ReminderUpdatedEvent(Event):
    """Published by :class:`~jarvis.services.reminder_service.ReminderService`
    on reminder create/update/dismiss/cancel/delete.

    Note what is *not* here: there is no ``reminder.fired``. Nothing in
    Milestone 11 Task Group B delivers a reminder -- that is M7's
    Scheduler (Phase 6). Defining a firing event now would advertise a
    transition no code can reach."""

    reminder_id: str = ""
    workspace_id: str = ""
    action: str = "created"  # created|updated|dismissed|cancelled|deleted


# ---------------------------------------------------------------------------
# Milestone 11 Task Group C — File Platform
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class FileUpdatedEvent(Event):
    """Published by :class:`~jarvis.services.file_service.FileService` on
    file create/update/move/rename/index/delete.

    Six transitions, one class with an ``action`` field -- the shape
    every domain from ``memory.updated`` onward uses. ``indexed`` is one
    of them rather than its own event because a subscriber watching a
    file almost always wants all six, and the one that only wants
    indexing branches on a string instead of subscribing twice.

    ``relative_path`` travels with the event because the commonest
    reaction to a move or rename is to update a displayed path, and
    re-reading the row to learn where it went would make every listener
    do a query the publisher had the answer to.
    """

    file_id: str = ""
    workspace_id: str = ""
    folder_id: str = ""
    relative_path: str = ""
    action: str = "created"  # created|updated|moved|renamed|indexed|deleted


@dataclass(frozen=True, slots=True)
class FolderUpdatedEvent(Event):
    """Published on folder create/rename/move/delete.

    A move or a delete can rewrite or remove a whole subtree, so
    ``affected_files`` reports how many file rows the operation touched.
    A listener refreshing a tree view needs to know the difference
    between "one folder changed" and "four hundred paths just moved".
    """

    folder_id: str = ""
    workspace_id: str = ""
    parent_folder_id: str = ""
    relative_path: str = ""
    affected_files: int = 0
    action: str = "created"  # created|renamed|moved|deleted


@dataclass(frozen=True, slots=True)
class AttachmentUpdatedEvent(Event):
    """Published on attach/detach.

    ``target`` and ``target_id`` are the flattened view of the five
    nullable foreign keys on ``WorkspaceAttachment``: the row needs real
    constraints, but a subscriber only needs to know what the file was
    attached to. ``target`` is ``"workspace"`` when the file is filed
    against the workspace itself, which is the default rather than a
    missing value.
    """

    attachment_id: str = ""
    workspace_id: str = ""
    file_id: str = ""
    target: str = "workspace"  # workspace|project|note|task|event|reminder
    target_id: str = ""
    action: str = "attached"  # attached|detached


# ---------------------------------------------------------------------------
# Milestone 11 Task Group D — AI Workspace
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class WorkspaceKnowledgeLinkedEvent(Event):
    """Published by
    :class:`~jarvis.services.workspace_ai_service.WorkspaceKnowledgeService`
    when a workspace entity is linked to, or unlinked from, a knowledge
    entity.

    One class with an ``action`` field, the shape every domain from
    ``memory.updated`` onward uses. ``target``/``target_id`` are the
    flattened view of the four nullable foreign keys on
    ``WorkspaceKnowledgeLink`` -- the row needs real constraints, a
    subscriber only needs to know what was linked.

    ``source`` travels with the event because the commonest reaction to
    a re-ingestion is to refresh a view, and "forty extracted links were
    replaced" and "one link a person asserted was removed" call for
    different reactions.

    ``reingested`` is the batch action, published once per target rather
    than once per link, and it is the one case where ``link_id`` and
    ``entity_id`` are empty -- a rebuild of a target's extracted links is
    not about any one of them. It is a distinct action rather than a
    ``linked`` with blank ids precisely so that emptiness reads as the
    documented shape of a batch instead of a missing field.
    """

    link_id: str = ""
    workspace_id: str = ""
    entity_id: str = ""
    target: str = "workspace"  # workspace|project|note|task|file
    target_id: str = ""
    source: str = "extracted"  # extracted|manual
    action: str = "linked"  # linked|promoted|unlinked|reingested


@dataclass(frozen=True, slots=True)
class WorkspaceAssistCompletedEvent(Event):
    """Published by
    :class:`~jarvis.services.workspace_ai_service.WorkspaceAssistantService`
    once an assist call has produced an answer.

    Carries no answer text. The event exists so a UI can show that the
    assistant ran and on what, and relaying the answer would put a
    model's full output into every connected client's replay buffer for
    a request only one of them made. ``synthesized`` distinguishes a
    real LLM answer from the extractive fallback the assistant returns
    when no provider is reachable -- the one fact a caller cannot infer
    from the text itself.
    """

    workspace_id: str = ""
    mode: str = "summarize"  # summarize|ask|next_actions
    synthesized: bool = True
    citation_count: int = 0


# ---------------------------------------------------------------------------
# Milestone 11 Task Group E — Integration Platform
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class IntegrationCallCompletedEvent(Event):
    """Published by
    :class:`~jarvis.services.integration_service.IntegrationService` after
    every outbound vendor call -- the audit trail the roadmap's "single,
    audited egress point" requires.

    **Carries no request body and no response body.** A Gmail request
    body is the text of an email and a response body is someone's
    inbox; relaying either would put it in every connected client's
    replay buffer for a call one of them made. What travels is what an
    audit needs: which integration, which operation, what the vendor
    said, and whether the answer came from the gateway's cache rather
    than the network.

    Provider lifecycle transitions are **not** here: an integration is
    an MCP provider, so connecting one publishes the
    ``MCPProviderStateChangedEvent`` every provider publishes, and
    authorizing one publishes ``MCPAuthStateChangedEvent``. A third
    event for the same transitions would be a second notification path
    for one thing happening.
    """

    integration_id: str = ""
    operation: str = ""
    status_code: int = 0
    ok: bool = True
    from_cache: bool = False
    detail: str = ""


# ---------------------------------------------------------------------------
# Milestone 12 Task Group A -- Smart Home Core
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class HomeUpdatedEvent(Event):
    """Published by
    :class:`~jarvis.services.smart_home_service.SmartHomeService` on
    home create/update/archive/delete. One event class carrying an
    ``action`` field, same convention as ``WorkspaceUpdatedEvent``."""

    home_id: str = ""
    action: str = "created"  # created|updated|archived|deleted


@dataclass(frozen=True, slots=True)
class DeviceUpdatedEvent(Event):
    """Published on device create/update/status-change/delete.

    ``action="status_changed"`` is its own value distinct from
    ``"updated"`` -- a subscriber watching for a device going
    ``offline``/``unreachable`` (a future Device Health Monitoring
    consumer) cares about that transition specifically, not every
    field edit."""

    device_id: str = ""
    home_id: str = ""
    action: str = "created"  # created|updated|status_changed|deleted
    status: str = ""
