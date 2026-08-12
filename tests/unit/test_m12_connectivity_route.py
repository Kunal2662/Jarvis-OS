"""Connectivity REST tests -- Milestone 12 Connectivity REST + Smart
Lighting.

Against the real FastAPI app and the real DI container, matching
``test_smart_home_route.py``'s pattern: a real session token, the real
Bearer dependency, a real temp-file database, with only the
``connectivity_registry`` provider overridden so ``home_assistant``
resolves to a scripted ``FakeDeviceConnector`` instead of a real HTTP
client -- there is no real vendor to talk to in a test.
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


# --- Auth + envelope ------------------------------------------------------------


def test_every_route_requires_a_session(client) -> None:
    for method, path in (
        ("get", "/api/v1/connectivity/connectors"),
        ("post", "/api/v1/connectivity/discover"),
    ):
        assert getattr(client, method)(path).status_code in (401, 403)


def test_list_connectors_uses_the_documented_envelope(client, auth) -> None:
    response = client.get("/api/v1/connectivity/connectors", headers=auth)
    assert response.status_code == 200
    assert set(response.json()) == {"data", "meta"}
    types = {row["connector_type"] for row in response.json()["data"]}
    assert {"home_assistant", "mqtt"} <= types


# --- Connector lifecycle -----------------------------------------------------


def test_connect_and_disconnect_round_trip(client, auth) -> None:
    connected = client.post(
        "/api/v1/connectivity/connectors/home_assistant/connect", json={"config": {}}, headers=auth
    )
    assert connected.status_code == 200
    assert connected.json()["data"]["connected"] is True

    listed = client.get("/api/v1/connectivity/connectors", headers=auth).json()["data"]
    row = next(r for r in listed if r["connector_type"] == "home_assistant")
    assert row["connected"] is True

    disconnected = client.post(
        "/api/v1/connectivity/connectors/home_assistant/disconnect", headers=auth
    )
    assert disconnected.status_code == 200
    assert disconnected.json()["data"]["connected"] is False


def test_connect_unregistered_connector_type_is_400(client, auth) -> None:
    response = client.post(
        "/api/v1/connectivity/connectors/mqtt/connect", json={"config": {}}, headers=auth
    )
    assert response.status_code == 400


# --- Discovery -----------------------------------------------------------------


def test_discover_registers_devices(client, auth, fake_connector) -> None:
    from jarvis.core.interfaces.connectivity import DiscoveredDevice

    home_id = _home(client, auth)
    fake_connector.devices = [
        DiscoveredDevice(external_id="light.kitchen", name="Kitchen Light", device_type="light")
    ]
    client.post(
        "/api/v1/connectivity/connectors/home_assistant/connect", json={"config": {}}, headers=auth
    )

    response = client.post(
        "/api/v1/connectivity/discover",
        json={"connector_type": "home_assistant", "home_id": home_id},
        headers=auth,
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert len(payload) == 1
    assert payload[0]["name"] == "Kitchen Light"
    assert payload[0]["device_type"] == "light"


def test_discover_unknown_home_is_404(client, auth) -> None:
    response = client.post(
        "/api/v1/connectivity/discover",
        json={"connector_type": "home_assistant", "home_id": "no-such-home"},
        headers=auth,
    )
    assert response.status_code == 404


def test_discover_without_connecting_first_is_400(client, auth) -> None:
    home_id = _home(client, auth)
    response = client.post(
        "/api/v1/connectivity/discover",
        json={"connector_type": "home_assistant", "home_id": home_id},
        headers=auth,
    )
    assert response.status_code == 400


# --- State + commands -----------------------------------------------------------


def test_refresh_unknown_device_is_404(client, auth) -> None:
    response = client.post("/api/v1/connectivity/devices/no-such-device/refresh", headers=auth)
    assert response.status_code == 404


def test_send_command_unknown_device_is_404(client, auth) -> None:
    response = client.post(
        "/api/v1/connectivity/devices/no-such-device/command",
        json={"command": "turn_on", "payload": {}},
        headers=auth,
    )
    assert response.status_code == 404


def test_send_command_round_trip(client, auth, fake_connector) -> None:
    from jarvis.core.interfaces.connectivity import DiscoveredDevice

    home_id = _home(client, auth)
    client.post(
        "/api/v1/connectivity/connectors/home_assistant/connect", json={"config": {}}, headers=auth
    )
    fake_connector.devices = [
        DiscoveredDevice(external_id="light.kitchen", name="Kitchen Light", device_type="light")
    ]
    discovered = client.post(
        "/api/v1/connectivity/discover",
        json={"connector_type": "home_assistant", "home_id": home_id},
        headers=auth,
    ).json()["data"]
    real_device_id = next(d["id"] for d in discovered if d["external_id"] == "light.kitchen")

    response = client.post(
        f"/api/v1/connectivity/devices/{real_device_id}/command",
        json={"command": "turn_on", "payload": {}},
        headers=auth,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["success"] is True
    assert body["meta"]["success"] is True
    assert fake_connector.sent_commands == [("light.kitchen", "turn_on", {})]
