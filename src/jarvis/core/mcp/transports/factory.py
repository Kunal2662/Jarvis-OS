"""Transport factory -- Milestone 10.5 Task Group B, deliverable 5.

Builds a concrete :class:`~jarvis.core.interfaces.mcp.IMCPTransport`
from plain configuration, and registers every shipped transport into
Task Group A's existing
:class:`~jarvis.core.mcp.transport.TransportFactoryRegistry`.

Task Group A left that registry deliberately empty and said a later
pass would call ``register(...)`` at its DI composition root. This is
that pass: :func:`build_default_transport_registry` is what the
container now calls, and no code in the client runtime, the server
runtime, or the registry itself branches on transport type -- adding a
fifth transport later means adding one factory here and nothing else.

Each factory is a plain callable taking the connection's config dict,
matching the ``TransportFactory`` alias Task Group A already defined --
composition over inheritance, no transport base class anywhere.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from jarvis.core.interfaces.mcp import TRANSPORT_TYPES, MCPTransportError
from jarvis.core.mcp.transport import InProcessTransport, TransportFactoryRegistry
from jarvis.core.mcp.transports.http import HttpTransport
from jarvis.core.mcp.transports.ipc import IpcTransport
from jarvis.core.mcp.transports.stdio import StdioTransport
from jarvis.core.mcp.transports.websocket import WebSocketTransport

if TYPE_CHECKING:
    from jarvis.core.interfaces.mcp import IMCPTransport
    from jarvis.core.mcp.server import MCPServerRuntime


def _require(config: dict[str, Any], key: str, transport_type: str) -> Any:
    value = config.get(key)
    if value in (None, ""):
        raise MCPTransportError(
            f"{transport_type} transport requires a {key!r} entry in its configuration."
        )
    return value


def build_stdio_transport(config: dict[str, Any]) -> IMCPTransport:
    return StdioTransport(
        str(_require(config, "command", "stdio")),
        list(config.get("args") or ()),
        cwd=config.get("cwd"),
        env=config.get("env"),
        **_timeout_kwargs(config),
    )


def build_websocket_transport(config: dict[str, Any]) -> IMCPTransport:
    return WebSocketTransport(
        str(_require(config, "url", "websocket")),
        headers=config.get("headers"),
        **_timeout_kwargs(config),
    )


def build_http_transport(config: dict[str, Any]) -> IMCPTransport:
    return HttpTransport(
        str(_require(config, "url", "http")),
        headers=config.get("headers"),
        verify=bool(config.get("verify", True)),
        **_timeout_kwargs(config),
    )


def build_ipc_transport(config: dict[str, Any]) -> IMCPTransport:
    return IpcTransport(
        str(_require(config, "endpoint", "ipc")),
        **_timeout_kwargs(config),
    )


def _timeout_kwargs(config: dict[str, Any]) -> dict[str, float]:
    timeout = config.get("request_timeout_seconds")
    return {} if timeout is None else {"request_timeout_seconds": float(timeout)}


def build_default_transport_registry(
    *,
    in_process_server: MCPServerRuntime | None = None,
) -> TransportFactoryRegistry:
    """Every transport this build ships, registered.

    *in_process_server*, when supplied, also registers the Task Group A
    ``in_process`` reference transport so a caller can address JARVIS's
    own MCP server through the same factory as any remote peer -- one
    creation path for every transport type, rather than in-process being
    a special case constructed by hand.
    """
    registry = TransportFactoryRegistry()
    registry.register("stdio", build_stdio_transport)
    registry.register("websocket", build_websocket_transport)
    registry.register("http", build_http_transport)
    registry.register("ipc", build_ipc_transport)

    if in_process_server is not None:

        def _build_in_process(config: dict[str, Any]) -> IMCPTransport:
            return InProcessTransport(
                in_process_server,
                client_id=str(config.get("client_id") or "jarvis-local"),
            )

        registry.register("in_process", _build_in_process)

    missing = sorted(TRANSPORT_TYPES - set(registry.registered_types))
    if missing and in_process_server is not None:
        # Guards the vocabulary against silent drift: every name in
        # TRANSPORT_TYPES should be constructible once this factory has
        # been given everything it needs.
        raise MCPTransportError(f"Transport factory is missing registrations for {missing}.")
    return registry
