"""Model Context Protocol ports -- Milestone 10.5 Task Group A.

The seam every MCP transport and every exposed/consumed capability plugs
into, the same "port + adapter" shape every other cross-cutting
capability in this codebase already uses
(:class:`~jarvis.core.interfaces.search.ISearchSource`,
:class:`~jarvis.core.interfaces.vector_store.IVectorStore`,
:class:`~jarvis.core.interfaces.llm_provider.ILLMProvider`, ...).

**Ports only -- no provider-specific code.** Task Group A is the MCP
runtime foundation: the registry, the transport abstraction, the client
and server lifecycles, and negotiation. Concrete network transports
(``stdio``/``websocket``/``http``/``ipc``, named in
:data:`TRANSPORT_TYPES` so future work uses consistent identifiers) and
concrete provider integrations are explicitly *not* built here -- they
plug into :class:`IMCPTransport` without this module changing.

**Permissions reuse the existing vocabulary.** A capability declares
scopes drawn from ``core/plugins/sdk.py``'s ``PERMISSION_SCOPES`` -- the
same fixed set a plugin manifest declares, gated by the same
``PermissionModel``. There is deliberately no second permission
vocabulary and no second permission system; see
``core/mcp/server.py`` for how the existing model is namespaced across
both principal kinds.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

#: Transport identifiers this platform recognizes. All five ship an
#: implementation: ``in_process`` in ``core/mcp/transport.py``, the
#: other four in ``core/mcp/transports/`` (Milestone 10.5 Task Group B).
#:
#: Closed by design. A transport identifier names a *wire protocol*, and
#: an integration author configures one of these rather than inventing a
#: sixth -- which is why ``TransportFactoryRegistry.register`` rejects
#: anything outside this set.
TRANSPORT_TYPES: frozenset[str] = frozenset(
    {
        "in_process",
        "stdio",
        "websocket",
        "http",
        "ipc",
    }
)

#: MCP's three capability primitives. Kept as a frozenset of plain
#: strings (not an enum) to match ``PERMISSION_SCOPES``' own shape --
#: validated at registration, serialized without conversion.
CAPABILITY_KINDS: frozenset[str] = frozenset({"tool", "resource", "prompt"})


class MCPError(Exception):
    """Base for every MCP-platform failure. Mirrors ``PluginError``'s
    role in the plugin platform -- one catchable base per subsystem."""


class MCPTransportError(MCPError):
    """A transport-level failure: connect, disconnect, or request."""


class MCPCapabilityError(MCPError):
    """An invalid capability declaration, or a name collision."""


@dataclass(frozen=True, slots=True)
class MCPCapability:
    """One capability offered over MCP -- by JARVIS to an external
    client (``core/mcp/server.py``) or by an external server to JARVIS
    (``core/mcp/client.py``). The same shape in both directions, so
    negotiation logic never branches on which side declared it.

    ``permissions`` are scopes from ``core/plugins/sdk.py``'s
    ``PERMISSION_SCOPES`` -- declaring one is a *request*, never a
    grant, exactly as a plugin manifest's own ``permissions`` list is.
    """

    name: str
    version: str = "1.0.0"
    kind: str = "tool"
    description: str = ""
    permissions: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class IMCPProvider(Protocol):
    """One configured MCP integration -- Milestone 10.5 Task Group C.

    Deliberately **transport-independent**: a provider declares which
    transport it wants in its metadata/config and the framework builds
    it through the existing ``TransportFactoryRegistry``. Nothing here
    references a socket, a subprocess, or a URL, so adding a fifth
    transport never touches a provider.

    The six lifecycle methods mirror ``core/interfaces/service.py``'s
    ``IService`` exactly, rather than inventing a second lifecycle
    vocabulary for the same shape. ``suspend``/``resume`` are the two
    additions a provider genuinely needs that a service does not: an
    integration can be temporarily parked without being torn down and
    re-registered.

    ``core/mcp/providers/transport_backed.py`` implements this for the
    entire "point at an MCP server with this transport config" case,
    which is every provider M11 currently anticipates. This Protocol
    exists so a future integration with genuinely different needs (a
    token refresh loop, say) can supply its own implementation without
    the framework changing.
    """

    #: Stable identifier, unique within the provider registry.
    provider_id: str

    async def initialize(self) -> None:
        """Resolve dependencies and validate configuration. No network
        or subprocess I/O -- that belongs to :meth:`connect`."""
        ...

    async def start(self) -> None:
        """Begin real work: connect to the peer."""
        ...

    async def stop(self) -> None:
        """Graceful, idempotent stop."""
        ...

    async def suspend(self) -> None:
        """Park the provider without deregistering it -- the connection
        drops, the registration and configuration survive."""
        ...

    async def resume(self) -> None:
        """Reverse of :meth:`suspend`."""
        ...

    async def health(self) -> Any:
        """Cheap liveness signal. Returns
        ``core/interfaces/service.py``'s ``HealthStatus``."""
        ...

    async def status(self) -> Any:
        """Detailed on-demand snapshot. Returns ``ServiceStatus``."""
        ...

    async def shutdown(self) -> None:
        """Final resource release beyond :meth:`stop`."""
        ...


@runtime_checkable
class IMCPTransport(Protocol):
    """Abstract MCP transport. One instance per connection.

    Deliberately narrow: MCP is a JSON-RPC protocol, so a single
    ``request`` primitive carries the handshake, capability discovery,
    and every later call. A transport owns framing and delivery only --
    it never interprets a method name, and never enforces a permission
    (that is the server runtime's job).
    """

    #: One of :data:`TRANSPORT_TYPES`.
    transport_type: str

    @property
    def is_connected(self) -> bool: ...

    async def connect(self) -> None:
        """Establish the underlying channel. Idempotent -- connecting an
        already-connected transport is a no-op, never an error."""
        ...

    async def disconnect(self) -> None:
        """Tear the channel down. Idempotent, and safe to call on a
        transport that never connected."""
        ...

    async def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """One JSON-RPC round trip. Raises :class:`MCPTransportError` if
        the channel is down or the peer reports a protocol-level
        failure."""
        ...
