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
    from jarvis.core.mcp.auth.manager import MCPAuthManager
    from jarvis.core.mcp.auth.store import CredentialStore
    from jarvis.core.mcp.auth.strategies import AuthStrategyRegistry
    from jarvis.core.mcp.client import MCPClientRuntime
    from jarvis.core.mcp.diagnostics import MCPDiagnostics
    from jarvis.core.mcp.heartbeat import MCPHeartbeatMonitor
    from jarvis.core.mcp.providers.manager import MCPProviderManager
    from jarvis.core.mcp.providers.registry import MCPProviderRegistry
    from jarvis.core.mcp.server import MCPServerRuntime
    from jarvis.core.mcp.transport import TransportFactoryRegistry

router = APIRouter(prefix="/mcp", tags=["mcp"], dependencies=[Depends(get_current_session)])


def _server(request: Request) -> MCPServerRuntime:
    return cast("MCPServerRuntime", request.app.state.container.mcp_server_runtime())


def _client(request: Request) -> MCPClientRuntime:
    return cast("MCPClientRuntime", request.app.state.container.mcp_client_runtime())


def _transports(request: Request) -> TransportFactoryRegistry:
    return cast("TransportFactoryRegistry", request.app.state.container.mcp_transport_registry())


def _auth(request: Request) -> MCPAuthManager:
    return cast("MCPAuthManager", request.app.state.container.mcp_auth_manager())


def _auth_strategies(request: Request) -> AuthStrategyRegistry:
    return cast("AuthStrategyRegistry", request.app.state.container.mcp_auth_strategies())


def _credential_store(request: Request) -> CredentialStore:
    return cast("CredentialStore", request.app.state.container.mcp_credential_store())


def _provider_registry(request: Request) -> MCPProviderRegistry:
    return cast("MCPProviderRegistry", request.app.state.container.mcp_provider_registry())


def _diagnostics(request: Request) -> MCPDiagnostics:
    return cast("MCPDiagnostics", request.app.state.container.mcp_diagnostics())


def _provider_manager(request: Request) -> MCPProviderManager:
    return cast("MCPProviderManager", request.app.state.container.mcp_provider_manager())


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


@router.get("/providers", response_model=Envelope[tuple[dict[str, Any], ...]])
async def mcp_providers(
    request: Request,
    transport: str | None = None,
    capability: str | None = None,
    state: str | None = None,
    protocol: str | None = None,
    permission: str | None = None,
    enabled_only: bool = False,
) -> Envelope[tuple[dict[str, Any], ...]]:
    """Registered providers, with the registry's own discovery filters
    exposed as query parameters. Filters combine with AND; omitting one
    does not constrain."""
    registry = _provider_registry(request)
    records = registry.discover(
        transport=transport,
        capability=capability,
        state=state,
        protocol=protocol,
        permission=permission,
        enabled_only=enabled_only,
    )
    payload = tuple(record.as_dict() for record in records)
    return envelope(payload, meta={"count": len(payload), "total": len(registry)})


@router.get("/providers/{provider_id}", response_model=Envelope[dict[str, Any]])
async def mcp_provider_detail(provider_id: str, request: Request) -> Envelope[dict[str, Any]]:
    """One provider's full status -- registration, configuration, live
    connection detail, and its granted-versus-pending permissions."""
    manager = _provider_manager(request)
    if not manager.registry.has(provider_id):
        raise HTTPException(status_code=404, detail=f"Unknown provider {provider_id!r}.")
    return envelope(await manager.status(provider_id))


@router.get("/providers/{provider_id}/health", response_model=Envelope[dict[str, Any]])
async def mcp_provider_health(provider_id: str, request: Request) -> Envelope[dict[str, Any]]:
    """One provider's liveness. Rides the same check M9's
    ``HealthMonitor`` collector aggregates -- not a second health path."""
    manager = _provider_manager(request)
    if not manager.registry.has(provider_id):
        raise HTTPException(status_code=404, detail=f"Unknown provider {provider_id!r}.")
    health = await manager.health(provider_id)
    return envelope(health, meta={"healthy": health["healthy"]})


@router.get("/providers/{provider_id}/metadata", response_model=Envelope[dict[str, Any]])
async def mcp_provider_metadata(provider_id: str, request: Request) -> Envelope[dict[str, Any]]:
    """A provider's declaration alone -- what it is, not what it is
    doing. Reading it never touches the transport."""
    metadata = _provider_registry(request).metadata(provider_id)
    if metadata is None:
        raise HTTPException(status_code=404, detail=f"Unknown provider {provider_id!r}.")
    return envelope(metadata.as_dict())


