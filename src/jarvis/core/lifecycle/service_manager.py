"""``ServiceManager`` -- the real registry of running services M9's own
spec calls for: *"a registry of every running service ... with health
status, built on the existing `core/di/container.py` rather than a
second registry."* (Milestone 9 Task Group B.)

Orchestrates :class:`~jarvis.core.interfaces.service.IService` in the
order its declared dependency graph requires, tracks each service's
lifecycle state, and polls health -- one fault-isolated failure never
blocks an unrelated service, matching :class:`~jarvis.core.lifecycle.
runtime_manager.RuntimeManager`'s own design philosophy (composition,
not a competing lifecycle mechanism: `ServiceManager` itself registers
as exactly one startup/shutdown hook pair with `RuntimeManager`, see
`app.py`).

**Why only four services are registered today**, not the full set
`services/` contains: no existing service implements `IService` (see
`core/interfaces/service.py`'s own docstring) -- rather than retrofit
every service (a separate, larger migration outside this task group),
this module wraps a small, curated, *conflict-free* set in thin
adapters:

* `ConversationServiceAdapter`, `ChatServiceAdapter` -- pure,
  side-effect-free domain services with no existing lifecycle owner
  anywhere. `chat` genuinely depends on `conversation` (mirrors
  `core/di/container.py`'s own constructor wiring,
  `chat_service = providers.Singleton(..., conversations=conversation_service, ...)`),
  giving the dependency graph below a real edge to prove, not a fabricated one.
* `MemoryServiceAdapter` -- `start()` now runs the real
  `enforce_policies()` call that used to be a standalone `app.py`
  startup hook (Task Group A); moved here so it has exactly one real
  owner instead of two.
* `ThemeServiceAdapter` -- another pure, conflict-free service.

**Deliberately excluded**: `VoiceService` and `HotkeyService` already
have a real shutdown-hook owner -- `ui/main_window.py`'s
`_register_shutdown_hooks()`, registered directly against
`RuntimeManager` since before this task group. Registering them here
too would give one service two competing lifecycle owners. Migrating
that ownership into `ServiceManager` is real, valid future work, not
something this task group decides unilaterally (see the changelog
addendum's "Future Work" section). `BrowserService`/`AutomationService`/
`SystemService` are DI `Factory` providers (a new instance every
resolution, per `core/di/container.py`) -- they have no stable
identity a registry could poll `health()` on repeatedly.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from jarvis.core.events.events import ServiceFailedEvent, ServiceStartedEvent, ServiceStoppedEvent
from jarvis.core.interfaces.service import HealthStatus, IService, ServiceStatus
from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.core.events.event_bus import EventBus

_logger = get_logger("jarvis.core.lifecycle.service_manager")


class ServiceState(enum.StrEnum):
    REGISTERED = "registered"
    INITIALIZING = "initializing"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Adapters -- thin IService wrappers over real, existing services.
# Composition, not modification: none of the wrapped service classes change.
# ---------------------------------------------------------------------------
class ConversationServiceAdapter:
    """No real start/stop work -- a pure DB-backed CRUD wrapper, ready
    as soon as it's constructed. `health()` is honestly unconditional:
    there is no background work here that can silently die."""

    def __init__(self, conversation_service: Any) -> None:
        self._service = conversation_service

    async def initialize(self) -> None:
        pass

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def health(self) -> HealthStatus:
        return HealthStatus(healthy=True)

    async def status(self) -> ServiceStatus:
        return ServiceStatus(name="conversation_service", state="ready")

    async def shutdown(self) -> None:
        pass


class ChatServiceAdapter:
    """Same shape as `ConversationServiceAdapter` -- `ChatService` has
    no lifecycle needs of its own, only domain methods (`ask`/`stream`)."""

    def __init__(self, chat_service: Any) -> None:
        self._service = chat_service

    async def initialize(self) -> None:
        pass

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def health(self) -> HealthStatus:
        return HealthStatus(healthy=True)

    async def status(self) -> ServiceStatus:
        return ServiceStatus(name="chat_service", state="ready")

    async def shutdown(self) -> None:
        pass


class MemoryServiceAdapter:
    """`start()` runs the real `enforce_policies()` call -- moved here
    from `app.py`'s own ad-hoc startup hook (Task Group A) so
    memory-policy enforcement has exactly one real owner."""

    def __init__(self, memory_service: Any, *, enabled: bool) -> None:
        self._service = memory_service
        self._enabled = enabled
        self._healthy = True

    async def initialize(self) -> None:
        pass

    async def start(self) -> None:
        if not self._enabled:
            return
        try:
            await self._service.enforce_policies()
        except Exception as err:
            self._healthy = False
            _logger.warning("Memory policy enforcement failed at startup: {}", err)
            raise

    async def stop(self) -> None:
        pass

    async def health(self) -> HealthStatus:
        if not self._healthy:
            return HealthStatus(healthy=False, detail="Last policy enforcement failed.")
        return HealthStatus(healthy=True)

    async def status(self) -> ServiceStatus:
        return ServiceStatus(
            name="memory_service", state="ready", detail={"policies_enabled": self._enabled}
        )

    async def shutdown(self) -> None:
        pass


class ThemeServiceAdapter:
    def __init__(self, theme_service: Any) -> None:
        self._service = theme_service

    async def initialize(self) -> None:
        pass

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def health(self) -> HealthStatus:
        return HealthStatus(healthy=True)

    async def status(self) -> ServiceStatus:
        return ServiceStatus(name="theme_service", state="ready")

    async def shutdown(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class _Entry:
    name: str
    service: IService
    dependencies: tuple[str, ...]
    priority: int
    state: ServiceState = ServiceState.REGISTERED
    error: str = ""


@dataclass(frozen=True, slots=True)
class ServiceSnapshot:
    """A `ServiceManager`-wide snapshot -- Developer Mode's future State
    Inspector reads this, not each service's internals directly."""

    name: str
    state: str
    dependencies: tuple[str, ...]
    error: str = ""


