"""MCP Transport abstraction -- Milestone 10.5 Task Group A, deliverable 2.

:class:`~jarvis.core.interfaces.mcp.IMCPTransport` (the port) lives in
``core/interfaces/mcp.py``; this module holds the registry future
transports register into, plus the one reference implementation.

**No provider-specific code, by design.** ``stdio``, ``websocket``,
``http`` and ``ipc`` are named in
:data:`~jarvis.core.interfaces.mcp.TRANSPORT_TYPES` and are explicitly
*not* implemented in this task group -- each is its own later pass and
plugs in through :meth:`TransportFactoryRegistry.register` without this
module changing, the same extensibility seam ``ISearchSource`` gives
Universal Search.

**Why one transport does ship.** :class:`InProcessTransport` connects a
client runtime directly to an in-process :class:`~jarvis.core.mcp.server.
MCPServerRuntime` with no network, no subprocess, and no serialization
boundary. It is not a provider integration and not a test double: it is
the transport JARVIS uses to consume its *own* MCP server, and shipping
it means the client/server handshake, capability discovery, permission
enforcement and negotiation paths in this task group are exercised
against something real rather than only against mocks.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from jarvis.core.interfaces.mcp import TRANSPORT_TYPES, MCPTransportError
from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.core.interfaces.mcp import IMCPTransport
    from jarvis.core.mcp.server import MCPServerRuntime

_logger = get_logger("jarvis.core.mcp.transport")

#: A factory takes the connection's own config dict and returns a
#: ready-but-unconnected transport. Deliberately a plain callable rather
#: than a class hierarchy -- composition over inheritance, per
#: ``docs/ARCHITECTURE.md``'s development principles.
TransportFactory = Callable[[dict[str, Any]], "IMCPTransport"]


class TransportFactoryRegistry:
    """Maps a transport type name to the factory that builds it.

    Empty of network transports today. A milestone that adds ``stdio``
    calls ``register("stdio", build_stdio_transport)`` at its DI
    composition root; nothing in the client runtime branches on
    transport type.
    """

    def __init__(self) -> None:
        self._factories: dict[str, TransportFactory] = {}

    def register(self, transport_type: str, factory: TransportFactory) -> None:
        if transport_type not in TRANSPORT_TYPES:
            raise MCPTransportError(
                f"Unknown transport type {transport_type!r}; " f"allowed: {sorted(TRANSPORT_TYPES)}"
            )
        self._factories[transport_type] = factory
        _logger.info("MCP transport registered: {}", transport_type)

    def unregister(self, transport_type: str) -> bool:
        return self._factories.pop(transport_type, None) is not None

    def create(self, transport_type: str, config: dict[str, Any] | None = None) -> IMCPTransport:
        factory = self._factories.get(transport_type)
        if factory is None:
            raise MCPTransportError(
                f"No transport registered for {transport_type!r}. "
                f"Registered: {sorted(self._factories) or 'none'}."
            )
        return factory(config or {})

    @property
    def registered_types(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))

    def supports(self, transport_type: str) -> bool:
        return transport_type in self._factories


class InProcessTransport:
    """The reference :class:`IMCPTransport` -- dispatches straight to an
    in-process :class:`~jarvis.core.mcp.server.MCPServerRuntime`.

    Implements the Protocol structurally (no inheritance), matching how
    every other adapter in this codebase satisfies its port.
    """

    transport_type = "in_process"

    def __init__(self, server: MCPServerRuntime, *, client_id: str = "jarvis-local") -> None:
        self._server = server
        self._client_id = client_id
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self._connected:
            raise MCPTransportError(f"Cannot call {method!r}: transport is not connected.")
        return await self._server.handle_request(method, params or {}, client_id=self._client_id)
