"""MCP Server Runtime -- Milestone 10.5 Task Group A, deliverables 4 and 6.

Exposes JARVIS's own capabilities to MCP clients: its own
:class:`~jarvis.core.mcp.capabilities.MCPCapabilityRegistry`, permission
enforcement on every invocation, and a lifecycle
(``start``/``stop``/``health``/``status``) matching
``core/interfaces/service.py``'s ``IService`` shape.

**One permission system, not two.** Enforcement delegates to M9's
existing :class:`~jarvis.core.plugins.permissions.PermissionModel` --
the same store, the same persisted grants, the same audit log, the same
``PENDING``-until-explicitly-granted default. MCP principals are
namespaced ``mcp:<client_id>`` so an MCP client and a plugin can never
collide on one identity, while both remain visible in the single
``pending()`` queue a future approval surface reads. No new permission
vocabulary is introduced: capabilities declare scopes from
``core/plugins/sdk.py``'s ``PERMISSION_SCOPES``.

**Handler registration, not a hardcoded method table.** ``initialize``,
``capabilities/list`` and ``capabilities/call`` are the three protocol
methods Task Group A defines; a later task group adds a method by
calling :meth:`register_method`, without editing the dispatch here.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from jarvis.core.events.events import (
    MCPCapabilitiesChangedEvent,
    MCPPermissionDeniedEvent,
)
from jarvis.core.interfaces.mcp import MCPError
from jarvis.core.interfaces.service import HealthStatus, ServiceStatus
from jarvis.core.logging.logger import get_logger
from jarvis.core.mcp.capabilities import MCPCapabilityRegistry
from jarvis.core.mcp.negotiation import (
    PROTOCOL_VERSION,
    SUPPORTED_PROTOCOL_VERSIONS,
    negotiate_version,
)

if TYPE_CHECKING:
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.interfaces.mcp import MCPCapability
    from jarvis.core.plugins.permissions import PermissionModel

_logger = get_logger("jarvis.core.mcp.server")

#: Prefix that namespaces an MCP principal inside the shared
#: ``PermissionModel`` store, keeping MCP client ids and plugin ids in
#: separate identity spaces without a second store.
MCP_PRINCIPAL_PREFIX = "mcp:"

MethodHandler = Callable[[dict[str, Any], str], Awaitable[dict[str, Any]]]


def principal_for(client_id: str) -> str:
    """The ``PermissionModel`` identity for an MCP peer."""
    return f"{MCP_PRINCIPAL_PREFIX}{client_id}"


class MCPServerRuntime:
    """JARVIS as an MCP provider."""

    def __init__(
        self,
        *,
        permission_model: PermissionModel,
        event_bus: EventBus | None = None,
        server_id: str = "jarvis",
    ) -> None:
        self.server_id = server_id
        self._permission_model = permission_model
        self._event_bus = event_bus
        self._capabilities = MCPCapabilityRegistry(owner=server_id)
        self._methods: dict[str, MethodHandler] = {}
        self._invokers: dict[str, Callable[[dict[str, Any]], Awaitable[Any]]] = {}
        self._running = False
        self._register_builtin_methods()

    # ------------------------------------------------------------------
    # Capability exposure
    # ------------------------------------------------------------------
    @property
    def capabilities(self) -> MCPCapabilityRegistry:
        return self._capabilities

    async def expose(
        self,
        capability: MCPCapability,
        invoker: Callable[[dict[str, Any]], Awaitable[Any]] | None = None,
        *,
        replace: bool = False,
    ) -> None:
        """Registers *capability* and, optionally, the coroutine that
        actually performs it.

        A capability with no *invoker* is discoverable but not callable
        -- :meth:`invoke` reports that honestly rather than returning a
        fabricated result, per the project's no-simulated-functionality
        rule.
        """
        self._capabilities.register(capability, replace=replace)
        if invoker is not None:
            self._invokers[capability.name] = invoker
        await self._publish_capabilities_changed()

    async def revoke(self, name: str) -> bool:
        removed = self._capabilities.unregister(name)
        self._invokers.pop(name, None)
        if removed:
            await self._publish_capabilities_changed()
        return removed

    # ------------------------------------------------------------------
    # Permission enforcement
    # ------------------------------------------------------------------
    def declare_for(self, client_id: str, capability_names: list[str] | None = None) -> None:
        """Declares the scopes *client_id* would need, moving each to
        ``PENDING`` in the shared store unless already decided.

        Declaring is never granting -- identical semantics to
        ``PluginRegistry.load_one``'s own ``declare`` call.
        """
        names = capability_names if capability_names is not None else list(self._capabilities.names)
        scopes: set[str] = set()
        for name in names:
            capability = self._capabilities.get(name)
            if capability is not None:
                scopes.update(capability.permissions)
        if scopes:
            self._permission_model.declare(principal_for(client_id), sorted(scopes))

    def granted_scopes(self, client_id: str) -> set[str]:
        """Every scope currently granted to *client_id*, resolved across
        all exposed capabilities -- the input
        ``negotiation.negotiate()`` takes."""
        principal = principal_for(client_id)
        declared = {
            scope
            for capability in self._capabilities.list_capabilities()
            for scope in capability.permissions
        }
        return {scope for scope in declared if self._permission_model.is_granted(principal, scope)}

    async def check_permitted(self, client_id: str, capability_name: str) -> tuple[bool, str]:
        """Whether *client_id* may invoke *capability_name*, and why not.

        Publishes :class:`MCPPermissionDeniedEvent` on refusal so a
        denial is observable over the runtime WebSocket relay rather
        than only in a log line.
        """
        capability = self._capabilities.get(capability_name)
        if capability is None:
            return False, f"Unknown capability {capability_name!r}."

        principal = principal_for(client_id)
        for scope in capability.permissions:
            if not self._permission_model.is_granted(principal, scope):
                await self._publish_permission_denied(principal, capability_name, scope)
                return False, f"Permission {scope!r} is not granted for {principal!r}."
        return True, ""

    # ------------------------------------------------------------------
    # Invocation
    # ------------------------------------------------------------------
    async def invoke(
        self, capability_name: str, params: dict[str, Any], *, client_id: str
    ) -> dict[str, Any]:
        """Permission-gated capability invocation."""
        permitted, reason = await self.check_permitted(client_id, capability_name)
        if not permitted:
            raise MCPError(reason)

        invoker = self._invokers.get(capability_name)
        if invoker is None:
            raise MCPError(
                f"Capability {capability_name!r} is registered but has no invoker bound; "
                "it is discoverable, not callable."
            )
        return {"result": await invoker(params)}

    # ------------------------------------------------------------------
    # Protocol dispatch
    # ------------------------------------------------------------------
    def register_method(self, method: str, handler: MethodHandler) -> None:
        """Adds a protocol method. A later task group extends the
        protocol surface here rather than by editing this class."""
        self._methods[method] = handler

    async def handle_request(
        self, method: str, params: dict[str, Any], *, client_id: str
    ) -> dict[str, Any]:
        """One JSON-RPC round trip, from a transport's perspective."""
        if not self._running:
            raise MCPError(f"Cannot handle {method!r}: MCP server runtime is not running.")
        handler = self._methods.get(method)
        if handler is None:
            raise MCPError(f"Unknown MCP method {method!r}.")
        return await handler(params, client_id)

    def _register_builtin_methods(self) -> None:
        self.register_method("initialize", self._handle_initialize)
        self.register_method("capabilities/list", self._handle_list)
        self.register_method("capabilities/call", self._handle_call)

    async def _handle_initialize(self, params: dict[str, Any], client_id: str) -> dict[str, Any]:
        remote_versions = list(params.get("protocol_versions") or [])
        agreed = negotiate_version(SUPPORTED_PROTOCOL_VERSIONS, remote_versions)
        if agreed is None:
            return {
                "server_id": self.server_id,
                "agreed_version": "",
                "protocol_versions": list(SUPPORTED_PROTOCOL_VERSIONS),
                "failure_reason": (
                    f"No shared protocol version. Server: {list(SUPPORTED_PROTOCOL_VERSIONS)}; "
                    f"client: {remote_versions}."
                ),
            }
        # A connecting client's needs become PENDING requests, never
        # automatic grants -- the same least-privilege default a plugin
        # gets on discovery.
        self.declare_for(client_id)
        return {
            "server_id": self.server_id,
            "agreed_version": agreed,
            "protocol_versions": list(SUPPORTED_PROTOCOL_VERSIONS),
            "failure_reason": "",
        }

    async def _handle_list(self, params: dict[str, Any], client_id: str) -> dict[str, Any]:
        kind = params.get("kind")
        capabilities = self._capabilities.list_capabilities(kind=kind)
        return {
            "capabilities": [
                {
                    "name": c.name,
                    "version": c.version,
                    "kind": c.kind,
                    "description": c.description,
                    "permissions": list(c.permissions),
                    "metadata": dict(c.metadata),
                }
                for c in capabilities
            ]
        }

    async def _handle_call(self, params: dict[str, Any], client_id: str) -> dict[str, Any]:
        name = str(params.get("name") or "")
        if not name:
            raise MCPError("capabilities/call requires a 'name' parameter.")
        return await self.invoke(name, dict(params.get("arguments") or {}), client_id=client_id)

    # ------------------------------------------------------------------
    # Lifecycle (IService-shaped)
    # ------------------------------------------------------------------
    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> None:
        """Idempotent. No socket is opened here -- a transport owns that;
        this marks the runtime willing to serve requests."""
        self._running = True
        _logger.info("MCP server runtime started: {}", self.server_id)

    async def stop(self) -> None:
        self._running = False
        _logger.info("MCP server runtime stopped: {}", self.server_id)

    async def health(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(healthy=False, detail="MCP server runtime is not running.")
        return HealthStatus(healthy=True)

    async def status(self) -> ServiceStatus:
        return ServiceStatus(
            name=f"mcp-server:{self.server_id}",
            state="running" if self._running else "stopped",
            detail={
                "protocol_version": PROTOCOL_VERSION,
                "supported_protocol_versions": list(SUPPORTED_PROTOCOL_VERSIONS),
                "capability_count": len(self._capabilities),
                "capabilities": list(self._capabilities.names),
                "methods": sorted(self._methods),
            },
        )

    # ------------------------------------------------------------------
    # Events (no-op without a bus -- same pattern as MemoryService)
    # ------------------------------------------------------------------
    async def _publish_capabilities_changed(self) -> None:
        if self._event_bus is None:
            return
        await self._event_bus.publish(
            MCPCapabilitiesChangedEvent(owner=self.server_id, count=len(self._capabilities))
        )

    async def _publish_permission_denied(self, principal: str, capability: str, scope: str) -> None:
        if self._event_bus is None:
            return
        await self._event_bus.publish(
            MCPPermissionDeniedEvent(principal=principal, capability=capability, scope=scope)
        )
