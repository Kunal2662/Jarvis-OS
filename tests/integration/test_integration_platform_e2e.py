"""Integration Platform end-to-end -- Milestone 11 Task Group E.

Drives the real DI container, the real REST app, the real EventBus, the
real ``RuntimeWebSocketHub``, the real ``SearchService``, the real
``MCPProviderRegistry``, the real ``MCPAuthManager`` and the real
encrypted ``CredentialStore``. The unit tests prove each piece; this
proves they are wired to each other -- and it runs the *whole* OAuth
authorization-code flow, from ``/authorize`` through a browser-style
callback to an authenticated vendor call.

Only the vendor is faked, because only the vendor is unavailable: one
``aiohttp`` server plays both the authorization server (token endpoint)
and the API. A test spec pointed at it is installed through the same
catalogue path a Google integration uses, so nothing about the engine
is special-cased for the test.
"""

from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar
from urllib.parse import parse_qs, urlparse

import pytest

from jarvis.core.integrations.models import AuthSpec, IntegrationSpec, OperationSpec
from jarvis.core.mcp.auth.credentials import AuthMethod
from jarvis.core.mcp.server import principal_for


class _VendorHandler(BaseHTTPRequestHandler):
    """A fake vendor: authorization server and API in one handler."""

    state: ClassVar[dict[str, object]] = {}

    def log_message(self, *args: object) -> None:  # keep pytest output clean
        pass

    def _json(self, payload: dict[str, object], status: int = 200) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # BaseHTTPRequestHandler's own camelCase contract
        parsed = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        if parsed.path.endswith("/messages"):
            self.state["calls"] = int(self.state.get("calls", 0)) + 1
            self.state["last_auth"] = self.headers.get("Authorization", "")
            self._json({"messages": [{"id": "m1", "subject": f"about {query.get('q', '')}"}]})
            return
        self._json({"error": "not found"}, status=404)

    def do_POST(self) -> None:  # BaseHTTPRequestHandler's own camelCase contract
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode()
        parsed = urlparse(self.path)

        if parsed.path == "/oauth/token":
            form = {k: v[0] for k, v in parse_qs(raw).items()}
            self.state["tokens"] = int(self.state.get("tokens", 0)) + 1
            self.state["last_form"] = form
            if form.get("grant_type") == "refresh_token":
                self._json({"access_token": "at-refreshed", "expires_in": 3600})
                return
            if form.get("code") != "the-code":
                self._json({"error": "invalid_grant", "error_description": "bad code"}, status=400)
                return
            self._json(
                {
                    "access_token": "at-1",
                    "refresh_token": "rt-1",
                    "expires_in": 3600,
                    "scope": "vendor.read vendor.send",
                }
            )
            return

        if parsed.path.endswith("/send"):
            self.state["calls"] = int(self.state.get("calls", 0)) + 1
            self._json({"id": "sent-1"})
            return

        if parsed.path == "/oauth/revoke":
            self._json({})
            return

        self._json({"error": "not found"}, status=404)


