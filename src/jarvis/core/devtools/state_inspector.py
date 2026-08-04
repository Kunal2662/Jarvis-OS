"""State Inspector -- Milestone 9 Task Group E.

"A live view into Service Manager's registry and each service's state"
-- made real by combining three already-real, already-shipped
snapshots into one unified view, rather than building a fourth,
parallel state-tracking mechanism:

* :meth:`~jarvis.core.lifecycle.service_manager.ServiceManager.snapshot`
  (Task Group B) -- first-party service states.
* :meth:`~jarvis.core.plugins.registry.PluginRegistry.snapshot`
  (Task Group D) -- plugin states, extending the same inspection
  surface to the newest stateful registry in the runtime.
* :attr:`~jarvis.core.lifecycle.runtime_manager.RuntimeManager.
  registered_startup_names` / ``registered_names`` -- the ordered
  lifecycle hooks each phase actually registered, not a hand-maintained
  duplicate list.

All three are optional constructor arguments -- a caller (a test, a
lighter-weight runtime mode) that only has some of them still gets a
real, partial snapshot rather than an error.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jarvis.core.lifecycle.runtime_manager import RuntimeManager
    from jarvis.core.lifecycle.service_manager import ServiceManager
    from jarvis.core.plugins.registry import PluginRegistry


@dataclass(frozen=True, slots=True)
class ServiceStateView:
    name: str
    state: str
    dependencies: tuple[str, ...]
    error: str = ""


@dataclass(frozen=True, slots=True)
class PluginStateView:
    plugin_id: str
    display_name: str
    version: str
    state: str
    error: str = ""


@dataclass(frozen=True, slots=True)
class StateInspectorSnapshot:
    services: tuple[ServiceStateView, ...] = field(default_factory=tuple)
    plugins: tuple[PluginStateView, ...] = field(default_factory=tuple)
    startup_hooks: tuple[str, ...] = field(default_factory=tuple)
    shutdown_hooks: tuple[str, ...] = field(default_factory=tuple)


class StateInspector:
    def __init__(
        self,
        *,
        service_manager: ServiceManager | None = None,
        plugin_registry: PluginRegistry | None = None,
        runtime_manager: RuntimeManager | None = None,
    ) -> None:
        self._service_manager = service_manager
        self._plugin_registry = plugin_registry
        self._runtime_manager = runtime_manager

    def snapshot(self) -> StateInspectorSnapshot:
        services: tuple[ServiceStateView, ...] = ()
        if self._service_manager is not None:
            services = tuple(
                ServiceStateView(
                    name=s.name, state=s.state, dependencies=s.dependencies, error=s.error
                )
                for s in self._service_manager.snapshot()
            )

        plugins: tuple[PluginStateView, ...] = ()
        if self._plugin_registry is not None:
            plugins = tuple(
                PluginStateView(
                    plugin_id=p.plugin_id,
                    display_name=p.display_name,
                    version=p.version,
                    state=p.state,
                    error=p.error,
                )
                for p in self._plugin_registry.snapshot()
            )

        startup_hooks: tuple[str, ...] = ()
        shutdown_hooks: tuple[str, ...] = ()
        if self._runtime_manager is not None:
            startup_hooks = tuple(self._runtime_manager.registered_startup_names)
            shutdown_hooks = tuple(self._runtime_manager.registered_names)

        return StateInspectorSnapshot(
            services=services,
            plugins=plugins,
            startup_hooks=startup_hooks,
            shutdown_hooks=shutdown_hooks,
        )
