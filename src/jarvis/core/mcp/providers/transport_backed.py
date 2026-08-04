"""The generic provider implementation -- Milestone 10.5 Task Group C,
deliverable 1.

:class:`TransportBackedProvider` satisfies
:class:`~jarvis.core.interfaces.mcp.IMCPProvider` for the entire
"point at an MCP server with this transport config" case, which is
every integration M11 currently anticipates. A future provider only
needs its own class if it has genuinely different behaviour (a token
refresh loop, say) -- otherwise it is metadata plus configuration, and
this class runs it.

**It owns no connection logic.** Connecting, the handshake, capability
discovery, negotiation and bounded-retry reconnect all belong to Task
Group A's ``MCPClientRuntime``; this class delegates to it. Building
the transport belongs to Task Group B's ``TransportFactoryRegistry``;
this class delegates to that too. What remains here is genuinely its
own: turning a declarative provider into the two calls those
collaborators need, in the right order, and reporting the result.

Satisfies the Protocol structurally, with no base class -- composition
over inheritance, as every other adapter in this codebase does.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from jarvis.core.interfaces.service import HealthStatus, ServiceStatus
from jarvis.core.logging.logger import get_logger
from jarvis.core.mcp.providers.metadata import MCPProviderError

if TYPE_CHECKING:
    from collections.abc import Collection

    from jarvis.core.mcp.client import MCPClientRuntime
    from jarvis.core.mcp.providers.metadata import ProviderConfig, ProviderMetadata
    from jarvis.core.mcp.transport import TransportFactoryRegistry

_logger = get_logger("jarvis.core.mcp.providers.transport_backed")


class TransportBackedProvider:
    """A provider defined entirely by its metadata and configuration."""

    def __init__(
        self,
        provider_id: str,
        metadata: ProviderMetadata,
        config: ProviderConfig,
        *,
        client_runtime: MCPClientRuntime,
        transport_registry: TransportFactoryRegistry,
    ) -> None:
        self.provider_id = provider_id
        self._metadata = metadata
        self._config = config
        self._client = client_runtime
        self._transports = transport_registry
        self._initialized = False
        self._granted_scopes: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def initialize(self) -> None:
        """Validate and build the transport, then register it as a
        connection -- but do **not** open it. Registering without
        connecting is what keeps a configured-but-offline provider
        visible rather than invisible until it happens to be reachable,
        the same property ``MCPClientRuntime.register_connection``
        already gives."""
        if self._initialized:
            return

        transport_type = self._config.resolved_transport(self._metadata)
        if not self._transports.supports(transport_type):
            raise MCPProviderError(
                f"Provider {self.provider_id!r} needs transport {transport_type!r}, "
                f"which is not registered. Registered: "
                f"{list(self._transports.registered_types) or 'none'}."
            )

        transport = self._transports.create(transport_type, dict(self._config.options))
        self._client.register_connection(self.provider_id, transport)
        self._initialized = True
        _logger.info(
            "MCP provider {!r} initialized on transport {!r}.", self.provider_id, transport_type
        )

    async def start(self) -> None:
        """Connect through the client runtime, honouring this provider's
        reconnect policy. Raises on failure so the manager can record a
        ``FAILED`` state with the reason."""
        if not self._initialized:
            await self.initialize()

        connected = await self._client.connect(
            self.provider_id,
            granted_scopes=self._granted_scopes,
            retry=self._config.reconnect.enabled,
        )
        if not connected:
            connection = self._client.get(self.provider_id)
            reason = connection.error if connection is not None else "unknown error"
            raise MCPProviderError(f"Provider {self.provider_id!r} failed to connect: {reason}")

    async def stop(self) -> None:
        await self._client.disconnect(self.provider_id)

    async def suspend(self) -> None:
        """Drop the connection, keep the registration. The transport
        object survives, so :meth:`resume` needs no re-initialization."""
        await self._client.disconnect(self.provider_id)

    async def resume(self) -> None:
        await self.start()

    async def shutdown(self) -> None:
        await self.stop()
        self._initialized = False

    # ------------------------------------------------------------------
    # Permissions
    # ------------------------------------------------------------------
    def set_granted_scopes(self, scopes: Collection[str]) -> None:
        """The scopes negotiation should filter against on the next
        connect. Resolved by the manager from the shared
        ``PermissionModel`` -- this class never reads a permission store
        itself, so there is no second permission system here."""
        self._granted_scopes = set(scopes)

    @property
    def granted_scopes(self) -> frozenset[str]:
        return frozenset(self._granted_scopes)

    # ------------------------------------------------------------------
    # Health / status
    # ------------------------------------------------------------------
    async def health(self) -> HealthStatus:
        connection = self._client.get(self.provider_id)
        if connection is None:
            return HealthStatus(healthy=False, detail="Provider is not initialized.")

        from jarvis.core.mcp.client import MCPConnectionState

        if connection.state is MCPConnectionState.CONNECTED:
            return HealthStatus(healthy=True)
        return HealthStatus(
            healthy=False,
            detail=connection.error or f"Connection state: {connection.state.value}",
        )

    async def status(self) -> ServiceStatus:
        connection = self._client.get(self.provider_id)
        detail: dict[str, Any] = {
            "transport": self._config.resolved_transport(self._metadata),
            "initialized": self._initialized,
            "granted_scopes": sorted(self._granted_scopes),
            "required_permissions": list(self._metadata.required_permissions),
        }
        if connection is not None:
            detail |= {
                "agreed_version": connection.agreed_version,
                "capabilities": list(connection.capabilities.names),
                "rejected": [{"name": n, "reason": r} for n, r in connection.rejected],
                "error": connection.error,
            }
        return ServiceStatus(
            name=f"mcp-provider:{self.provider_id}",
            state=connection.state.value if connection is not None else "uninitialized",
            detail=detail,
        )
