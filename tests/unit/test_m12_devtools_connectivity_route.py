"""Developer Tools -- Connectivity / Integration Health REST tests --
Milestone 12 Developer Tools (Connectivity / Integration Health
Slice).

Against the real FastAPI app and the real DI container, matching
every other M12 route test's pattern. No permission grant is involved
anywhere in this file -- this route has no `PermissionModel` gate, by
deliberate design (Logic Contract §8), matching every other devtools
route.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest


@pytest.fixture
def fake_connector():
    from tests.fakes.fake_device_connector import FakeDeviceConnector

    return FakeDeviceConnector()


@pytest.fixture
def client(tmp_path: Path, fake_connector):
    from fastapi.testclient import TestClient

    from jarvis.core.config.settings import Settings
    from jarvis.core.connectivity.registry import ConnectorFactoryRegistry
    from jarvis.core.di.container import Container
    from jarvis.infrastructure.api.fastapi_server import create_app

    container = Container()
    settings = Settings(data_dir=str(tmp_path / "data"))
    settings.db.url = f"sqlite+aiosqlite:///{tmp_path / 'jarvis.db'}"
    container.settings.override(settings)

    registry = ConnectorFactoryRegistry()
    registry.register("home_assistant", lambda config: fake_connector)
    container.connectivity_registry.override(registry)

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


def _home(client, auth, name: str = "Primary Residence") -> str:
    response = client.post("/api/v1/homes", json={"name": name}, headers=auth)
    assert response.status_code == 201
    return response.json()["data"]["id"]


def _connect(client, auth) -> None:
    client.post(
        "/api/v1/connectivity/connectors/home_assistant/connect", json={"config": {}}, headers=auth
    )


# --- Auth ------------------------------------------------------------------------


def test_route_requires_a_session(client) -> None:
    assert client.get("/api/v1/devtools/connectivity").status_code == 401


# --- No permission gate (deliberate -- Logic Contract §8) --------------------------


def test_no_permission_grant_needed(client, auth) -> None:
    """Unlike every M12 device-control module, this route has no
    PermissionModel gate at all -- a bare authenticated session is
    sufficient, matching every other devtools capability."""
    response = client.get("/api/v1/devtools/connectivity", headers=auth)
    assert response.status_code == 200


# --- Connector status ----------------------------------------------------------------


def test_connector_registered_but_not_connected(client, auth) -> None:
    response = client.get("/api/v1/devtools/connectivity", headers=auth)

    assert response.status_code == 200
    connectors = response.json()["data"]["connectors"]
    assert connectors == [
        {"connector_type": "home_assistant", "registered": True, "connected": False}
    ]


def test_connector_connected(client, auth) -> None:
    _connect(client, auth)

    response = client.get("/api/v1/devtools/connectivity", headers=auth)

    connectors = response.json()["data"]["connectors"]
    assert connectors == [
        {"connector_type": "home_assistant", "registered": True, "connected": True}
    ]


# --- Device health -------------------------------------------------------------------


def test_no_homes_is_empty_list(client, auth) -> None:
    response = client.get("/api/v1/devtools/connectivity", headers=auth)

    assert response.status_code == 200
    assert response.json()["data"]["homes"] == []
    assert response.json()["meta"]["home_count"] == 0


def test_home_filter_returns_one_home(client, auth) -> None:
    home_id = _home(client, auth)
    _home(client, auth, name="Second Home")

    response = client.get(
        "/api/v1/devtools/connectivity", params={"home_id": home_id}, headers=auth
    )

    body = response.json()["data"]
    assert len(body["homes"]) == 1
    assert body["homes"][0]["home_id"] == home_id


def test_no_home_filter_returns_every_home(client, auth) -> None:
    home_a = _home(client, auth, name="Home A")
    home_b = _home(client, auth, name="Home B")

    response = client.get("/api/v1/devtools/connectivity", headers=auth)

    ids = {row["home_id"] for row in response.json()["data"]["homes"]}
    assert ids == {home_a, home_b}


def test_unknown_home_id_is_404(client, auth) -> None:
    response = client.get(
        "/api/v1/devtools/connectivity", params={"home_id": "no-such-home"}, headers=auth
    )
    assert response.status_code == 404


# --- Envelope / meta -----------------------------------------------------------------


def test_response_envelope_shape(client, auth) -> None:
    response = client.get("/api/v1/devtools/connectivity", headers=auth)

    assert set(response.json()) == {"data", "meta"}
    assert set(response.json()["data"]) == {"connectors", "homes"}
    assert "connector_count" in response.json()["meta"]
    assert "home_count" in response.json()["meta"]


def test_meta_counts_match_data(client, auth) -> None:
    _connect(client, auth)
    _home(client, auth)

    response = client.get("/api/v1/devtools/connectivity", headers=auth)

    body = response.json()
    assert body["meta"]["connector_count"] == len(body["data"]["connectors"])
    assert body["meta"]["home_count"] == len(body["data"]["homes"])


# --- No secret exposure ---------------------------------------------------------------


def test_no_secret_or_credential_fields_in_response(client, auth) -> None:
    _connect(client, auth)
    _home(client, auth)

    response = client.get("/api/v1/devtools/connectivity", headers=auth)
    body_text = response.text.lower()

    for forbidden in ("password", "token", "api_key", "apikey", "secret", "credential"):
        assert forbidden not in body_text


# --- No extra endpoints ---------------------------------------------------------------


def test_no_mutation_route_exists(client, auth) -> None:
    for method, path in (
        ("post", "/api/v1/devtools/connectivity"),
        ("put", "/api/v1/devtools/connectivity"),
        ("delete", "/api/v1/devtools/connectivity"),
    ):
        assert getattr(client, method)(path, headers=auth).status_code in (404, 405)


def test_no_convenience_endpoints_beyond_contract(client, auth) -> None:
    for path in (
        "/api/v1/devtools/connectivity/latency",
        "/api/v1/devtools/connectivity/uptime",
        "/api/v1/devtools/connectivity/history",
        "/api/v1/devtools/mqtt",
        "/api/v1/devtools/events",
    ):
        assert client.get(path, headers=auth).status_code == 404
