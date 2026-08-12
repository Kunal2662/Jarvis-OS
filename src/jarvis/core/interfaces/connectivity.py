"""Connectivity Layer ports -- Milestone 12 Task Group B.

The seam a real device connector plugs into, the same "port + adapter"
shape :class:`~jarvis.core.interfaces.mcp.IMCPTransport` already uses
for MCP transports -- deliberately mirrored, not reinvented, down to
the closed-vocabulary-plus-factory-registry pattern
(:class:`~jarvis.core.connectivity.registry.ConnectorFactoryRegistry`).

**Ports only -- no protocol-specific code.** This module names the
vocabulary (:data:`CONNECTOR_TYPES`) and the shape every connector
implements; concrete connectors (Home Assistant, MQTT) are separate,
later phases of this same task group and plug in through
:meth:`~jarvis.core.connectivity.registry.ConnectorFactoryRegistry.register`
without this module changing.

**Why this is a new file, not an extension of `providers.py`'s
``ISmartHomeProvider``.** That Protocol (``get_connection_status`` /
``list_devices`` / ``set_device_state`` / ``get_recent_activity``,
each operating on ``dict[str, Any]``) is an M5-era API-Center
dashboard-card interface, sibling to ``IWeatherProvider`` /
``IFinanceProvider``. It predates Task Group A's real ``Device`` /
``Home`` domain entirely and was never touched by it -- extending it
here would mean two disconnected device models for the same feature.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

#: Connector identifiers this platform recognizes. Closed by design,
#: the same reasoning `TRANSPORT_TYPES` documents: a connector
#: identifier names a *wire protocol*, and a configuration author
#: selects one of these rather than inventing another --
#: `ConnectorFactoryRegistry.register` rejects anything outside this
#: set. Deliberately narrow to what this task group's approved phases
#: actually build (Home Assistant, MQTT) -- BLE, Matter, Thread,
#: Zigbee, Z-Wave and vendor-direct adapters are named in
#: `MASTER_ROADMAP.md`'s own Connectivity Layer feature list and
#: Future Expansion note, but adding their identifiers here without an
#: approved phase to implement them would name scope this task group
#: was not given.
CONNECTOR_TYPES: frozenset[str] = frozenset(
    {
        "home_assistant",
        "mqtt",
    }
)


class ConnectivityError(Exception):
    """Base for every Connectivity Layer failure. Mirrors `MCPError`'s
    role in the MCP platform -- one catchable base per subsystem."""


class ConnectorNotConnectedError(ConnectivityError):
    """Raised when an operation needs a live connection and there is
    none -- distinct from a connection that failed to establish."""


@dataclass(frozen=True, slots=True)
class DiscoveredDevice:
    """One device a connector's `discover()` found, in the connector's
    own vocabulary -- not yet a `Device` row.

    `ConnectivityService` is what turns this into a real
    `SmartHomeService.register_discovered_device()` call; a connector
    never touches the database directly, preserving Task Group A's own
    layering (a connector is a port adapter, not a repository client).
    """

    external_id: str
    name: str
    device_type: str = "other"
    manufacturer: str = ""
    model: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DeviceState:
    """A connector's own report of one device's current state --
    distinct from `Device.status` (Task Group A's domain lifecycle:
    discovered/paired/offline/...): this is the connector's raw
    reading (e.g. Home Assistant's own entity state string), which
    `ConnectivityService` interprets, not the connector."""

    external_id: str
    status: str
    attributes: dict[str, Any] = field(default_factory=dict)
    observed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class CommandResult:
    """The outcome of one `send_command()` call. `success=False` with
    a `detail` is a real, expected outcome (a device offline, a
    rejected command) -- not every failure is an exception."""

    external_id: str
    command: str
    success: bool
    detail: str = ""


@runtime_checkable
class IDeviceConnector(Protocol):
    """One connector, one live connection. A connector owns protocol
    framing and delivery only -- it never decides what a command
    *means* (that is a later M12 module's job, reached through
    `ConnectivityService.send_command`, the single chokepoint that
    module will gate for `safety_critical` devices)."""

    #: One of `CONNECTOR_TYPES`.
    connector_type: str

    @property
    def is_connected(self) -> bool: ...

    async def connect(self) -> None:
        """Establish the underlying channel. Idempotent -- connecting
        an already-connected connector is a no-op, never an error."""
        ...

    async def disconnect(self) -> None:
        """Tear the channel down. Idempotent, and safe to call on a
        connector that never connected."""
        ...

    async def discover(self) -> list[DiscoveredDevice]:
        """Every device this connector can currently see. Returns an
        empty list rather than raising when the bus is reachable but
        genuinely has nothing to report."""
        ...

    async def read_state(self, external_id: str) -> DeviceState:
        """Raises `ConnectorNotConnectedError` if called before
        `connect()`, and a connector-specific `ConnectivityError`
        subclass if `external_id` is not one this connector knows."""
        ...

    async def send_command(
        self, external_id: str, command: str, payload: dict[str, Any]
    ) -> CommandResult:
        """Never raises for a command the device itself rejects --
        that is `CommandResult.success=False`, not an exception. Raises
        only for a connector-level failure (not connected, malformed
        `external_id`)."""
        ...
