"""Vacuum + Humidifier REST tests -- Milestone 12 Appliance Control
(Vacuum + Humidifier Core Slice).

Against the real FastAPI app and the real DI container, matching
``test_m12_thermostats_route.py``'s pattern. Permission is granted
through the existing generic plugin-permissions route, never
``PermissionModel`` directly.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from jarvis.services.vacuum_humidifier_service import SMART_HOME_SCOPE, VACUUM_HUMIDIFIER_PRINCIPAL


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


def _grant(client, auth) -> None:
    response = client.post(
        f"/api/v1/plugins/{VACUUM_HUMIDIFIER_PRINCIPAL}/permissions/{SMART_HOME_SCOPE}/grant",
        headers=auth,
    )
    assert response.status_code == 200


def _home(client, auth, name: str = "Primary Residence") -> str:
    response = client.post("/api/v1/homes", json={"name": name}, headers=auth)
    assert response.status_code == 201
    return response.json()["data"]["id"]


def _connect(client, auth) -> None:
    client.post(
        "/api/v1/connectivity/connectors/home_assistant/connect", json={"config": {}}, headers=auth
    )


def _discover(client, auth, fake_connector, home_id: str, devices) -> list[dict]:
    fake_connector.devices = devices
    response = client.post(
        "/api/v1/connectivity/discover",
        json={"connector_type": "home_assistant", "home_id": home_id},
        headers=auth,
    )
    assert response.status_code == 200
    return response.json()["data"]


def _vacuum(external_id: str):
    from jarvis.core.interfaces.connectivity import DiscoveredDevice

    return DiscoveredDevice(
        external_id=external_id,
        name="Robot Vacuum",
        device_type="appliance",
        metadata={"domain": "vacuum"},
    )


def _humidifier(external_id: str):
    from jarvis.core.interfaces.connectivity import DiscoveredDevice

    return DiscoveredDevice(
        external_id=external_id,
        name="Bedroom Humidifier",
        device_type="appliance",
        metadata={"domain": "humidifier"},
    )


# --- Auth ------------------------------------------------------------------------


def test_routes_require_a_session(client) -> None:
    for method, path in (
        ("get", "/api/v1/appliances/vacuums"),
        ("get", "/api/v1/appliances/humidifiers"),
    ):
        assert getattr(client, method)(path).status_code in (401, 403)


# --- Reads are ungated ---------------------------------------------------------------


def test_reads_succeed_without_grant(client, auth) -> None:
    _home(client, auth)
    assert client.get("/api/v1/appliances/vacuums", headers=auth).status_code == 200
    assert client.get("/api/v1/appliances/humidifiers", headers=auth).status_code == 200


# --- Vacuum ------------------------------------------------------------------------


def test_vacuum_list_get(client, auth, fake_connector) -> None:
    from jarvis.core.interfaces.connectivity import DeviceState

    home_id = _home(client, auth)
    _connect(client, auth)
    discovered = _discover(client, auth, fake_connector, home_id, [_vacuum("vacuum.living_room")])
    device_id = discovered[0]["id"]
    fake_connector.states["vacuum.living_room"] = DeviceState(
        external_id="vacuum.living_room", status="docked", attributes={"battery_level": 90}
    )

    listed = client.get("/api/v1/appliances/vacuums", headers=auth)
    assert listed.status_code == 200
    assert listed.json()["meta"]["count"] == 1

    fetched = client.get(f"/api/v1/appliances/vacuums/{device_id}", headers=auth)
    assert fetched.status_code == 200
    assert fetched.json()["data"]["state"] == "docked"
    assert fetched.json()["data"]["battery_level"] == 90.0


def test_vacuum_get_unknown_is_404(client, auth) -> None:
    response = client.get("/api/v1/appliances/vacuums/no-such-device", headers=auth)
    assert response.status_code == 404


def test_vacuum_get_wrong_type_is_404(client, auth) -> None:
    home_id = _home(client, auth)
    switch = client.post(
        "/api/v1/devices",
        json={"home_id": home_id, "name": "Switch", "device_type": "switch"},
        headers=auth,
    ).json()["data"]

    response = client.get(f"/api/v1/appliances/vacuums/{switch['id']}", headers=auth)

    assert response.status_code == 404


def test_vacuum_action_denied_without_grant_is_400(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    _connect(client, auth)
    discovered = _discover(client, auth, fake_connector, home_id, [_vacuum("vacuum.living_room")])
    device_id = discovered[0]["id"]

    response = client.post(f"/api/v1/appliances/vacuums/{device_id}/start", headers=auth)

    assert response.status_code == 400
    assert "permission" in response.json()["detail"].lower()


@pytest.mark.parametrize("verb", ["start", "stop", "pause", "dock"])
def test_vacuum_action_succeeds_after_grant(client, auth, fake_connector, verb: str) -> None:
    from jarvis.core.interfaces.connectivity import DeviceState

    home_id = _home(client, auth)
    _connect(client, auth)
    discovered = _discover(client, auth, fake_connector, home_id, [_vacuum("vacuum.living_room")])
    device_id = discovered[0]["id"]
    fake_connector.states["vacuum.living_room"] = DeviceState(
        external_id="vacuum.living_room", status="docked", attributes={}
    )
    _grant(client, auth)

    response = client.post(f"/api/v1/appliances/vacuums/{device_id}/{verb}", headers=auth)

    assert response.status_code == 200
    assert response.json()["data"]["success"] is True
    assert response.json()["meta"]["success"] is True


def test_vacuum_no_extra_endpoints(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    _connect(client, auth)
    discovered = _discover(client, auth, fake_connector, home_id, [_vacuum("vacuum.living_room")])
    device_id = discovered[0]["id"]
    _grant(client, auth)

    for method, path in (
        ("post", f"/api/v1/appliances/vacuums/{device_id}/state"),
        ("post", f"/api/v1/appliances/vacuums/{device_id}/locate"),
        ("post", f"/api/v1/appliances/vacuums/{device_id}"),
    ):
        assert getattr(client, method)(path, headers=auth).status_code in (404, 405)


# --- Humidifier --------------------------------------------------------------------


def test_humidifier_list_get(client, auth, fake_connector) -> None:
    from jarvis.core.interfaces.connectivity import DeviceState

    home_id = _home(client, auth)
    _connect(client, auth)
    discovered = _discover(
        client, auth, fake_connector, home_id, [_humidifier("humidifier.bedroom")]
    )
    device_id = discovered[0]["id"]
    fake_connector.states["humidifier.bedroom"] = DeviceState(
        external_id="humidifier.bedroom", status="on", attributes={"humidity": 45.0}
    )

    listed = client.get("/api/v1/appliances/humidifiers", headers=auth)
    assert listed.status_code == 200
    assert listed.json()["meta"]["count"] == 1

    fetched = client.get(f"/api/v1/appliances/humidifiers/{device_id}", headers=auth)
    assert fetched.status_code == 200
    assert fetched.json()["data"]["on"] is True
    assert fetched.json()["data"]["target_humidity"] == 45.0


def test_humidifier_get_unknown_is_404(client, auth) -> None:
    response = client.get("/api/v1/appliances/humidifiers/no-such-device", headers=auth)
    assert response.status_code == 404


def test_humidifier_state_denied_without_grant_is_400(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    _connect(client, auth)
    discovered = _discover(
        client, auth, fake_connector, home_id, [_humidifier("humidifier.bedroom")]
    )
    device_id = discovered[0]["id"]

    response = client.post(
        f"/api/v1/appliances/humidifiers/{device_id}/state", json={"on": True}, headers=auth
    )

    assert response.status_code == 400
    assert "permission" in response.json()["detail"].lower()


def test_humidifier_combined_state_update_succeeds_after_grant(
    client, auth, fake_connector
) -> None:
    from jarvis.core.interfaces.connectivity import DeviceState

    home_id = _home(client, auth)
    _connect(client, auth)
    discovered = _discover(
        client, auth, fake_connector, home_id, [_humidifier("humidifier.bedroom")]
    )
    device_id = discovered[0]["id"]
    fake_connector.states["humidifier.bedroom"] = DeviceState(
        external_id="humidifier.bedroom", status="off", attributes={}
    )
    _grant(client, auth)

    response = client.post(
        f"/api/v1/appliances/humidifiers/{device_id}/state",
        json={"on": True, "target_humidity": 45.0},
        headers=auth,
    )

    assert response.status_code == 200
    assert response.json()["data"]["success"] is True
    assert fake_connector.sent_commands == [
        ("humidifier.bedroom", "turn_on", {}),
        ("humidifier.bedroom", "set_humidity", {"humidity": 45.0}),
    ]


def test_humidifier_empty_body_is_400(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    _connect(client, auth)
    discovered = _discover(
        client, auth, fake_connector, home_id, [_humidifier("humidifier.bedroom")]
    )
    device_id = discovered[0]["id"]
    _grant(client, auth)

    response = client.post(
        f"/api/v1/appliances/humidifiers/{device_id}/state", json={}, headers=auth
    )

    assert response.status_code == 400


def test_humidifier_get_wrong_type_is_404(client, auth) -> None:
    home_id = _home(client, auth)
    switch = client.post(
        "/api/v1/devices",
        json={"home_id": home_id, "name": "Switch", "device_type": "switch"},
        headers=auth,
    ).json()["data"]

    response = client.get(f"/api/v1/appliances/humidifiers/{switch['id']}", headers=auth)

    assert response.status_code == 404


# --- Envelope shape ----------------------------------------------------------------


def test_response_uses_the_documented_envelope(client, auth) -> None:
    _home(client, auth)
    listed = client.get("/api/v1/appliances/vacuums", headers=auth)
    assert set(listed.json()) == {"data", "meta"}
