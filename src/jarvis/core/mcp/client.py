"""MCP Client Runtime -- Milestone 10.5 Task Group A, deliverable 3.

**Lifecycle only.** Connection management, handshake, capability
discovery, health and reconnect -- for *any* transport satisfying
:class:`~jarvis.core.interfaces.mcp.IMCPTransport`. No provider
implementations, no credential handling, no OAuth: those are M11's
scope, and nothing here presumes which transport it is driving.

Fault isolation follows the precedent
``core/plugins/registry.py`` set for plugins and
``services/search_service.py`` set for search sources: one connection
failing is that connection's own ``FAILED`` state, never an exception
propagating out of a batch operation over every connection.

Reconnect is deliberately caller-driven (:meth:`reconnect`) plus an
opt-in bounded retry inside :meth:`connect`, rather than a background
supervisor loop. M9's ``BackgroundTaskManager`` already owns "run this
repeatedly in the background", and adding a second, MCP-private
supervisor would be exactly the parallel runtime this milestone's own
scope note forbids.
"""

from __future__ import annotations

import asyncio
import enum
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from jarvis.core.events.events import (
    MCPCapabilitiesChangedEvent,
    MCPConnectionChangedEvent,
)
from jarvis.core.interfaces.mcp import MCPCapability, MCPError, MCPTransportError
from jarvis.core.interfaces.service import HealthStatus, ServiceStatus
from jarvis.core.logging.logger import get_logger
from jarvis.core.mcp.capabilities import MCPCapabilityRegistry
from jarvis.core.mcp.negotiation import (
    SUPPORTED_PROTOCOL_VERSIONS,
    NegotiationResult,
    negotiate,
)

if TYPE_CHECKING:
    from collections.abc import Collection

    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.interfaces.mcp import IMCPTransport

_logger = get_logger("jarvis.core.mcp.client")

DEFAULT_RECONNECT_ATTEMPTS = 3
DEFAULT_RECONNECT_BACKOFF_SECONDS = 0.5


