"""MCP diagnostics -- Milestone 10.5 Task Group E, deliverable 5.

One read-only aggregator over every MCP subsystem, for the CLI, the
Developer Platform Tools, and anyone debugging a provider that will not
connect.

**Collects, never computes.** Every number here is already owned by the
subsystem that produced it -- capability counts from the capability
registry, connection state from the client runtime, health from
``MCPProviderManager.collect_health``, credential status from
``MCPAuthManager``. This class calls them and merges the results. It
holds no state, caches nothing, and is safe to call at any time,
because a diagnostic that changes what it observes is not a diagnostic.

**Read-only, by construction.** Nothing here connects, authenticates,
starts, or mutates. ``inspect_provider`` on a broken provider reports
why it is broken; it does not try to fix it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from jarvis.core.mcp.negotiation import PROTOCOL_VERSION, SUPPORTED_PROTOCOL_VERSIONS
from jarvis.core.mcp.sdk.validation import validate_registry_consistency

if TYPE_CHECKING:
    from jarvis.core.mcp.auth.manager import MCPAuthManager
    from jarvis.core.mcp.auth.strategies import AuthStrategyRegistry
    from jarvis.core.mcp.client import MCPClientRuntime
    from jarvis.core.mcp.heartbeat import MCPHeartbeatMonitor
    from jarvis.core.mcp.providers.manager import MCPProviderManager
    from jarvis.core.mcp.server import MCPServerRuntime
    from jarvis.core.mcp.transport import TransportFactoryRegistry


class MCPDiagnostics:
    """Aggregated, read-only inspection of the whole MCP platform."""

    def __init__(
        self,
        *,
        server: MCPServerRuntime,
        client: MCPClientRuntime,
        transports: TransportFactoryRegistry,
        provider_manager: MCPProviderManager,
        auth_manager: MCPAuthManager,
        auth_strategies: AuthStrategyRegistry,
        heartbeat: MCPHeartbeatMonitor | None = None,
    ) -> None:
        self._server = server
        self._client = client
        self._transports = transports
        self._providers = provider_manager
        self._auth = auth_manager
        self._strategies = auth_strategies
        self._heartbeat = heartbeat

    # ------------------------------------------------------------------
    # Focused inspections
    # ------------------------------------------------------------------
    async def runtime(self) -> dict[str, Any]:
        server_status = await self._server.status()
        client_status = await self._client.status()
        return {
            "protocol_version": PROTOCOL_VERSION,
            "supported_protocol_versions": list(SUPPORTED_PROTOCOL_VERSIONS),
            "server": {
                "id": self._server.server_id,
                "running": self._server.is_running,
                "state": server_status.state,
                "capability_count": len(self._server.capabilities),
                "methods": server_status.detail.get("methods", []),
            },
            "client": {
                "id": self._client.client_id,
                "state": client_status.state,
                "connection_count": len(self._client.server_ids),
            },
            "heartbeat_running": bool(self._heartbeat and self._heartbeat.is_running),
        }

    def capabilities(self) -> tuple[dict[str, Any], ...]:
        """Capabilities JARVIS exposes. Peer-offered ones are reported
        per connection instead, so one peer's list can never be mistaken
        for JARVIS's own."""
        return self._server.capabilities.snapshot()

    def transports(self) -> tuple[dict[str, Any], ...]:
        return self._transports.describe_all()

    def connections(self) -> tuple[dict[str, Any], ...]:
        return self._client.snapshot()

    def providers(self) -> tuple[dict[str, Any], ...]:
        return self._providers.registry.snapshot()

    def auth(self) -> tuple[dict[str, Any], ...]:
        """Credential metadata only -- never a token value."""
        return self._auth.public_snapshot()

    def auth_methods(self) -> tuple[dict[str, Any], ...]:
        return self._strategies.describe()

    async def inspect_provider(self, provider_id: str) -> dict[str, Any] | None:
        """Everything known about one provider, across all four
        subsystems, in one payload -- registration, live connection,
        authentication and health. Returns ``None`` when the id is not
        registered, rather than raising, so a CLI can report it
        cleanly."""
        if not self._providers.registry.has(provider_id):
            return None

        status = await self._providers.status(provider_id)
        connection = next(
            (c for c in self._client.snapshot() if c["server_id"] == provider_id), None
        )
        auth = self._auth.status(provider_id) if provider_id in self._auth.provider_ids else None
        return {
            "provider": status,
            "connection": connection,
            "authentication": auth,
            "health": await self._providers.health(provider_id),
        }

    def inspect_capability(self, name: str) -> dict[str, Any] | None:
        """One capability's declaration plus who offers it -- JARVIS
        itself and/or any connected peer."""
        exposed = self._server.capabilities.get(name)
        offered_by = [
            connection["server_id"]
            for connection in self._client.snapshot()
            if name in connection.get("capabilities", [])
        ]
        if exposed is None and not offered_by:
            return None
        return {
            "name": name,
            "exposed_by_jarvis": exposed is not None,
            "declaration": (
                {
                    "version": exposed.version,
                    "kind": exposed.kind,
                    "description": exposed.description,
                    "permissions": list(exposed.permissions),
                }
                if exposed is not None
                else None
            ),
            "offered_by_peers": offered_by,
        }

    # ------------------------------------------------------------------
    # Whole-platform
    # ------------------------------------------------------------------
    def validate(self) -> dict[str, Any]:
        """Cross-subsystem consistency -- the check no single registry
        can make about itself."""
        return validate_registry_consistency(
            provider_registry=self._providers.registry,
            transport_registry=self._transports,
            auth_manager=self._auth,
            strategies=self._strategies,
        ).as_dict()

    async def report(self) -> dict[str, Any]:
        """The full picture, as one serializable payload."""
        return {
            "runtime": await self.runtime(),
            "capabilities": list(self.capabilities()),
            "transports": list(self.transports()),
            "connections": list(self.connections()),
            "providers": list(self.providers()),
            "authentication": list(self.auth()),
            "auth_methods": list(self.auth_methods()),
            "provider_health": await self._providers.collect_health(),
            "auth_health": await self._auth.collect_health(),
            "validation": self.validate(),
        }

    async def summary(self) -> dict[str, Any]:
        """The compact counts a CLI status line shows."""
        validation = self.validate()
        return {
            "server_running": self._server.is_running,
            "capabilities": len(self._server.capabilities),
            "registered_transports": len(self._transports.registered_types),
            "providers": len(self._providers.registry),
            "connections": len(self._client.server_ids),
            "authenticated": len((await self._auth.collect_health())["authenticated"]),
            "validation_ok": validation["ok"],
            "validation_errors": validation["error_count"],
            "validation_warnings": validation["warning_count"],
        }
