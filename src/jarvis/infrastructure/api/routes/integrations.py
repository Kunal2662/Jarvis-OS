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


@router.get("/integrations/{integration_id}", response_model=Envelope[dict[str, Any]])
async def integration_status(integration_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        return envelope(await _service(request).status(integration_id))
    except ServiceError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err


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