class MCPConnectionState(enum.StrEnum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    FAILED = "failed"


@dataclass(slots=True)
class MCPConnection:
    """One peer connection's live state. Mutable by design -- the
    registry entry ``PluginRegistry._Entry`` is the same shape for the
    same reason: state transitions are recorded in place, not by
    rebuilding a frozen record on every tick."""

    server_id: str
    transport: IMCPTransport
    state: MCPConnectionState = MCPConnectionState.DISCONNECTED
    agreed_version: str = ""
    error: str = ""
    capabilities: MCPCapabilityRegistry = field(default_factory=MCPCapabilityRegistry)
    rejected: tuple[tuple[str, str], ...] = ()


class MCPClientRuntime:
    """JARVIS as an MCP consumer -- manages every outbound connection."""

    def __init__(
        self,
        *,
        event_bus: EventBus | None = None,
        client_id: str = "jarvis",
        reconnect_attempts: int = DEFAULT_RECONNECT_ATTEMPTS,
        reconnect_backoff_seconds: float = DEFAULT_RECONNECT_BACKOFF_SECONDS,
    ) -> None:
        self.client_id = client_id
        self._event_bus = event_bus
        self._reconnect_attempts = max(1, reconnect_attempts)
        self._backoff = max(0.0, reconnect_backoff_seconds)
        self._connections: dict[str, MCPConnection] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------
    def register_connection(self, server_id: str, transport: IMCPTransport) -> MCPConnection:
        """Records a peer without connecting to it -- discovery and
        connection are separate steps, so a configured-but-offline peer
        is still visible in :meth:`snapshot` rather than invisible until
        it happens to be reachable."""
        connection = MCPConnection(
            server_id=server_id,
            transport=transport,
            capabilities=MCPCapabilityRegistry(owner=server_id),
        )
        self._connections[server_id] = connection
        return connection

    def get(self, server_id: str) -> MCPConnection | None:
        return self._connections.get(server_id)

    @property
    def server_ids(self) -> tuple[str, ...]:
        return tuple(self._connections)

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------
    async def connect(
        self,
        server_id: str,
        *,
        granted_scopes: Collection[str] = (),
        retry: bool = False,
    ) -> bool:
        """Connect, handshake, then discover -- returns success rather
        than raising, so one unreachable peer never aborts a batch.

        *granted_scopes* comes from the caller's own permission
        resolution; negotiation filters the peer's offered capabilities
        against it (least-privilege: an ungranted capability is dropped,
        and the connection still succeeds with the remainder).
        """
        connection = self._connections.get(server_id)
        if connection is None:
            raise MCPError(f"MCP server {server_id!r} is not registered.")

        attempts = self._reconnect_attempts if retry else 1
        last_error = ""
        for attempt in range(1, attempts + 1):
            await self._set_state(connection, MCPConnectionState.CONNECTING)
            try:
                await connection.transport.connect()
                agreed = await self._handshake(connection)
                await self._discover(connection, granted_scopes=granted_scopes, agreed=agreed)
            except (MCPError, MCPTransportError, OSError) as err:
                last_error = str(err)
                _logger.warning(
                    "MCP connect to {!r} failed (attempt {}/{}): {}",
                    server_id,
                    attempt,
                    attempts,
                    err,
                )
                await self._safe_disconnect(connection)
                if attempt < attempts and self._backoff:
                    await asyncio.sleep(self._backoff * attempt)
                continue
            else:
                connection.error = ""
                await self._set_state(connection, MCPConnectionState.CONNECTED)
                return True

        connection.error = last_error
        await self._set_state(connection, MCPConnectionState.FAILED, detail=last_error)
        return False

    async def disconnect(self, server_id: str) -> bool:
        connection = self._connections.get(server_id)
        if connection is None:
            return False
        await self._safe_disconnect(connection)
        # A stale capability list is worse than an empty one -- callers
        # would otherwise negotiate against capabilities nothing serves.
        connection.capabilities.clear()
        connection.agreed_version = ""
        await self._set_state(connection, MCPConnectionState.DISCONNECTED)
        return True

    async def reconnect(self, server_id: str, *, granted_scopes: Collection[str] = ()) -> bool:
        """Disconnect-then-connect with the bounded retry enabled."""
        await self.disconnect(server_id)
        return await self.connect(server_id, granted_scopes=granted_scopes, retry=True)

    async def disconnect_all(self) -> None:
        for server_id in tuple(self._connections):
            await self.disconnect(server_id)

    # ------------------------------------------------------------------
    # Handshake + discovery
    # ------------------------------------------------------------------
    async def _handshake(self, connection: MCPConnection) -> str:
        response = await connection.transport.request(
            "initialize",
            {
                "client_id": self.client_id,
                "protocol_versions": list(SUPPORTED_PROTOCOL_VERSIONS),
            },
        )
        agreed = str(response.get("agreed_version") or "")
        if not agreed:
            raise MCPError(
                str(response.get("failure_reason") or "Handshake failed: no agreed version.")
            )
        connection.agreed_version = agreed
        return agreed

    async def _discover(
        self,
        connection: MCPConnection,
        *,
        granted_scopes: Collection[str],
        agreed: str,
    ) -> None:
        response = await connection.transport.request("capabilities/list", {})
        offered = [_capability_from_payload(raw) for raw in response.get("capabilities") or []]

        result = negotiate(
            offered,
            remote_versions=[agreed],
            granted_scopes=granted_scopes,
            local_versions=[agreed],
        )
        connection.capabilities.clear()
        connection.capabilities.register_all(result.capabilities, replace=True)
        connection.rejected = result.rejected
        await self._publish_capabilities_changed(connection)

    async def negotiated(
        self, server_id: str, *, granted_scopes: Collection[str] = ()
    ) -> NegotiationResult:
        """Re-run negotiation against an already-discovered peer without
        a round trip -- what a permission grant/revoke calls to refresh
        which capabilities are usable."""
        connection = self._connections.get(server_id)
        if connection is None:
            raise MCPError(f"MCP server {server_id!r} is not registered.")
        return negotiate(
            connection.capabilities.list_capabilities(),
            remote_versions=[connection.agreed_version] if connection.agreed_version else [],
            granted_scopes=granted_scopes,
            local_versions=(
                [connection.agreed_version]
                if connection.agreed_version
                else list(SUPPORTED_PROTOCOL_VERSIONS)
            ),
        )

    # ------------------------------------------------------------------
    # Invocation
    # ------------------------------------------------------------------
    async def call(
        self, server_id: str, capability_name: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        connection = self._connections.get(server_id)
        if connection is None:
            raise MCPError(f"MCP server {server_id!r} is not registered.")
        if connection.state is not MCPConnectionState.CONNECTED:
            raise MCPError(
                f"MCP server {server_id!r} is not connected (state: {connection.state})."
            )
        if not connection.capabilities.has(capability_name):
            raise MCPError(
                f"Capability {capability_name!r} was not negotiated for {server_id!r}. "
                f"Available: {list(connection.capabilities.names) or 'none'}."
            )
        return await connection.transport.request(
            "capabilities/call", {"name": capability_name, "arguments": arguments or {}}
        )

    # ------------------------------------------------------------------
    # Health / status (IService-shaped)
    # ------------------------------------------------------------------
    async def health(self) -> HealthStatus:
        failed = [
            c.server_id for c in self._connections.values() if c.state is MCPConnectionState.FAILED
        ]
        if failed:
            return HealthStatus(healthy=False, detail=f"Failed MCP connections: {failed}")
        return HealthStatus(healthy=True)

    async def status(self) -> ServiceStatus:
        connected = [
            c.server_id
            for c in self._connections.values()
            if c.state is MCPConnectionState.CONNECTED
        ]
        return ServiceStatus(
            name="mcp-client",
            state="running" if connected else "idle",
            detail={
                "client_id": self.client_id,
                "connection_count": len(self._connections),
                "connected": connected,
                "connections": list(self.snapshot()),
            },
        )

    def snapshot(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            {
                "server_id": c.server_id,
                "state": c.state.value,
                "transport": c.transport.transport_type,
                "agreed_version": c.agreed_version,
                "error": c.error,
                "capability_count": len(c.capabilities),
                "capabilities": list(c.capabilities.names),
                "rejected": [{"name": n, "reason": r} for n, r in c.rejected],
            }
            for c in self._connections.values()
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    async def _safe_disconnect(self, connection: MCPConnection) -> None:
        try:
            await connection.transport.disconnect()
        except Exception as err:  # a failed teardown must not mask the real error
            _logger.warning(
                "MCP transport disconnect for {!r} failed: {}", connection.server_id, err
            )

    async def _set_state(
        self, connection: MCPConnection, state: MCPConnectionState, *, detail: str = ""
    ) -> None:
        connection.state = state
        if self._event_bus is None:
            return
        await self._event_bus.publish(
            MCPConnectionChangedEvent(
                server_id=connection.server_id, state=state.value, detail=detail
            )
        )

    async def _publish_capabilities_changed(self, connection: MCPConnection) -> None:
        if self._event_bus is None:
            return
        await self._event_bus.publish(
            MCPCapabilitiesChangedEvent(
                owner=connection.server_id, count=len(connection.capabilities)
            )
        )


def _capability_from_payload(raw: dict[str, Any]) -> MCPCapability:
    """Rebuilds a capability from its wire form. Unknown fields are
    ignored rather than rejected -- forward compatibility with a newer
    peer is the point of negotiating a version at all."""
    return MCPCapability(
        name=str(raw.get("name") or ""),
        version=str(raw.get("version") or "1.0.0"),
        kind=str(raw.get("kind") or "tool"),
        description=str(raw.get("description") or ""),
        permissions=tuple(raw.get("permissions") or ()),
        metadata=dict(raw.get("metadata") or {}),
    )
