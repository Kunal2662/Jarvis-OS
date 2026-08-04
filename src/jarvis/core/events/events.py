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


@dataclass(frozen=True, slots=True)
class ScheduledJobFiredEvent(Event):
    """Fired when the Scheduler (Milestone 7, Phase 6) dispatches a due
    job. Not yet published anywhere -- no scheduler loop exists until
    Phase 6. Defined now so future phases can publish it without
    touching this file again."""

    schedule_id: str = ""
    workflow_id: str = ""
    status: str = ""
