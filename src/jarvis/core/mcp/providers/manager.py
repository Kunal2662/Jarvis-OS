"""Provider Manager -- Milestone 10.5 Task Group C, deliverables 3, 7 and 8.

Owns the provider *lifecycle* -- install, initialize, connect,
disconnect, suspend, resume, shutdown -- and publishes every transition
on the existing ``EventBus``.

**It is not a connection manager.** Every connect/disconnect delegates
to the provider, which delegates to Task Group A's ``MCPClientRuntime``.
This class decides *when* a provider moves and records *that* it moved;
it never opens a socket, spawns a process, or holds a transport. That
separation is what keeps the framework from becoming the second
connection manager this task group's rules forbid.

**It is not a health subsystem.** :meth:`collect_health` returns a
plain dict for M9's ``HealthMonitor.register_collector`` -- the same
extension point Task Groups A and B already ride. There is one health
channel.

**It is not a permission system.** :meth:`resolve_scopes` reads the
shared ``PermissionModel``, namespaced with the same ``mcp:`` prefix
Task Group A established, and hands the result to the provider. No
grants are stored here.

Fault isolation matches ``PluginRegistry.discover_and_load_all``: a
batch operation never lets one provider's failure stop another's -- the
failure lands as that provider's own ``FAILED`` state with a reason.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from jarvis.core.events.events import MCPProviderStateChangedEvent
from jarvis.core.logging.logger import get_logger
from jarvis.core.mcp.providers.metadata import (
    MCPProviderError,
    ProviderConfig,
    ProviderMetadata,
    ProviderState,
)
from jarvis.core.mcp.providers.transport_backed import TransportBackedProvider
from jarvis.core.mcp.server import principal_for

if TYPE_CHECKING:
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.mcp.client import MCPClientRuntime
    from jarvis.core.mcp.providers.registry import MCPProviderRegistry, ProviderRecord
    from jarvis.core.mcp.transport import TransportFactoryRegistry
    from jarvis.core.plugins.permissions import PermissionModel

_logger = get_logger("jarvis.core.mcp.providers.manager")


class MCPProviderManager:
    """Drives registered providers through their lifecycle."""

    def __init__(
        self,
        registry: MCPProviderRegistry,
        *,
        client_runtime: MCPClientRuntime,
        transport_registry: TransportFactoryRegistry,
        permission_model: PermissionModel,
        event_bus: EventBus | None = None,
    ) -> None:
        self._registry = registry
        self._client = client_runtime
        self._transports = transport_registry
        self._permissions = permission_model
        self._event_bus = event_bus

    @property
    def registry(self) -> MCPProviderRegistry:
        return self._registry

    # ------------------------------------------------------------------
    # Install
    # ------------------------------------------------------------------
    async def install(
        self,
        provider_id: str,
        metadata: ProviderMetadata,
        config: ProviderConfig | None = None,
        *,
        replace: bool = False,
    ) -> ProviderRecord:
        """Register a provider and declare its permission requests.

        Declaring moves each requested scope to ``PENDING`` in the
        shared store unless already decided -- identical semantics to
        ``PluginRegistry.load_one``'s own ``declare`` call, and to Task
        Group A's ``MCPServerRuntime.declare_for``. Installing never
        grants anything.
        """
        record = self._registry.register(
            provider_id, metadata, config, provider=None, replace=replace
        )
        record.provider = TransportBackedProvider(
            provider_id,
            record.metadata,
            record.config,
            client_runtime=self._client,
            transport_registry=self._transports,
        )
        if metadata.required_permissions:
            self._permissions.declare(
                principal_for(provider_id), sorted(metadata.required_permissions)
            )
        await self._publish(record, "registered")
        return record

    async def remove(self, provider_id: str) -> bool:
        """Shut the provider down, then deregister it. Removing a
        running provider without stopping it first would leak its
        transport, so the order is not optional."""
        record = self._registry.get(provider_id)
        if record is None:
            return False
        await self._safe(record, "shutdown")
        removed = self._registry.unregister(provider_id)
        if removed:
            record.state = ProviderState.REMOVED
            await self._publish(record, "removed")
        return removed

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def initialize(self, provider_id: str) -> bool:
        record = self._registry.require(provider_id)
        if not await self._safe(record, "initialize"):
            return False
        record.state = ProviderState.INITIALIZED
        record.error = ""
        await self._publish(record, "initialized")
        return True

    async def connect(self, provider_id: str) -> bool:
        """Resolve this provider's granted scopes, then connect.

        Scopes are resolved fresh on every connect rather than cached at
        install time, so a grant made after installation takes effect on
        the next connect without re-registering the provider.
        """
        record = self._registry.require(provider_id)
        if not record.config.enabled:
            raise MCPProviderError(f"Provider {provider_id!r} is disabled.")

        if record.state is ProviderState.REGISTERED and not await self.initialize(provider_id):
            return False

        provider = record.provider
        if provider is not None and hasattr(provider, "set_granted_scopes"):
            provider.set_granted_scopes(self.resolve_scopes(provider_id))

        record.state = ProviderState.CONNECTING
        if not await self._safe(record, "start"):
            return False

        record.state = ProviderState.CONNECTED
        record.error = ""
        await self._publish(record, "connected")
        return True

    async def disconnect(self, provider_id: str) -> bool:
        record = self._registry.require(provider_id)
        if not await self._safe(record, "stop"):
            return False
        record.state = ProviderState.DISCONNECTED
        await self._publish(record, "disconnected")
        return True

    async def suspend(self, provider_id: str) -> bool:
        """Park a provider without deregistering it. Idempotent: an
        already-suspended provider stays suspended rather than
        erroring, since the caller's intent is already satisfied."""
        record = self._registry.require(provider_id)
        if record.state is ProviderState.SUSPENDED:
            return True
        if not await self._safe(record, "suspend"):
            return False
        record.state = ProviderState.SUSPENDED
        await self._publish(record, "suspended")
        return True

    async def resume(self, provider_id: str) -> bool:
        record = self._registry.require(provider_id)
        if record.state is not ProviderState.SUSPENDED:
            raise MCPProviderError(
                f"Provider {provider_id!r} is not suspended (state: {record.state.value})."
            )

        provider = record.provider
        if provider is not None and hasattr(provider, "set_granted_scopes"):
            provider.set_granted_scopes(self.resolve_scopes(provider_id))

        if not await self._safe(record, "resume"):
            return False
        # 'resumed' is the transition; 'connected' is where it lands.
        record.state = ProviderState.CONNECTED
        record.error = ""
        await self._publish(record, "resumed")
        return True

    async def shutdown(self, provider_id: str) -> bool:
        record = self._registry.require(provider_id)
        if not await self._safe(record, "shutdown"):
            return False
        record.state = ProviderState.DISCONNECTED
        await self._publish(record, "disconnected")
        return True

    # ------------------------------------------------------------------
    # Batch operations -- fault-isolated, per PluginRegistry's precedent
    # ------------------------------------------------------------------
    async def connect_all(self) -> dict[str, bool]:
        """Connect every enabled provider. One failure never stops the
        rest; the result maps each id to whether it connected."""
        results: dict[str, bool] = {}
        for record in self._registry.discover(enabled_only=True):
            try:
                results[record.provider_id] = await self.connect(record.provider_id)
            except MCPProviderError as err:
                _logger.warning("Provider {!r} could not connect: {}", record.provider_id, err)
                results[record.provider_id] = False
        return results

    async def disconnect_all(self) -> None:
        for record in self._registry.enumerate():
            if record.state in (ProviderState.CONNECTED, ProviderState.CONNECTING):
                await self._safe(record, "stop")
                record.state = ProviderState.DISCONNECTED

    # ------------------------------------------------------------------
    # Permissions (resolved from the shared model, never stored here)
    # ------------------------------------------------------------------
    def resolve_scopes(self, provider_id: str) -> set[str]:
        record = self._registry.require(provider_id)
        principal = principal_for(provider_id)
        return {
            scope
            for scope in record.metadata.required_permissions
            if self._permissions.is_granted(principal, scope)
        }

    def pending_scopes(self, provider_id: str) -> tuple[str, ...]:
        """Requested-but-not-granted scopes -- what an approval surface
        would show for this provider."""
        record = self._registry.require(provider_id)
        granted = self.resolve_scopes(provider_id)
        return tuple(s for s in record.metadata.required_permissions if s not in granted)

    # ------------------------------------------------------------------
    # Health (one channel -- M9's HealthMonitor collector)
    # ------------------------------------------------------------------
    async def health(self, provider_id: str) -> dict[str, Any]:
        record = self._registry.require(provider_id)
        provider = record.provider
        healthy, detail = False, "Provider has no implementation bound."
        if provider is not None:
            status = await provider.health()
            healthy, detail = status.healthy, status.detail
        return {
            "provider_id": provider_id,
            "state": record.state.value,
            "healthy": healthy,
            "detail": detail or record.error,
        }

    async def collect_health(self) -> dict[str, Any]:
        """The payload M9's ``HealthMonitor`` merges under its own key."""
        providers = [await self.health(r.provider_id) for r in self._registry.enumerate()]
        unhealthy = [p["provider_id"] for p in providers if not p["healthy"]]
        return {
            "count": len(providers),
            "connected": [
                r.provider_id for r in self._registry.discover(state=ProviderState.CONNECTED)
            ],
            "unhealthy": unhealthy,
            "providers": providers,
        }

    async def status(self, provider_id: str) -> dict[str, Any]:
        record = self._registry.require(provider_id)
        payload = record.as_dict()
        if record.provider is not None:
            service_status = await record.provider.status()
            payload["detail"] = service_status.detail
        payload["pending_permissions"] = list(self.pending_scopes(provider_id))
        payload["granted_permissions"] = sorted(self.resolve_scopes(provider_id))
        return payload

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    async def _safe(self, record: ProviderRecord, method: str) -> bool:
        """Runs one lifecycle method, converting any failure into this
        provider's own ``FAILED`` state plus a published event -- never
        an exception escaping into a batch operation."""
        provider = record.provider
        if provider is None:
            record.state = ProviderState.FAILED
            record.error = "Provider has no implementation bound."
            await self._publish(record, "failed")
            return False

        try:
            await getattr(provider, method)()
        except Exception as err:
            record.state = ProviderState.FAILED
            record.error = str(err)
            _logger.warning("Provider {!r} {}() failed: {}", record.provider_id, method, err)
            await self._publish(record, "failed")
            return False
        return True

    async def _publish(self, record: ProviderRecord, action: str) -> None:
        if self._event_bus is None:
            return
        await self._event_bus.publish(
            MCPProviderStateChangedEvent(
                provider_id=record.provider_id,
                action=action,
                state=record.state.value,
                detail=record.error,
            )
        )
