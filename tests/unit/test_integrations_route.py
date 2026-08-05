"""Integration Platform REST tests -- Milestone 11 Task Group E.

Against the real FastAPI app and the real DI container, matching
``test_ai_workspace_route.py``. Nothing here reaches a vendor: the
routes under test are the catalogue, install, authorization and
refusal paths, all of which are supposed to work without one.

The callback tests are security tests. Exactly one route in this
application is session-free, and these pin both halves of that: that it
*is* reachable without a Bearer token (otherwise the flow could never
complete) and that ``state`` is what makes it safe -- unknown, replayed
and expired values are all refused.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest


@pytest.fixture
def client(tmp_path: Path):
    from fastapi.testclient import TestClient

    from jarvis.core.config.settings import Settings
    from jarvis.core.di.container import Container
    from jarvis.infrastructure.api.fastapi_server import create_app

    container = Container()
    settings = Settings(data_dir=str(tmp_path / "data"))
    settings.db.url = f"sqlite+aiosqlite:///{tmp_path / 'jarvis.db'}"
    # A configured OAuth client, so the authorize route can be exercised
    # without reaching Google.
    settings.integrations.clients = {
        "google": {"client_id": "test-client", "client_secret": "test-secret"}
    }
    container.settings.override(settings)

    database = container.database()
    asyncio.run(database.initialize())

    app = create_app(settings, container)
    with TestClient(app) as test_client:
        test_client.container = container  # type: ignore[attr-defined]
        yield test_client

    asyncio.run(database.dispose())


@pytest.fixture
def auth(client):
    session = client.post("/api/v1/sessions", json={}).json()["data"]
    return {"Authorization": f"Bearer {session['session_id']}"}


def _install(client, auth, integration_id: str = "google_gmail"):
    return client.post(
        "/api/v1/integrations", json={"integration_id": integration_id}, headers=auth
    )


# --- auth + envelope ------------------------------------------------------------


def test_the_authenticated_routes_require_a_session(client) -> None:
    for path in (
        "/api/v1/integrations",
        "/api/v1/integrations/catalogue",
        "/api/v1/integrations/gateway/stats",
    ):
        assert client.get(path).status_code in (401, 403)


def test_responses_use_the_documented_envelope(client, auth) -> None:
    body = client.get("/api/v1/integrations/catalogue", headers=auth).json()

    assert set(body) == {"data", "meta"}
    assert body["meta"]["count"] == len(body["data"])


# --- catalogue ------------------------------------------------------------------


def test_the_catalogue_lists_phase_one(client, auth) -> None:
    entries = client.get("/api/v1/integrations/catalogue", headers=auth).json()["data"]
    ids = {row["integration_id"] for row in entries}

    assert "google_gmail" in ids
    assert {row["vendor"] for row in entries} == {"google"}


def test_the_catalogue_surfaces_availability_notes(client, auth) -> None:
    """So a caller learns Keep is enterprise-only *before* spending an
    OAuth round trip finding out."""
    entries = client.get("/api/v1/integrations/catalogue", headers=auth).json()["data"]
    keep = next(row for row in entries if row["integration_id"] == "google_keep")

    assert "Workspace" in keep["availability_note"]


def test_one_integration_can_be_described_in_full(client, auth) -> None:
    body = client.get("/api/v1/integrations/catalogue/google_gmail", headers=auth).json()

    assert body["data"]["name"] == "Gmail"
    assert len(body["data"]["operations"]) == 12
    assert body["data"]["required_permissions"] == ["network"]


def test_an_unknown_integration_is_a_404(client, auth) -> None:
    response = client.get("/api/v1/integrations/catalogue/microsoft_teams", headers=auth)

    assert response.status_code == 404
    assert "Available" in response.json()["detail"]


# --- install / lifecycle --------------------------------------------------------


def test_installing_registers_an_mcp_provider(client, auth) -> None:
    """Not a parallel registry -- the same one `/api/v1/mcp/providers`
    reports."""
    created = _install(client, auth)
    providers = client.get("/api/v1/mcp/providers", headers=auth).json()["data"]

    assert created.status_code == 201
    assert created.json()["data"]["metadata"]["transport"] == "http"
    assert "google_gmail" in {row["provider_id"] for row in providers}


def test_installing_declares_permissions_as_pending_and_grants_nothing(client, auth) -> None:
    _install(client, auth)
    status = client.get("/api/v1/integrations/google_gmail", headers=auth).json()["data"]

    assert status["pending_permissions"] == ["network"]
    assert status["granted_permissions"] == []


def test_installing_makes_no_network_call(client, auth) -> None:
    """An install is cheap and reversible, which is what lets an
    approval screen show what a connector would do first."""
    _install(client, auth)
    stats = client.get("/api/v1/integrations/gateway/stats", headers=auth).json()["data"]

    assert stats["calls"] == 0
    assert stats["open"] is False


def test_installing_twice_without_replace_is_a_400(client, auth) -> None:
    _install(client, auth)
    assert _install(client, auth).status_code == 400


def test_installing_an_unknown_integration_is_a_400(client, auth) -> None:
    response = client.post(
        "/api/v1/integrations", json={"integration_id": "acme_mail"}, headers=auth
    )
    assert response.status_code == 400


def test_installed_integrations_are_listed(client, auth) -> None:
    _install(client, auth)
    _install(client, auth, "google_drive")

    body = client.get("/api/v1/integrations", headers=auth).json()

    assert body["meta"]["count"] == 2
    assert {row["provider_id"] for row in body["data"]} == {"google_gmail", "google_drive"}


def test_connecting_without_a_credential_is_a_400(client, auth) -> None:
    _install(client, auth)

    response = client.post("/api/v1/integrations/google_gmail/connect", headers=auth)

    assert response.status_code == 400
    assert "credential" in response.json()["detail"]


def test_uninstalling_removes_the_provider(client, auth) -> None:
    _install(client, auth)

    assert client.delete("/api/v1/integrations/google_gmail", headers=auth).status_code == 204
    assert client.get("/api/v1/integrations/google_gmail", headers=auth).status_code == 404


def test_uninstalling_something_absent_is_a_404(client, auth) -> None:
    assert client.delete("/api/v1/integrations/google_gmail", headers=auth).status_code == 404


# --- authorization --------------------------------------------------------------


def test_authorize_returns_a_url_with_pkce_and_state(client, auth) -> None:
    from urllib.parse import parse_qs, urlparse

    body = client.post(
        "/api/v1/integrations/oauth/authorize",
        json={"integration_id": "google_gmail"},
        headers=auth,
    ).json()

    params = parse_qs(urlparse(body["data"]["authorization_url"]).query)
    assert params["code_challenge_method"] == ["S256"]
    assert params["state"] == [body["data"]["state"]]
    assert params["access_type"] == ["offline"]
    assert body["meta"]["pkce"] == "S256"


def test_the_authorize_response_never_carries_the_verifier(client, auth) -> None:
    """Returning it would defeat the exchange it protects."""
    body = client.post(
        "/api/v1/integrations/oauth/authorize",
        json={"integration_id": "google_gmail"},
        headers=auth,
    ).json()

    assert "code_verifier" not in str(body)


def test_authorizing_without_a_configured_client_names_the_setting(client, auth) -> None:
    client.container.settings().integrations.clients = {}

    response = client.post(
        "/api/v1/integrations/oauth/authorize",
        json={"integration_id": "google_gmail"},
        headers=auth,
    )

    assert response.status_code == 400
    assert "CLIENT_ID" in response.json()["detail"]


# --- the callback: the one session-free route -----------------------------------


def test_the_callback_is_reachable_without_a_session(client) -> None:
    """A browser redirect carries no Authorization header and cannot be
    made to. Requiring one would mean the flow could never complete --
    so this must not be a 401."""
    response = client.get("/api/v1/integrations/oauth/callback?state=whatever&code=x")

    assert response.status_code not in (401, 403)


def test_an_unknown_state_is_refused(client) -> None:
    """`state` is what proves the response belongs to a flow this
    process started."""
    response = client.get("/api/v1/integrations/oauth/callback?state=forged&code=x")

    assert response.status_code == 400
    assert "Unknown or already-used" in response.json()["detail"]


def test_a_replayed_state_is_refused(client, auth) -> None:
    """Single-use. The first attempt consumes it even though the token
    exchange then fails against a Google that is not there."""
    state = client.post(
        "/api/v1/integrations/oauth/authorize",
        json={"integration_id": "google_gmail"},
        headers=auth,
    ).json()["data"]["state"]

    client.get(f"/api/v1/integrations/oauth/callback?state={state}&code=first")
    second = client.get(f"/api/v1/integrations/oauth/callback?state={state}&code=second")

    assert second.status_code == 400
    assert "Unknown or already-used" in second.json()["detail"]


def test_a_callback_without_a_code_is_refused(client) -> None:
    response = client.get("/api/v1/integrations/oauth/callback?state=s")

    assert response.status_code == 400
    assert "no code" in response.json()["detail"]


def test_a_vendor_error_is_reported_as_a_bad_request_not_a_500(client) -> None:
    """The user declining is not a server fault."""
    response = client.get("/api/v1/integrations/oauth/callback?state=s&error=access_denied")

    assert response.status_code == 400
    assert "access_denied" in response.json()["detail"]


def test_a_missing_state_is_a_validation_error(client) -> None:
    assert client.get("/api/v1/integrations/oauth/callback?code=x").status_code == 422


# --- invoke / preview -----------------------------------------------------------


def test_invoking_an_uninstalled_integration_is_a_400(client, auth) -> None:
    response = client.post(
        "/api/v1/integrations/google_gmail/invoke",
        json={"operation": "messages.list", "params": {"user_id": "me"}},
        headers=auth,
    )

    assert response.status_code == 400
    assert "not installed" in response.json()["detail"]


def test_preview_resolves_the_request_without_sending_it(client, auth) -> None:
    _install(client, auth)

    body = client.post(
        "/api/v1/integrations/google_gmail/preview",
        json={"operation": "messages.list", "params": {"user_id": "me", "q": "invoice"}},
        headers=auth,
    ).json()

    assert body["data"]["url"].endswith("/gmail/v1/users/me/messages")
    assert body["data"]["query_keys"] == ["q"]
    stats = client.get("/api/v1/integrations/gateway/stats", headers=auth).json()["data"]
    assert stats["calls"] == 0


def test_preview_omits_headers_because_one_of_them_is_the_token(client, auth) -> None:
    _install(client, auth)

    body = client.post(
        "/api/v1/integrations/google_gmail/preview",
        json={"operation": "messages.list", "params": {"user_id": "me"}},
        headers=auth,
    ).json()

    assert "headers" not in body["data"]
    assert "Authorization" not in str(body)


def test_preview_refuses_an_undeclared_parameter(client, auth) -> None:
    _install(client, auth)

    response = client.post(
        "/api/v1/integrations/google_gmail/preview",
        json={"operation": "messages.list", "params": {"user_id": "me", "impersonate": "x"}},
        headers=auth,
    )

    assert response.status_code == 400
    assert "does not accept parameter" in response.json()["detail"]


def test_preview_refuses_a_missing_path_parameter(client, auth) -> None:
    _install(client, auth)

    response = client.post(
        "/api/v1/integrations/google_gmail/preview",
        json={"operation": "messages.get", "params": {"user_id": "me"}},
        headers=auth,
    )

    assert response.status_code == 400
    assert "path parameter" in response.json()["detail"]


# --- diagnostics ----------------------------------------------------------------


def test_gateway_stats_report_egress_counters(client, auth) -> None:
    body = client.get("/api/v1/integrations/gateway/stats", headers=auth).json()

    assert set(body["data"]) >= {"calls", "failures", "retries", "cache_hits", "open"}


def test_integrations_appear_in_mcp_health(client, auth) -> None:
    """One health channel: an integration is an MCP provider, so it is
    already in the provider manager's collector."""
    _install(client, auth)

    health = asyncio.run(client.container.mcp_provider_manager().collect_health())

    assert "google_gmail" in {row["provider_id"] for row in health["providers"]}
