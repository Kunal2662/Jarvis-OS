"""Connector factory registry -- Milestone 12 Task Group B, Phase 1.

:class:`~jarvis.core.interfaces.connectivity.IDeviceConnector` (the
port) lives in ``core/interfaces/connectivity.py``; this module holds
the registry future connectors register into. Directly mirrors
:class:`~jarvis.core.mcp.transport.TransportFactoryRegistry` -- same
shape, same reasoning: a plain callable per connector type, composition
over inheritance, no connector base class anywhere.

**No protocol-specific code, by design.** ``home_assistant`` and
``mqtt`` are named in
:data:`~jarvis.core.interfaces.connectivity.CONNECTOR_TYPES` and are
explicitly *not* implemented in this phase -- each is its own later
phase of this same task group and plugs in through
:meth:`ConnectorFactoryRegistry.register` without this module
changing, the same extensibility seam ``TransportFactoryRegistry``
gives MCP.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from jarvis.core.interfaces.connectivity import CONNECTOR_TYPES, ConnectivityError
from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.core.interfaces.connectivity import IDeviceConnector

_logger = get_logger("jarvis.core.connectivity.registry")

#: A factory takes the connector's own config dict and returns a
#: ready-but-unconnected connector. Deliberately a plain callable
#: rather than a class hierarchy, matching ``TransportFactory``'s own
#: reasoning -- composition over inheritance, per
#: ``docs/ARCHITECTURE.md``'s development principles.
ConnectorFactory = Callable[[dict[str, Any]], "IDeviceConnector"]


class ConnectorRegistrationError(ConnectivityError):
    """Raised when a caller registers or requests an unknown connector
    type -- the same "reject rather than silently ignore" posture
    ``TransportFactoryRegistry`` already applies."""


class ConnectorFactoryRegistry:
    """Maps a connector type name to the factory that builds it.

    Empty of real connectors at construction. A phase that adds Home
    Assistant calls ``register("home_assistant", build_home_assistant_
    connector)`` at its DI composition root; nothing in
    ``ConnectivityService`` branches on connector type.
    """

    def __init__(self) -> None:
        self._factories: dict[str, ConnectorFactory] = {}

    def register(self, connector_type: str, factory: ConnectorFactory) -> None:
        if connector_type not in CONNECTOR_TYPES:
            raise ConnectorRegistrationError(
                f"Unknown connector type {connector_type!r}; allowed: {sorted(CONNECTOR_TYPES)}"
            )
        self._factories[connector_type] = factory
        _logger.info("Connectivity connector registered: {}", connector_type)

    def unregister(self, connector_type: str) -> bool:
        return self._factories.pop(connector_type, None) is not None

    def create(self, connector_type: str, config: dict[str, Any] | None = None) -> IDeviceConnector:
        factory = self._factories.get(connector_type)
        if factory is None:
            raise ConnectorRegistrationError(
                f"No connector registered for {connector_type!r}. "
                f"Registered: {sorted(self._factories) or 'none'}."
            )
        return factory(config or {})

    @property
    def registered_types(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))

    def supports(self, connector_type: str) -> bool:
        return connector_type in self._factories
