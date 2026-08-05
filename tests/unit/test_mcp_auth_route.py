"""Authentication REST route tests -- Milestone 10.5 Task Group D,
deliverables 9 and 10.

The "never leaks a token" assertions run against the real response body
text, not a parsed field -- a leak anywhere in the payload fails them.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

pytest.importorskip("langgraph")
pytest.importorskip("langchain_core")

_TOKEN = "tok_SUPER_SECRET_VALUE"


@pytest.fixture
def client(tmp_path: Path):
    from fastapi.testclient import TestClient

    from jarvis.core.config.settings import Settings
    from jarvis.core.di.container import Container
    from jarvis.infrastructure.api.fastapi_server import create_app

    container = Container()
    settings = Settings(data_dir=str(tmp_path / "data"))
    settings.db.url = f"sqlite+aiosqlite:///{tmp_path / 'jarvis.db'}"
    settings.security.secret_key = type(settings.security.secret_key)(
        Fernet.generate_key().decode()
    )
    container.settings.override(settings)

    database = container.database()
    asyncio.run(database.initialize())

    app = create_app(settings, container)
    with TestClient(app) as test_client:
        test_client.container = container  # type: ignore[attr-defined]
        yield test_client

    asyncio.run(database.dispose())


@pytest.fixture
def auth_headers(client):
    session = client.post("/api/v1/sessions", json={}).json()["data"]
    return {"Authorization": f"Bearer {session['session_id']}"}


def _authenticate(container, provider_id: str = "demo", **kwargs):
    from jarvis.core.mcp.auth.credentials import AuthMethod

    return asyncio.run(
        container.mcp_auth_manager().authenticate(
            provider_id,
            kwargs.pop("method", AuthMethod.API_KEY),
            {"token": kwargs.pop("token", _TOKEN), **kwargs},
        )
    )


# --- Auth gate -----------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/mcp/auth",
        "/api/v1/mcp/auth/methods",
        "/api/v1/mcp/auth/demo",
        "/api/v1/mcp/auth/demo/status",
    ],
)
def test_every_auth_route_requires_a_session(client, path: str) -> None:
    assert client.get(path).status_code == 401


# --- Listing --------------------------------------------------------------------


def test_auth_list_starts_empty(client, auth_headers) -> None:
    body = client.get("/api/v1/mcp/auth", headers=auth_headers).json()

    assert body["data"] == []
    assert body["meta"]["count"] == 0
    assert body["meta"]["can_persist"] is True


def test_auth_list_reports_an_authenticated_provider(client, auth_headers) -> None:
    _authenticate(client.container, scopes=["repo:read"])

    body = client.get("/api/v1/mcp/auth", headers=auth_headers).json()

    assert body["meta"]["count"] == 1
    entry = body["data"][0]
    assert entry["provider_id"] == "demo"
    assert entry["authenticated"] is True
    assert entry["credential"]["has_access_token"] is True
    assert entry["credential"]["scopes"] == ["repo:read"]


def test_methods_endpoint_reports_supported_versus_known(client, auth_headers) -> None:
    """Every method in the vocabulary is now supported.

    This test previously pinned the *opposite* for ``oauth2`` and
    ``client_credentials``: M10.5 Task Group D shipped the vocabulary
    with both unimplemented, because each needs an authorization server,
    a redirect URI and a callback endpoint that task group did not
    build. M11 Task Group E built all three
    (``core/mcp/auth/oauth2.py``), so the assertion flips -- which is
    the deferral closing, not a regression.
    """
    body = client.get("/api/v1/mcp/auth/methods", headers=auth_headers).json()
    described = {d["method"]: d for d in body["data"]}

    assert described["api_key"]["supported"] is True
    assert described["oauth2"]["supported"] is True
    assert described["client_credentials"]["supported"] is True
    # Refreshability is a property of the method, not of whether this
    # build implements it, so it was already true before Task Group E.
    assert described["oauth2"]["refreshable"] is True
    assert body["meta"]["count"] == 6


# --- Detail / status ------------------------------------------------------------


def test_detail_reports_session_and_credential(client, auth_headers) -> None:
    _authenticate(client.container)

    body = client.get("/api/v1/mcp/auth/demo", headers=auth_headers).json()

    assert body["data"]["session"]["state"] == "active"
    assert body["data"]["credential"]["method"] == "api_key"
    assert body["data"]["authenticated"] is True


def test_status_is_the_compact_liveness_answer(client, auth_headers) -> None:
    _authenticate(client.container)

    body = client.get("/api/v1/mcp/auth/demo/status", headers=auth_headers).json()

    assert body["data"]["authenticated"] is True
    assert body["data"]["credential_status"] == "active"
    assert body["data"]["is_refreshable"] is False
    assert body["meta"]["healthy"] is True


def test_status_explains_an_expired_credential(client, auth_headers) -> None:
    from datetime import UTC, datetime, timedelta

    from jarvis.core.mcp.auth.credentials import AuthMethod, Credential

    client.container.mcp_credential_store().put(
        Credential(
            provider_id="stale",
            method=AuthMethod.BEARER_TOKEN,
            access_token=_TOKEN,
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
    )

    body = client.get("/api/v1/mcp/auth/stale/status", headers=auth_headers).json()

    assert body["data"]["authenticated"] is False
    assert body["data"]["credential_status"] == "expired"
    assert body["meta"]["healthy"] is False


@pytest.mark.parametrize("suffix", ["", "/status"])
def test_unknown_provider_is_404(client, auth_headers, suffix: str) -> None:
    assert client.get(f"/api/v1/mcp/auth/nope{suffix}", headers=auth_headers).status_code == 404


# --- The security contract ------------------------------------------------------


@pytest.mark.parametrize(
    "path", ["/api/v1/mcp/auth", "/api/v1/mcp/auth/demo", "/api/v1/mcp/auth/demo/status"]
)
def test_no_route_ever_returns_a_token(client, auth_headers, path: str) -> None:
    """The single most important assertion in this task group."""
    _authenticate(client.container)

    body = client.get(path, headers=auth_headers).text

    assert _TOKEN not in body


def test_refresh_tokens_are_not_exposed_either(client, auth_headers) -> None:
    from jarvis.core.mcp.auth.credentials import AuthMethod, Credential

    client.container.mcp_credential_store().put(
        Credential(
            provider_id="oauthy",
            method=AuthMethod.OAUTH2,
            access_token="access_SECRET",
            refresh_token="refresh_SECRET",
        )
    )

    body = client.get("/api/v1/mcp/auth", headers=auth_headers).text

    assert "access_SECRET" not in body
    assert "refresh_SECRET" not in body
    # But their existence is reported.
    assert '"has_refresh_token":true' in body.replace(" ", "")


# --- DI --------------------------------------------------------------------------


def test_auth_services_are_singletons(client) -> None:
    container = client.container

    assert container.mcp_auth_manager() is container.mcp_auth_manager()
    assert container.mcp_credential_store() is container.mcp_credential_store()
    assert container.mcp_auth_strategies() is container.mcp_auth_strategies()


def test_store_uses_the_configured_app_secret_key(client) -> None:
    """The framework reuses the app's own Fernet key rather than
    managing a second one."""
    assert client.container.mcp_credential_store().can_persist is True
