"""End-to-end Authentication Framework test -- Milestone 10.5 Task
Group D.

Drives the real auth manager through the real DI container, against the
real M9 ``PermissionModel``, with a real Fernet key and real on-disk
encryption -- and asserts the lifecycle events reach a real WebSocket
subscriber while never carrying a token.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

_TOKEN = "tok_SUPER_SECRET_VALUE"


@pytest.fixture
def secret_key() -> str:
    return Fernet.generate_key().decode()


@pytest.fixture
def client(tmp_path: Path, secret_key: str):
    from fastapi.testclient import TestClient

    from jarvis.core.config.settings import Settings
    from jarvis.core.di.container import Container
    from jarvis.infrastructure.api.fastapi_server import create_app

    container = Container()
    settings = Settings(data_dir=str(tmp_path / "data"))
    settings.db.url = f"sqlite+aiosqlite:///{tmp_path / 'jarvis.db'}"
    settings.security.secret_key = type(settings.security.secret_key)(secret_key)
    container.settings.override(settings)

    database = container.database()
    asyncio.run(database.initialize())

    app = create_app(settings, container)
    container.runtime_ws_hub().start()

    with TestClient(app) as test_client:
        test_client.container = container  # type: ignore[attr-defined]
        test_client.data_dir = tmp_path / "data"  # type: ignore[attr-defined]
        yield test_client

    asyncio.run(database.dispose())


@pytest.fixture
def auth_headers(client):
    session = client.post("/api/v1/sessions", json={}).json()["data"]
    return {"Authorization": f"Bearer {session['session_id']}"}, session["session_id"]


def test_credential_is_encrypted_on_disk_through_the_real_container(client) -> None:
    """The security contract, end to end: a token written through the
    DI-provided store never appears in the file."""
    from jarvis.core.mcp.auth.credentials import AuthMethod

    manager = client.container.mcp_auth_manager()
    asyncio.run(manager.authenticate("demo", AuthMethod.API_KEY, {"token": _TOKEN}))

    store_file = client.data_dir / "config" / "mcp_credentials.json"
    raw = store_file.read_text(encoding="utf-8")

    assert store_file.exists()
    assert _TOKEN not in raw
    assert "demo" in raw  # metadata stays readable


def test_credential_survives_a_restart_and_decrypts(
    client, tmp_path: Path, secret_key: str
) -> None:
    """A second store over the same file with the same key recovers the
    token -- proving real persistence, not in-memory state."""
    from jarvis.core.mcp.auth.credentials import AuthMethod
    from jarvis.core.mcp.auth.store import CredentialStore

    manager = client.container.mcp_auth_manager()
    asyncio.run(manager.authenticate("demo", AuthMethod.API_KEY, {"token": _TOKEN}))

    reopened = CredentialStore(
        client.data_dir / "config" / "mcp_credentials.json", secret_key=secret_key
    )
    credential = reopened.get("demo")

    assert credential is not None
    assert credential.access_token == _TOKEN


def test_full_lifecycle_with_the_real_permission_model(client) -> None:
    """authenticate -> both permission gates -> revoke, against the real
    ``PermissionModel`` and the real encrypted store."""
    from jarvis.core.mcp.auth.credentials import AuthMethod
    from jarvis.core.mcp.server import principal_for

    container = client.container
    manager = container.mcp_auth_manager()
    permissions = container.permission_model()

    asyncio.run(
        manager.authenticate("demo", AuthMethod.API_KEY, {"token": _TOKEN, "scopes": ["repo:read"]})
    )

    # Gate 1 refuses until the operator grants the JARVIS-side scope.
    allowed, reason = manager.authorize_capability(
        "demo", required_permissions=("network",), required_scopes=("repo:read",)
    )
    assert allowed is False
    assert "JARVIS permission" in reason

    asyncio.run(permissions.grant(principal_for("demo"), "network"))
    allowed, _ = manager.authorize_capability(
        "demo", required_permissions=("network",), required_scopes=("repo:read",)
    )
    assert allowed is True

    # Gate 2 still refuses a scope the token does not carry, regardless.
    allowed, reason = manager.authorize_capability(
        "demo", required_permissions=("network",), required_scopes=("admin",)
    )
    assert allowed is False
    assert "provider scope" in reason

    assert asyncio.run(manager.revoke("demo")) is True
    assert manager.validate("demo") is False


def test_lifecycle_events_relay_over_the_real_websocket(client, auth_headers) -> None:
    from jarvis.core.mcp.auth.credentials import AuthMethod

    _headers, token = auth_headers
    manager = client.container.mcp_auth_manager()

    with client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
        asyncio.run(manager.authenticate("demo", AuthMethod.API_KEY, {"token": _TOKEN}))
        asyncio.run(manager.revoke("demo"))

        messages = [ws.receive_json() for _ in range(5)]

    assert [m["type"] for m in messages] == ["mcp.auth_changed"] * 5
    assert [m["payload"]["action"] for m in messages] == [
        "authentication_started",
        "authentication_completed",
        "provider_authenticated",
        "credential_revoked",
        "provider_disconnected",
    ]
    # The relay reaches remote subscribers -- a token here would be a leak.
    assert all(_TOKEN not in str(m) for m in messages)


def test_expiry_is_announced_through_the_health_sweep(client, auth_headers) -> None:
    """Expiry detection rides the existing health poll rather than a
    second timer -- and reaches the relay when it fires."""
    from jarvis.core.mcp.auth.credentials import AuthMethod, Credential

    _headers, token = auth_headers
    container = client.container
    container.mcp_credential_store().put(
        Credential(
            provider_id="stale",
            method=AuthMethod.BEARER_TOKEN,
            access_token=_TOKEN,
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
    )

    with client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
        health = asyncio.run(container.mcp_auth_manager().collect_health())
        message = ws.receive_json()

    assert health["expired"] == ["stale"]
    assert message["type"] == "mcp.auth_changed"
    assert message["payload"]["action"] == "token_expired"


def test_auth_health_joins_the_existing_health_snapshot(client) -> None:
    """One health channel -- M9's ``HealthMonitor`` collector, not a
    second subsystem."""
    from jarvis.core.mcp.auth.credentials import AuthMethod

    container = client.container
    manager = container.mcp_auth_manager()
    health_monitor = container.health_monitor()
    asyncio.run(manager.authenticate("demo", AuthMethod.API_KEY, {"token": _TOKEN}))

    health_monitor.register_collector("mcp_auth", manager.collect_health)
    snapshot = asyncio.run(health_monitor.snapshot())

    assert snapshot["mcp_auth"]["count"] == 1
    assert snapshot["mcp_auth"]["authenticated"] == ["demo"]
    assert snapshot["mcp_auth"]["can_persist"] is True
    assert _TOKEN not in str(snapshot)


def test_rest_reflects_the_live_authentication_state(client, auth_headers) -> None:
    from jarvis.core.mcp.auth.credentials import AuthMethod

    headers, _token = auth_headers
    manager = client.container.mcp_auth_manager()
    asyncio.run(
        manager.authenticate(
            "demo", AuthMethod.PERSONAL_ACCESS_TOKEN, {"token": _TOKEN, "scopes": ["a"]}
        )
    )

    listing = client.get("/api/v1/mcp/auth", headers=headers).json()
    status = client.get("/api/v1/mcp/auth/demo/status", headers=headers).json()

    assert listing["meta"]["count"] == 1
    assert status["data"]["authenticated"] is True
    assert status["data"]["credential_status"] == "active"
    assert _TOKEN not in client.get("/api/v1/mcp/auth", headers=headers).text


def test_a_provider_with_no_credential_is_authenticated_by_definition(client) -> None:
    """A local stdio peer needs nothing -- modelling that as a real
    state avoids a fake empty credential standing in for it."""
    from jarvis.core.mcp.auth.credentials import AuthMethod

    manager = client.container.mcp_auth_manager()
    asyncio.run(manager.authenticate("local-peer", AuthMethod.NONE, {}))

    assert manager.validate("local-peer") is True
    allowed, _ = manager.authorize_capability("local-peer")
    assert allowed is True
