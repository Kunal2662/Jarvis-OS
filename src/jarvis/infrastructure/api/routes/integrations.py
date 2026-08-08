"""Integration Platform API -- Milestone 11 Task Group E.

``/api/v1/integrations/*`` -- thin REST over ``IntegrationService``,
with the same ``{data, meta}`` envelope every resource router since M9
Task Group E uses. This one owns no state and no logic of its own.

**One route is deliberately unauthenticated, and only one.** The OAuth
callback is reached by the user's *browser* following a redirect from
the vendor, which carries no ``Authorization`` header and cannot be made
to. Requiring a Bearer token there would mean the flow could never
complete. What protects it instead is the ``state`` parameter:
generated with ``secrets`` when the flow starts, held server-side
alongside the PKCE verifier, single-use, and expiring. An unknown,
replayed or stale ``state`` is refused -- so the callback accepts
exactly one response per flow this process started, and nothing else.
That is the standard defence for this exact problem (RFC 6749 §10.12),
and it is stronger here than a Bearer token would be, because the
attacker a Bearer token would stop is not the attacker this endpoint
faces.

Every other route sits behind ``Depends(get_current_session)`` like the
rest of the API.

**No token ever appears in a response.** The authorize route returns a
URL and a ``state``; the callback returns the credential's *public*
dict (``has_access_token``, expiry, scopes -- never a value); preview
returns request metadata with headers omitted precisely because one of
them is the token.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from jarvis.infrastructure.api.auth import Envelope, envelope, get_current_session

if TYPE_CHECKING:
    from jarvis.services.integration_service import IntegrationService

#: The authenticated surface.
router = APIRouter(tags=["integrations"], dependencies=[Depends(get_current_session)])

#: The callback only. A separate router because its whole point is that
#: it carries no session dependency -- keeping it on the same router and
#: overriding the dependency per route would make the exception easy to
#: miss in review.
callback_router = APIRouter(tags=["integrations"])


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------
class InstallRequest(BaseModel):
    integration_id: str
    account_id: str = ""
    replace: bool = False


class AuthorizeRequest(BaseModel):
    integration_id: str
    redirect_uri: str = ""
    scopes: list[str] | None = None


class InvokeRequest(BaseModel):
    operation: str
    params: dict[str, Any] = {}


class TestConnectionRequest(BaseModel):
    #: An existing, non-mutating operation name on *this* integration's
    #: own spec -- never a URL. Left unset, a safe zero-argument read
    #: operation is chosen automatically. See
    #: docs/M11_API_CENTER_LOGIC_CONTRACT.md §11/§18: the vendor target
    #: always comes from trusted catalogue configuration, never from
    #: caller input, which is what rules out SSRF here.
    operation: str | None = None
    timeout_seconds: float | None = None


class SwitchRequest(BaseModel):
    #: Both ids must already be installed, trusted, catalogue-backed
    #: integrations -- there is no field here for a URL, a provider
    #: class, or a credential. See
    #: docs/M11_API_CENTER_LOGIC_CONTRACT.md §14.
    operation: str
    from_integration_id: str
    to_integration_id: str


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------
def _service(request: Request) -> IntegrationService:
    return cast("IntegrationService", request.app.state.container.integration_service())


def _bad_request(err: Exception) -> HTTPException:
    """``ServiceError`` means the caller asked for something invalid --
    an unknown integration, an undeclared parameter, a replayed OAuth
    state. 400, not 500: nothing broke."""
    return HTTPException(status_code=400, detail=str(err))


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------
@router.get("/integrations/catalogue", response_model=Envelope[list[dict[str, Any]]])
async def integration_catalogue(request: Request) -> Envelope[list[dict[str, Any]]]:
    """Every integration this build can install. Data only -- describing
    one never touches the network."""
    entries = list(_service(request).catalogue())
    return envelope(entries, meta={"count": len(entries)})


@router.get("/integrations/catalogue/{integration_id}", response_model=Envelope[dict[str, Any]])
async def integration_detail(integration_id: str, request: Request) -> Envelope[dict[str, Any]]:
    """One integration in full, including every operation, the JARVIS
    permissions it requests and the vendor scopes it needs."""
    from jarvis.core.exceptions import ServiceError

    try:
        return envelope(_service(request).describe(integration_id))
    except ServiceError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err


# ---------------------------------------------------------------------------
# Installation + lifecycle
# ---------------------------------------------------------------------------
@router.get("/integrations", response_model=Envelope[list[dict[str, Any]]])
async def list_integrations(request: Request) -> Envelope[list[dict[str, Any]]]:
    installed = list(await _service(request).list_installed())
    return envelope(installed, meta={"count": len(installed)})


@router.post("/integrations", response_model=Envelope[dict[str, Any]], status_code=201)
async def install_integration(body: InstallRequest, request: Request) -> Envelope[dict[str, Any]]:
    """Register an integration as an MCP provider.

    Installing declares its permission requests against the shared
    ``PermissionModel`` (they land ``PENDING``) and makes no network
    call -- so an approval screen can show what a connector would do
    before anyone authorizes it.
    """
    from jarvis.core.exceptions import ServiceError

    try:
        record = await _service(request).install(
            body.integration_id, account_id=body.account_id, replace=body.replace
        )
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(record, meta={"installed": True})


@router.get("/integrations/observability", response_model=Envelope[dict[str, Any]])
async def integrations_observability(request: Request) -> Envelope[dict[str, Any]]:
    """Safe operational counters across the whole M11 surface --
    installed/connected counts, connection-test and switch tallies,
    failover outcomes, discovery runs, and the gateway's own egress
    counters. Collected from the same in-memory state every other
    diagnostics route already reads; not a second observability
    platform.

    **Registered before ``GET /integrations/{integration_id}`` below,
    deliberately.** FastAPI/Starlette match routes in registration
    order; a single-segment literal path like this one must be declared
    ahead of a single-segment path-*parameter* route or the parameter
    route silently swallows it (as ``/integrations/gateway/stats`` and
    the other two-segment routes below never risk, having two segments
    to a param route's one).
    """
    return envelope(_service(request).observability_snapshot())


@router.get("/integrations/{integration_id}", response_model=Envelope[dict[str, Any]])
async def integration_status(integration_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        return envelope(await _service(request).status(integration_id))
    except ServiceError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err


@router.get("/integrations/{integration_id}/health", response_model=Envelope[dict[str, Any]])
async def integration_health(integration_id: str, request: Request) -> Envelope[dict[str, Any]]:
    """Locally-known health for one installed integration -- never a
    vendor request. Deliberately distinct from (a later task group's)
    Connection Testing; see
    ``docs/M11_API_CENTER_LOGIC_CONTRACT.md`` §11/§13.
    """
    from jarvis.core.exceptions import ServiceError

    try:
        return envelope(await _service(request).health(integration_id))
    except ServiceError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err


@router.post(
    "/integrations/{integration_id}/test-connection", response_model=Envelope[dict[str, Any]]
)
async def test_connection(
    integration_id: str,
    request: Request,
    body: TestConnectionRequest | None = None,
) -> Envelope[dict[str, Any]]:
    """The explicit, user-triggered Connection Test -- M11 Task Group
    B, the one M11 operation permitted to make a real vendor request.
    Deliberately distinct from ``GET .../health`` above (local-only).

    The vendor target always comes from this integration's own trusted
    ``IntegrationSpec``; *operation* selects among its already-declared,
    non-mutating operations and can never be a URL -- there is no SSRF
    surface here because there is nowhere for a caller-supplied
    destination to go. Never raises for a vendor-side failure (auth,
    network, timeout, rate limit, ...) -- those come back as a
    structured, 200-envelope result the caller reads; only an unknown
    *integration_id* is a 404.

    *body* is entirely optional (every field on it is) -- a bare
    ``POST`` with no body runs the automatic zero-argument probe.
    """
    from jarvis.core.exceptions import ServiceError

    body = body or TestConnectionRequest()
    try:
        result = await _service(request).test_connection(
            integration_id,
            operation=body.operation,
            timeout_seconds=body.timeout_seconds,
        )
    except ServiceError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    return envelope(result, meta={"outcome": result["outcome"]})


@router.post("/integrations/{integration_id}/connect", response_model=Envelope[dict[str, Any]])
async def connect_integration(integration_id: str, request: Request) -> Envelope[dict[str, Any]]:
    """Connect through the shared provider manager -- the same state
    machine and the same events every MCP provider uses."""
    from jarvis.core.exceptions import ServiceError

    try:
        return envelope(await _service(request).connect(integration_id))
    except ServiceError as err:
        raise _bad_request(err) from err


@router.post("/integrations/{integration_id}/disconnect", response_model=Envelope[dict[str, Any]])
async def disconnect_integration(integration_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        disconnected = await _service(request).disconnect(integration_id)
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope({"integration_id": integration_id, "disconnected": disconnected})


@router.delete("/integrations/{integration_id}", status_code=204)
async def uninstall_integration(integration_id: str, request: Request) -> None:
    """Remove the provider. The credential is kept -- uninstalling is
    not revoking. ``DELETE /integrations/{id}/credential`` is."""
    if not await _service(request).uninstall(integration_id):
        raise HTTPException(status_code=404, detail="Integration is not installed.")


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------
@router.post("/integrations/oauth/authorize", response_model=Envelope[dict[str, Any]])
async def start_authorization(body: AuthorizeRequest, request: Request) -> Envelope[dict[str, Any]]:
    """Begin an OAuth2 authorization-code flow with PKCE.

    Returns the URL to open and the ``state`` that identifies the flow.
    The PKCE verifier stays server-side and is never returned -- handing
    it to a caller would defeat the exchange it protects.
    """
    from jarvis.core.exceptions import ServiceError

    try:
        started = _service(request).start_authorization(
            body.integration_id, redirect_uri=body.redirect_uri, scopes=body.scopes
        )
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(started, meta={"pkce": "S256"})


@callback_router.get("/integrations/oauth/callback", response_model=Envelope[dict[str, Any]])
async def oauth_callback(
    request: Request,
    state: str = Query(..., description="The flow identifier issued by /authorize."),
    code: str = Query("", description="The vendor's authorization code."),
    error: str = Query("", description="Set when the user declined or the vendor refused."),
) -> Envelope[dict[str, Any]]:
    """Complete the flow. **Deliberately session-free** -- see the module
    docstring for why ``state`` is the right protection here and a
    Bearer token is not available.

    A vendor reporting ``error`` (the user declined, most often) is a
    400 naming what the vendor said, not a 500: nothing broke, the user
    said no.
    """
    from jarvis.core.exceptions import ServiceError

    if error:
        raise HTTPException(
            status_code=400, detail=f"The provider refused the authorization: {error}"
        )
    try:
        completed = await _service(request).complete_authorization(state=state, code=code)
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(completed, meta={"authorized": True})


@router.delete("/integrations/{integration_id}/credential", status_code=204)
async def revoke_credential(integration_id: str, request: Request) -> None:
    """Revoke the credential, remotely where the vendor supports it, and
    disconnect. The provider registration survives."""
    from jarvis.core.exceptions import ServiceError

    try:
        revoked = await _service(request).revoke(integration_id)
    except ServiceError as err:
        raise _bad_request(err) from err
    if not revoked:
        raise HTTPException(status_code=404, detail="No credential is stored.")


# ---------------------------------------------------------------------------
# Invocation
# ---------------------------------------------------------------------------
@router.post("/integrations/{integration_id}/invoke", response_model=Envelope[dict[str, Any]])
async def invoke_operation(
    integration_id: str, body: InvokeRequest, request: Request
) -> Envelope[dict[str, Any]]:
    """Call one vendor operation.

    Both permission gates are checked inside the provider before
    anything leaves: the operator's grant in the shared
    ``PermissionModel``, and the vendor scopes the token actually
    carries. A refusal is a 400 naming which gate said no.
    """
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _service(request).invoke(integration_id, body.operation, body.params)
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(
        result,
        meta={"status_code": result["status_code"], "from_cache": result["from_cache"]},
    )


@router.post("/integrations/{integration_id}/preview", response_model=Envelope[dict[str, Any]])
async def preview_operation(
    integration_id: str, body: InvokeRequest, request: Request
) -> Envelope[dict[str, Any]]:
    """What ``/invoke`` *would* send, without sending it.

    An outbound call cannot be undone by inspecting it afterwards, so
    the resolved URL and parameter names are inspectable first. Headers
    are omitted -- one of them is the token.
    """
    from jarvis.core.exceptions import ServiceError

    try:
        return envelope(_service(request).preview(integration_id, body.operation, body.params))
    except ServiceError as err:
        raise _bad_request(err) from err


@router.get("/integrations/{integration_id}/search", response_model=Envelope[list[dict[str, Any]]])
async def search_integration(
    integration_id: str,
    request: Request,
    q: str = Query(..., description="What to look for inside this vendor."),
    top_k: int = 10,
) -> Envelope[list[dict[str, Any]]]:
    """Search inside one connected integration, through the vendor's own
    search endpoint."""
    from jarvis.core.exceptions import ServiceError

    try:
        rows = await _service(request).search(integration_id, q, top_k=top_k)
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(rows, meta={"count": len(rows), "query": q})


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------
@router.get("/integrations/gateway/stats", response_model=Envelope[dict[str, Any]])
async def gateway_stats(request: Request) -> Envelope[dict[str, Any]]:
    """Egress counters: calls, failures, retries, cache hits.

    Collected from the gateway, which is the only object that knows --
    the same collects-never-computes rule ``MCPDiagnostics`` follows.
    """
    return envelope(_service(request).gateway_stats())


# ---------------------------------------------------------------------------
# Runtime Switching + Failover (Milestone 11 Task Group E)
# ---------------------------------------------------------------------------
@router.post("/integrations/switch", response_model=Envelope[dict[str, Any]])
async def switch_integration(body: SwitchRequest, request: Request) -> Envelope[dict[str, Any]]:
    """The explicit, user-triggered Runtime Switch -- M11 Task Group E.

    Both *from_integration_id* and *to_integration_id* must already be
    installed, trusted, catalogue-backed integrations; there is no
    field for a URL, a provider class, or a credential, so there is
    nowhere for a caller-supplied destination to go. Never raises for
    an ineligible target (unregistered, incompatible, uncredentialed,
    unauthorized, activation failure) -- those come back as a
    structured, 200-envelope result; only an unknown *from* id (never
    installed at all) is a 404.
    """
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _service(request).switch(
            operation=body.operation,
            from_integration_id=body.from_integration_id,
            to_integration_id=body.to_integration_id,
        )
    except ServiceError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    return envelope(result, meta={"outcome": result["outcome"]})


@router.get("/integrations/failover/history", response_model=Envelope[list[dict[str, Any]]])
async def failover_history(
    request: Request,
    capability: str = Query("", description="Filter to one operation name. Empty means all."),
) -> Envelope[list[dict[str, Any]]]:
    """The last (up to 50) failover attempts, newest first, in-memory
    only. Read-only -- there is no endpoint to *force* a failover; it
    only ever happens as a side effect of
    ``IntegrationService.invoke_with_failover``.
    """
    rows = _service(request).failover_history(capability=capability or None)
    return envelope(rows, meta={"count": len(rows)})


# ---------------------------------------------------------------------------
# Automatic Discovery (Milestone 11 Task Group F)
# ---------------------------------------------------------------------------
@router.post("/integrations/discover", response_model=Envelope[list[dict[str, Any]]])
async def discover_integrations(request: Request) -> Envelope[list[dict[str, Any]]]:
    """Enumerate ``core/integrations/catalogue.py`` -- the only trusted
    source -- and register whichever entries are not yet installed.
    Takes no request body: there is nothing here for a caller to target
    with a URL, a module path, or a package name, because discovery
    never reads anything but the server's own trusted catalogue.

    Never activates, never contacts a vendor. Safe to call repeatedly;
    already-installed entries come back ``"already_registered"``, not
    duplicated.
    """
    results = await _service(request).discover()
    counts: dict[str, int] = {"registered": 0, "already_registered": 0, "rejected": 0}
    for row in results:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return envelope(results, meta={"count": len(results), **counts})