@pytest.fixture
def vendor():
    """A real HTTP server on a real port, in its own thread.

    A thread rather than this project's usual ``aiohttp_server`` fixture
    for a structural reason: FastAPI's synchronous ``TestClient`` blocks
    the test thread while it drives the app through its own event-loop
    portal, so an ``aiohttp`` server sharing the test's loop would never
    be serviced and every outbound call would time out. A stdlib server
    on its own thread is reachable from whichever loop the request comes
    from -- which is exactly the situation a real vendor is in.
    """
    _VendorHandler.state = {"tokens": 0, "calls": 0, "last_auth": "", "last_form": {}}
    server = ThreadingHTTPServer(("127.0.0.1", 0), _VendorHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    server.state = _VendorHandler.state  # type: ignore[attr-defined]
    server.base_url = f"http://127.0.0.1:{server.server_port}"  # type: ignore[attr-defined]
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _spec(base: str) -> IntegrationSpec:
    return IntegrationSpec(
        integration_id="acme_mail",
        name="Acme Mail",
        vendor="acme",
        description="A fake vendor, for proving the engine end to end.",
        base_url=base,
        auth=AuthSpec(
            method=AuthMethod.OAUTH2,
            authorize_url=f"{base}/oauth/authorize",
            token_url=f"{base}/oauth/token",
            revoke_url=f"{base}/oauth/revoke",
            default_scopes=("vendor.read",),
            authorize_params={"access_type": "offline"},
        ),
        search_operation="messages.search",
        operations=(
            OperationSpec(
                name="messages.search",
                method="GET",
                path="/v1/users/{user_id}/messages",
                description="Search messages.",
                category="search",
                permissions=("network",),
                scopes=("vendor.read",),
                query=("q", "maxResults"),
                required=("q",),
            ),
            OperationSpec(
                name="messages.send",
                method="POST",
                path="/v1/users/{user_id}/messages/send",
                description="Send a message.",
                category="write",
                permissions=("network",),
                scopes=("vendor.send",),
                body=("raw",),
                required=("raw",),
            ),
        ),
    )


@pytest.fixture
def client(tmp_path: Path, vendor, monkeypatch):
    from fastapi.testclient import TestClient

    from jarvis.core.config.settings import Settings
    from jarvis.core.di.container import Container
    from jarvis.core.integrations import catalogue
    from jarvis.infrastructure.api.fastapi_server import create_app

    base = vendor.base_url
    # Installed through the real catalogue path -- nothing about the
    # engine is special-cased for a test vendor.
    monkeypatch.setitem(catalogue.AVAILABLE_SPECS, "acme_mail", lambda: _spec(base))

    container = Container()
    settings = Settings(data_dir=str(tmp_path / "data"))
    settings.db.url = f"sqlite+aiosqlite:///{tmp_path / 'jarvis.db'}"
    settings.integrations.clients = {"acme": {"client_id": "client-1", "client_secret": "shh"}}
    settings.integrations.redirect_uri = "http://127.0.0.1:8765/callback"
    container.settings.override(settings)

    database = container.database()
    asyncio.run(database.initialize())

    app = create_app(settings, container)
    container.runtime_ws_hub().start()

    with TestClient(app) as test_client:
        test_client.container = container  # type: ignore[attr-defined]
        test_client.vendor = vendor  # type: ignore[attr-defined]
        yield test_client

    container.runtime_ws_hub().stop()
    asyncio.run(container.api_gateway().stop())
    asyncio.run(database.dispose())


@pytest.fixture
def auth(client):
    session = client.post("/api/v1/sessions", json={}).json()["data"]
    return {"Authorization": f"Bearer {session['session_id']}"}, session["session_id"]


def _authorize(client, headers) -> str:
    """Run the whole flow and return the integration id, authorized."""
    client.post("/api/v1/integrations", json={"integration_id": "acme_mail"}, headers=headers)
    started = client.post(
        "/api/v1/integrations/oauth/authorize",
        json={"integration_id": "acme_mail"},
        headers=headers,
    ).json()["data"]
    # The browser follows the redirect; no Authorization header.
    client.get(f"/api/v1/integrations/oauth/callback?state={started['state']}&code=the-code")
    return started["state"]


async def _grant(container, *scopes: str) -> None:
    permissions = container.permission_model()
    principal = principal_for("acme_mail")
    permissions.declare(principal, list(scopes))
    for scope in scopes:
        await permissions.grant(principal, scope)


# --- the whole flow -------------------------------------------------------------


def test_the_full_oauth_flow_authorizes_and_stores_a_credential(client, auth) -> None:
    """From /authorize to a stored, encrypted-at-rest credential --
    through the real MCPAuthManager and the real CredentialStore."""
    headers, _ = auth
    client.post("/api/v1/integrations", json={"integration_id": "acme_mail"}, headers=headers)

    started = client.post(
        "/api/v1/integrations/oauth/authorize",
        json={"integration_id": "acme_mail"},
        headers=headers,
    ).json()["data"]
    params = parse_qs(urlparse(started["authorization_url"]).query)
    completed = client.get(
        f"/api/v1/integrations/oauth/callback?state={started['state']}&code=the-code"
    )

    assert params["code_challenge_method"] == ["S256"]
    assert completed.status_code == 200, completed.text
    payload = completed.json()["data"]
    assert payload["credential"]["has_access_token"] is True
    assert payload["granted_scopes"] == ["vendor.read", "vendor.send"]
    # The value itself never appears in a response.
    assert "at-1" not in completed.text


def test_the_token_exchange_sends_pkce_and_the_client_secret(client, auth) -> None:
    headers, _ = auth
    _authorize(client, headers)

    form = client.vendor.state["last_form"]

    assert form["grant_type"] == "authorization_code"
    assert form["client_id"] == "client-1"
    assert form["client_secret"] == "shh"
    assert len(form["code_verifier"]) >= 43


def test_a_bad_code_is_reported_as_a_bad_request(client, auth) -> None:
    headers, _ = auth
    client.post("/api/v1/integrations", json={"integration_id": "acme_mail"}, headers=headers)
    started = client.post(
        "/api/v1/integrations/oauth/authorize",
        json={"integration_id": "acme_mail"},
        headers=headers,
    ).json()["data"]

    response = client.get(
        f"/api/v1/integrations/oauth/callback?state={started['state']}&code=wrong"
    )

    assert response.status_code == 400
    assert "bad code" in response.json()["detail"]


def test_connect_then_invoke_reaches_the_vendor_with_the_token(client, auth) -> None:
    headers, _ = auth
    _authorize(client, headers)
    asyncio.run(_grant(client.container, "network"))

    client.post("/api/v1/integrations/acme_mail/connect", headers=headers)
    body = client.post(
        "/api/v1/integrations/acme_mail/invoke",
        json={"operation": "messages.search", "params": {"user_id": "me", "q": "invoice"}},
        headers=headers,
    ).json()

    assert body["data"]["status_code"] == 200
    assert body["data"]["data"]["messages"][0]["subject"] == "about invoice"
    assert client.vendor.state["last_auth"] == "Bearer at-1"


def test_an_ungranted_permission_stops_the_call_before_egress(client, auth) -> None:
    """The operator never granted 'network', so nothing leaves --
    proved by the vendor's own call counter, not by an assertion on the
    error alone."""
    headers, _ = auth
    _authorize(client, headers)
    calls_before = client.vendor.state["calls"]

    client.post("/api/v1/integrations/acme_mail/connect", headers=headers)
    response = client.post(
        "/api/v1/integrations/acme_mail/invoke",
        json={"operation": "messages.search", "params": {"user_id": "me", "q": "x"}},
        headers=headers,
    )

    assert response.status_code == 400
    assert "permission" in response.json()["detail"]
    assert client.vendor.state["calls"] == calls_before


def test_a_missing_vendor_scope_stops_the_call_before_egress(client, auth) -> None:
    """Gate two, end to end: the token carries vendor.read and
    vendor.send, so an operation needing a scope it does not carry is
    refused. Here the credential is narrowed to prove the gate rather
    than the fixture."""
    headers, _ = auth
    _authorize(client, headers)
    asyncio.run(_grant(client.container, "network"))
    store = client.container.mcp_credential_store()
    from dataclasses import replace

    store.put(replace(store.get("acme_mail"), scopes=("vendor.read",)), persist=False)
    client.post("/api/v1/integrations/acme_mail/connect", headers=headers)
    calls_before = client.vendor.state["calls"]

    response = client.post(
        "/api/v1/integrations/acme_mail/invoke",
        json={"operation": "messages.send", "params": {"user_id": "me", "raw": "hi"}},
        headers=headers,
    )

    assert response.status_code == 400
    assert "provider scope" in response.json()["detail"]
    assert client.vendor.state["calls"] == calls_before


# --- wiring into the existing platform ------------------------------------------


def test_an_integration_is_a_provider_in_the_shared_mcp_registry(client, auth) -> None:
    """Not a parallel registry: `/api/v1/mcp/providers` reports it, and
    `/api/v1/mcp/diagnostics` inspects it."""
    headers, _ = auth
    _authorize(client, headers)

    providers = client.get("/api/v1/mcp/providers", headers=headers).json()["data"]
    diagnostics = client.get("/api/v1/mcp/diagnostics", headers=headers).json()["data"]

    assert "acme_mail" in {row["provider_id"] for row in providers}
    assert "acme_mail" in str(diagnostics)


def test_integration_health_rides_the_existing_collector(client, auth) -> None:
    """One health channel -- M9's HealthMonitor collector, through the
    provider manager that already feeds it."""
    headers, _ = auth
    _authorize(client, headers)
    asyncio.run(_grant(client.container, "network"))
    client.post("/api/v1/integrations/acme_mail/connect", headers=headers)

    health = asyncio.run(client.container.mcp_provider_manager().collect_health())
    row = next(r for r in health["providers"] if r["provider_id"] == "acme_mail")

    assert row["healthy"] is True
    assert "acme_mail" in health["connected"]


def test_authorizing_registers_in_the_shared_auth_surface(client, auth) -> None:
    headers, _ = auth
    _authorize(client, headers)

    rows = client.get("/api/v1/mcp/auth", headers=headers).json()["data"]
    acme = next(row for row in rows if row["provider_id"] == "acme_mail")

    assert acme["authenticated"] is True
    assert acme["credential"]["method"] == "oauth2"
    # The public dict reports *whether* a token exists, never its value.
    assert acme["credential"]["has_access_token"] is True
    assert "at-1" not in str(acme)
    assert "rt-1" not in str(acme)


def test_oauth2_is_now_a_supported_method(client, auth) -> None:
    """M10.5 shipped the vocabulary with both grants unsupported. This
    milestone's whole authentication story is that they now are."""
    headers, _ = auth

    methods = {
        row["method"]: row
        for row in client.get("/api/v1/mcp/auth/methods", headers=headers).json()["data"]
    }

    assert methods["oauth2"]["supported"] is True
    assert methods["client_credentials"]["supported"] is True


def test_connecting_registers_a_search_source_and_disconnecting_removes_it(client, auth) -> None:
    """M10A's provider registry working as designed -- the first source
    with a runtime lifetime, and no change to SearchService."""
    headers, _ = auth
    _authorize(client, headers)
    asyncio.run(_grant(client.container, "network"))
    search = client.container.search_service()

    before = {s.source_type for s in search.get_sources()}
    client.post("/api/v1/integrations/acme_mail/connect", headers=headers)
    connected = {s.source_type for s in search.get_sources()}
    client.post("/api/v1/integrations/acme_mail/disconnect", headers=headers)
    after = {s.source_type for s in search.get_sources()}

    assert "integration:acme_mail" not in before
    assert "integration:acme_mail" in connected
    assert "integration:acme_mail" not in after
    # Everything Task Groups A-D registered is untouched.
    assert {"workspaces", "notes", "tasks", "files"} <= after


def test_vendor_results_reach_universal_search(client, auth) -> None:
    """A connected vendor's own search endpoint answers through the
    shared SearchService, alongside every local source."""
    headers, _ = auth
    _authorize(client, headers)
    asyncio.run(_grant(client.container, "network"))
    client.post("/api/v1/integrations/acme_mail/connect", headers=headers)

    results = asyncio.run(client.container.search_service().search("invoice", top_k=20))
    vendor_hits = [r for r in results if r.source == "integration:acme_mail"]

    assert vendor_hits
    assert vendor_hits[0].title == "about invoice"
    assert vendor_hits[0].uri.startswith("integration://acme_mail/")


def test_the_call_audit_event_reaches_a_websocket_subscriber(client, auth) -> None:
    """One EventBus, one relay -- the audited egress point's trail."""
    headers, token = auth
    _authorize(client, headers)
    asyncio.run(_grant(client.container, "network"))
    client.post("/api/v1/integrations/acme_mail/connect", headers=headers)

    with client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
        client.post(
            "/api/v1/integrations/acme_mail/invoke",
            json={"operation": "messages.search", "params": {"user_id": "me", "q": "hi"}},
            headers=headers,
        )
        frame = ws.receive_json()

    assert frame["type"] == "integration.call_completed"
    assert frame["payload"]["integration_id"] == "acme_mail"
    assert frame["payload"]["operation"] == "messages.search"
    assert frame["payload"]["ok"] is True


def test_the_audit_event_carries_no_response_body(client, auth) -> None:
    """A response body is someone's inbox; relaying it would put that in
    every connected client's replay buffer."""
    headers, token = auth
    _authorize(client, headers)
    asyncio.run(_grant(client.container, "network"))
    client.post("/api/v1/integrations/acme_mail/connect", headers=headers)

    with client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
        client.post(
            "/api/v1/integrations/acme_mail/invoke",
            json={"operation": "messages.search", "params": {"user_id": "me", "q": "secret"}},
            headers=headers,
        )
        frame = ws.receive_json()

    assert "secret" not in str(frame["payload"])
    assert "messages" not in frame["payload"]


def test_the_agent_registry_grew_the_integration_tools(client) -> None:
    """External vendors reach the agent through the existing tool
    registry, not a second orchestrator."""
    from jarvis.agents.tools import build_tool_registry

    tools = build_tool_registry(integrations=client.container.integration_service())

    assert {t.name for t in tools} == {
        "list_integrations",
        "describe_integration",
        "search_integration",
        "invoke_integration",
    }


def test_an_agent_tool_invokes_through_the_same_gates(client, auth) -> None:
    from jarvis.agents.tools import build_tool_registry

    headers, _ = auth
    _authorize(client, headers)
    client.post("/api/v1/integrations/acme_mail/connect", headers=headers)
    tools = {
        t.name: t for t in build_tool_registry(integrations=client.container.integration_service())
    }

    # Connected and authorized, but the operator never granted
    # 'network' -- the tool reports the refusal as text rather than
    # raising, and nothing leaves.
    refused = asyncio.run(
        tools["invoke_integration"].ainvoke(
            {
                "integration_id": "acme_mail",
                "operation": "messages.search",
                "params": {"user_id": "me", "q": "x"},
            }
        )
    )

    assert "permission" in refused


# --- caching and revocation -----------------------------------------------------


def test_a_repeated_read_is_served_from_the_gateway_cache(client, auth) -> None:
    headers, _ = auth
    _authorize(client, headers)
    asyncio.run(_grant(client.container, "network"))
    client.post("/api/v1/integrations/acme_mail/connect", headers=headers)
    body = {"operation": "messages.search", "params": {"user_id": "me", "q": "invoice"}}

    client.post("/api/v1/integrations/acme_mail/invoke", json=body, headers=headers)
    calls_after_first = client.vendor.state["calls"]
    second = client.post("/api/v1/integrations/acme_mail/invoke", json=body, headers=headers).json()

    assert second["meta"]["from_cache"] is True
    assert client.vendor.state["calls"] == calls_after_first


def test_revoking_clears_the_credential_and_disconnects(client, auth) -> None:
    headers, _ = auth
    _authorize(client, headers)
    asyncio.run(_grant(client.container, "network"))
    client.post("/api/v1/integrations/acme_mail/connect", headers=headers)

    revoked = client.delete("/api/v1/integrations/acme_mail/credential", headers=headers)
    status = client.get("/api/v1/integrations/acme_mail", headers=headers).json()["data"]

    assert revoked.status_code == 204
    assert status["auth"]["authenticated"] is False
    assert status["state"] == "disconnected"


def test_a_revoked_integration_cannot_call(client, auth) -> None:
    headers, _ = auth
    _authorize(client, headers)
    asyncio.run(_grant(client.container, "network"))
    client.post("/api/v1/integrations/acme_mail/connect", headers=headers)
    client.delete("/api/v1/integrations/acme_mail/credential", headers=headers)
    calls_before = client.vendor.state["calls"]

    response = client.post(
        "/api/v1/integrations/acme_mail/invoke",
        json={"operation": "messages.search", "params": {"user_id": "me", "q": "x"}},
        headers=headers,
    )

    assert response.status_code == 400
    assert client.vendor.state["calls"] == calls_before