class ServiceManager:
    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._entries: dict[str, _Entry] = {}
        self._has_started = False
        self._restart_count = 0

    # ---- Registration ---------------------------------------------------
    def register(
        self,
        name: str,
        service: IService,
        *,
        dependencies: tuple[str, ...] = (),
        priority: int = 50,
    ) -> None:
        """Register a service. Re-registering an existing *name*
        replaces it (idempotent for tests/re-construction), matching
        `RuntimeManager.register()`'s own convention."""
        self._entries[name] = _Entry(
            name=name, service=service, dependencies=dependencies, priority=priority
        )

    def is_registered(self, name: str) -> bool:
        return name in self._entries

    @property
    def registered_names(self) -> tuple[str, ...]:
        return tuple(self._entries)

    def get_state(self, name: str) -> ServiceState:
        return self._entries[name].state

    def snapshot(self) -> tuple[ServiceSnapshot, ...]:
        return tuple(
            ServiceSnapshot(e.name, e.state.value, e.dependencies, e.error)
            for e in (self._entries[n] for n in self._ordered_names())
        )

    @property
    def restart_count(self) -> int:
        """Total successful :meth:`restart` calls across every service
        this run -- read directly by :class:`~jarvis.core.lifecycle.
        health_monitor.HealthMonitor` rather than duplicating the
        counter there."""
        return self._restart_count

    # ---- Ordering ---------------------------------------------------------
    def _ordered_names(self) -> list[str]:
        """Kahn's-algorithm topological sort: a service's dependencies
        always come before it. Among services with no remaining
        unsatisfied dependency at a given step, lower `priority` runs
        first, then registration order -- the same tie-break rule
        `RuntimeManager` already uses."""
        remaining = dict(self._entries)
        satisfied: set[str] = set()
        ordered: list[str] = []

        while remaining:
            ready = [
                e for e in remaining.values() if all(dep in satisfied for dep in e.dependencies)
            ]
            if not ready:
                cyclic = ", ".join(sorted(remaining))
                raise ValueError(f"Circular or missing service dependency among: {cyclic}")
            ready.sort(key=lambda e: (e.priority, list(self._entries).index(e.name)))
            chosen = ready[0]
            ordered.append(chosen.name)
            satisfied.add(chosen.name)
            del remaining[chosen.name]

        return ordered

    # ---- Startup ------------------------------------------------------
    async def start_all(self) -> None:
        """`initialize()` then `start()` every registered service, in
        dependency order. Never raises: one service failing is caught,
        logged, published as `ServiceFailedEvent`, and marks that
        service (and only that service) `FAILED` -- every independent
        service still starts. A service whose *dependency* failed is
        skipped (not started in a broken state) and itself marked
        `FAILED`, which is real dependency semantics, not a fault-
        isolation gap."""
        if self._has_started:
            _logger.warning("ServiceManager.start_all() called more than once -- ignoring.")
            return
        self._has_started = True

        failed: set[str] = set()
        for name in self._ordered_names():
            entry = self._entries[name]
            if any(dep in failed for dep in entry.dependencies):
                entry.state = ServiceState.FAILED
                entry.error = "A dependency failed to start."
                failed.add(name)
                _logger.warning("Service {!r} skipped: dependency failure.", name)
                continue

            entry.state = ServiceState.INITIALIZING
            try:
                await entry.service.initialize()
                await entry.service.start()
            except Exception as err:
                entry.state = ServiceState.FAILED
                entry.error = str(err)
                failed.add(name)
                _logger.exception("Service {!r} failed to start.", name)
                await self._event_bus.publish(ServiceFailedEvent(service=name, detail=str(err)))
                continue

            entry.state = ServiceState.RUNNING
            _logger.info("Service {!r} started.", name)
            await self._event_bus.publish(ServiceStartedEvent(service=name))

    async def stop_all(self) -> None:
        """`stop()` then `shutdown()` every registered service, in
        reverse dependency order. Same fault-isolation guarantee as
        `start_all()` -- one failure never blocks the rest."""
        for name in reversed(self._ordered_names()):
            entry = self._entries[name]
            if entry.state not in (ServiceState.RUNNING, ServiceState.FAILED):
                continue
            entry.state = ServiceState.STOPPING
            try:
                await entry.service.stop()
                await entry.service.shutdown()
            except Exception as err:
                entry.state = ServiceState.FAILED
                entry.error = str(err)
                _logger.exception("Service {!r} failed to stop cleanly.", name)
                continue
            entry.state = ServiceState.STOPPED
            _logger.info("Service {!r} stopped.", name)
            await self._event_bus.publish(ServiceStoppedEvent(service=name))

    async def restart(self, name: str) -> None:
        """Stop then start one named service. Does not cascade to
        dependents -- a dependent service already running against the
        old instance keeps running; restarting the full dependent
        subgraph is real future work (see the changelog addendum), not
        implied by this method's name today."""
        entry = self._entries[name]
        if entry.state == ServiceState.RUNNING:
            entry.state = ServiceState.STOPPING
            await entry.service.stop()
        entry.state = ServiceState.INITIALIZING
        try:
            await entry.service.start()
        except Exception as err:
            entry.state = ServiceState.FAILED
            entry.error = str(err)
            await self._event_bus.publish(ServiceFailedEvent(service=name, detail=str(err)))
            raise
        entry.state = ServiceState.RUNNING
        entry.error = ""
        self._restart_count += 1
        await self._event_bus.publish(ServiceStartedEvent(service=name))

    # ---- Health ---------------------------------------------------------
    async def poll_health(self) -> dict[str, HealthStatus]:
        """Cheap, frequent check across every `RUNNING` service. Called
        by the Health Monitor's own poll loop, not a substitute for it
        (this method only reports; `HealthMonitor` decides what to do
        with the result)."""
        results: dict[str, HealthStatus] = {}
        for name in self._ordered_names():
            entry = self._entries[name]
            if entry.state is not ServiceState.RUNNING:
                continue
            try:
                status = await entry.service.health()
            except Exception as err:
                status = HealthStatus(healthy=False, detail=str(err))
            results[name] = status
            if not status.healthy:
                entry.state = ServiceState.FAILED
                entry.error = status.detail
                await self._event_bus.publish(
                    ServiceFailedEvent(service=name, detail=status.detail)
                )
        return results