@router.get("/auth", response_model=Envelope[tuple[dict[str, Any], ...]])
async def mcp_auth(request: Request) -> Envelope[tuple[dict[str, Any], ...]]:
    """Authentication state for every provider that has one.

    **Metadata only.** Every payload here comes from
    ``Credential.to_public_dict``, which reports *whether* a token
    exists and when it expires -- never its value. There is no code path
    from this router to a token, by construction rather than by
    remembering to redact.
    """
    manager = _auth(request)
    payload = manager.public_snapshot()
    return envelope(
        payload,
        meta={
            "count": len(payload),
            "supported_methods": list(_auth_strategies(request).supported_methods),
            "can_persist": _credential_store(request).can_persist,
        },
    )


@router.get("/auth/methods", response_model=Envelope[tuple[dict[str, Any], ...]])
async def mcp_auth_methods(request: Request) -> Envelope[tuple[dict[str, Any], ...]]:
    """Every authentication method in the vocabulary and whether this
    build can actually perform it -- the same known-versus-supported
    honesty the transports endpoint reports. ``oauth2`` and
    ``client_credentials`` are listed and unsupported: both need an
    authorization server and a callback endpoint, neither of which this
    task group ships."""
    payload = _auth_strategies(request).describe()
    return envelope(payload, meta={"count": len(payload)})


@router.get("/auth/{provider_id}", response_model=Envelope[dict[str, Any]])
async def mcp_auth_detail(provider_id: str, request: Request) -> Envelope[dict[str, Any]]:
    """One provider's authentication state -- session, credential
    metadata, and whether it is currently usable."""
    manager = _auth(request)
    if provider_id not in manager.provider_ids:
        raise HTTPException(
            status_code=404, detail=f"No authentication state for provider {provider_id!r}."
        )
    return envelope(manager.status(provider_id))


@router.get("/auth/{provider_id}/status", response_model=Envelope[dict[str, Any]])
async def mcp_auth_status(provider_id: str, request: Request) -> Envelope[dict[str, Any]]:
    """The compact liveness answer: is this provider authenticated right
    now, and if not, why not."""
    manager = _auth(request)
    if provider_id not in manager.provider_ids:
        raise HTTPException(
            status_code=404, detail=f"No authentication state for provider {provider_id!r}."
        )

    full = manager.status(provider_id)
    credential = full["credential"] or {}
    return envelope(
        {
            "provider_id": provider_id,
            "authenticated": full["authenticated"],
            "session_state": full["session"]["state"],
            "credential_status": credential.get("status", "missing"),
            "expires_at": credential.get("expires_at"),
            "seconds_until_expiry": credential.get("seconds_until_expiry"),
            "is_refreshable": credential.get("is_refreshable", False),
            "error": full["session"]["error"],
        },
        meta={"healthy": full["authenticated"]},
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


# ---------------------------------------------------------------------------
# Diagnostics (Milestone 10.5 Task Group E)
# ---------------------------------------------------------------------------
@router.get("/diagnostics", response_model=Envelope[dict[str, Any]])
async def mcp_diagnostics(request: Request) -> Envelope[dict[str, Any]]:
    """Every MCP subsystem in one payload -- the same aggregate
    ``jarvis mcp list --json`` prints, from the same singleton, so the
    two delivery mechanisms can never report different facts.

    Read-only, like the rest of this router: it collects what each
    subsystem already knows and connects to nothing."""
    diagnostics = _diagnostics(request)
    payload = await diagnostics.report()
    return envelope(payload, meta=await diagnostics.summary())


@router.get("/validate", response_model=Envelope[dict[str, Any]])
async def mcp_validate(request: Request) -> Envelope[dict[str, Any]]:
    """Cross-subsystem consistency -- a provider whose transport nothing
    registered, an auth method no strategy implements, a scope still
    awaiting a grant decision. The checks no single registry can make
    about itself.

    Always ``200``: a configuration problem is a finding to report, not
    a failure of this endpoint. Callers branch on ``data.ok``."""
    payload = _diagnostics(request).validate()
    return envelope(
        payload,
        meta={
            "ok": payload["ok"],
            "error_count": payload["error_count"],
            "warning_count": payload["warning_count"],
        },
    )
