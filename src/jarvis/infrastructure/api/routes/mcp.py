"""MCP platform API -- Milestone 10.5 Task Group A, deliverable 9.

Minimal, read-only runtime endpoints over the MCP client/server
runtimes: ``GET /api/v1/mcp/status``, ``GET /api/v1/mcp/capabilities``,
``GET /api/v1/mcp/connections``, ``GET /api/v1/mcp/transports``.

**Deliberately no provider management.** Registering, connecting,
granting or removing an MCP provider is Task Group B's surface and
M11's provider scope -- this router observes the runtime, it does not
mutate it, so every route here is a ``GET``. That keeps Task Group A's
REST surface additive and backward compatible when the write endpoints
land beside it.

Same ``Depends(get_current_session)`` Bearer auth + ``{data, meta}``
envelope convention as ``routes/plugins.py``/``routes/devtools.py``/
``routes/agent.py``/``routes/knowledge.py``/``routes/intelligence.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request

from jarvis.core.mcp.negotiation import PROTOCOL_VERSION, SUPPORTED_PROTOCOL_VERSIONS
from jarvis.infrastructure.api.auth import Envelope, envelope, get_current_session

if TYPE_CHECKING:
    from jarvis.core.mcp.client import MCPClientRuntime
    from jarvis.core.mcp.heartbeat import MCPHeartbeatMonitor
    from jarvis.core.mcp.server import MCPServerRuntime
    from jarvis.core.mcp.transport import TransportFactoryRegistry

router = APIRouter(prefix="/mcp", tags=["mcp"], dependencies=[Depends(get_current_session)])


def _server(request: Request) -> MCPServerRuntime:
    return cast("MCPServerRuntime", request.app.state.container.mcp_server_runtime())


def _client(request: Request) -> MCPClientRuntime:
    return cast("MCPClientRuntime", request.app.state.container.mcp_client_runtime())


def _transports(request: Request) -> TransportFactoryRegistry:
    return cast("TransportFactoryRegistry", request.app.state.container.mcp_transport_registry())


@router.get("/status", response_model=Envelope[dict[str, Any]])
async def mcp_status(request: Request) -> Envelope[dict[str, Any]]:
    """One combined runtime snapshot -- server side, client side, and
    the negotiated protocol versions this build speaks."""
    server = _server(request)
    client = _client(request)
    server_status = await server.status()
    client_status = await client.status()
    server_health = await server.health()
    client_health = await client.health()

    return envelope(
        {
            "protocol_version": PROTOCOL_VERSION,
            "supported_protocol_versions": list(SUPPORTED_PROTOCOL_VERSIONS),
            "server": {
                "id": server.server_id,
                "state": server_status.state,
                "healthy": server_health.healthy,
                "detail": server_status.detail,
            },
            "client": {
                "id": client.client_id,
                "state": client_status.state,
                "healthy": client_health.healthy,
                "connection_count": len(client.server_ids),
            },
            "registered_transports": list(_transports(request).registered_types),
        },
        meta={"healthy": server_health.healthy and client_health.healthy},
    )


@router.get("/capabilities", response_model=Envelope[tuple[dict[str, Any], ...]])
async def mcp_capabilities(
    request: Request, kind: str | None = None
) -> Envelope[tuple[dict[str, Any], ...]]:
    """Capabilities JARVIS exposes over MCP. Peer-offered capabilities
    are reported per connection by ``/connections`` instead, so one
    peer's list can never be mistaken for JARVIS's own."""
    registry = _server(request).capabilities
    payload = registry.snapshot()
    if kind is not None:
        payload = tuple(c for c in payload if c["kind"] == kind)
    return envelope(cast("tuple[dict[str, Any], ...]", payload), meta={"count": len(payload)})


@router.get("/connections", response_model=Envelope[tuple[dict[str, Any], ...]])
async def mcp_connections(request: Request) -> Envelope[tuple[dict[str, Any], ...]]:
    """Every registered outbound connection and its live state --
    including peers configured but not currently reachable, and the
    capabilities negotiation rejected, with reasons."""
    payload = _client(request).snapshot()
    return envelope(payload, meta={"count": len(payload)})


@router.get("/transports", response_model=Envelope[tuple[dict[str, Any], ...]])
async def mcp_transports(request: Request) -> Envelope[tuple[dict[str, Any], ...]]:
    """Every transport identifier this platform knows, each with its
    static traits and whether this build can actually create it.

    Task Group A returned a bare `{known, registered}` pair here because
    nothing was registered yet. Now that all five are, the endpoint
    returns one descriptor per transport -- a superset of the old shape's
    information, and the shape `/transports/{id}` returns a single
    element of.
    """
    registry = _transports(request)
    payload = registry.describe_all()
    return envelope(
        payload,
        meta={
            "count": len(payload),
            "registered": list(registry.registered_types),
        },
    )


@router.get("/transports/{transport_id}", response_model=Envelope[dict[str, Any]])
async def mcp_transport_detail(transport_id: str, request: Request) -> Envelope[dict[str, Any]]:
    """One transport's descriptor, plus the connections currently using
    it. A 404 means the identifier is not in the vocabulary at all --
    "known but not registered in this build" is a 200 with
    ``registered: false``, which is a different thing and worth
    distinguishing."""
    registry = _transports(request)
    descriptor = registry.describe(transport_id)
    if descriptor is None:
        raise HTTPException(status_code=404, detail=f"Unknown transport {transport_id!r}.")

    in_use = [
        connection
        for connection in _client(request).snapshot()
        if connection.get("transport") == transport_id
    ]
    return envelope(
        {**descriptor, "connections": in_use},
        meta={"connection_count": len(in_use)},
    )


@router.get("/heartbeat", response_model=Envelope[tuple[dict[str, Any], ...]])
async def mcp_heartbeat(request: Request) -> Envelope[tuple[dict[str, Any], ...]]:
    """The most recent liveness result per connected peer. Read-only --
    it reports what the monitor last observed and never forces a probe,
    so polling this endpoint cannot generate peer traffic."""
    monitor = cast("MCPHeartbeatMonitor", request.app.state.container.mcp_heartbeat_monitor())
    payload = monitor.snapshot()
    return envelope(
        cast("tuple[dict[str, Any], ...]", payload),
        meta={"count": len(payload), "running": monitor.is_running},
    )
