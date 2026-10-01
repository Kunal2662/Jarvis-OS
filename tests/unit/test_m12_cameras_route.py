"""Cameras REST tests -- Milestone 12 Smart Cameras (Core Camera
Slice).

Against the real FastAPI app and the real DI container, matching
``test_m12_sensors_route.py``'s pattern (reads are gated here too) and
``test_m12_smart_locks_route.py``'s four-action-endpoint shape.
Permission is granted through the existing generic plugin-permissions
route, never ``PermissionModel`` directly.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from jarvis.services.camera_service import CAMERA_PRINCIPAL, SMART_HOME_SCOPE


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
        f"/api/v1/plugins/{CAMERA_PRINCIPAL}/permissions/{SMART_HOME_SCOPE}/grant",
        headers=auth,
    )
    assert response.status_code == 200


def _home(client, auth, name: str = "Primary Residence") -> str:
    response = client.post("/api/v1/homes", json={"name": name}, headers=auth)
    assert response.status_code == 201
    return response.json()["data"]["id"]


def _connected_camera(client, auth, fake_connector, home_id: str) -> str:
    from jarvis.core.interfaces.connectivity import DiscoveredDevice

    client.post(
        "/api/v1/connectivity/connectors/home_assistant/connect", json={"config": {}}, headers=auth
    )
    fake_connector.devices = [
        DiscoveredDevice(
            external_id=f"camera.{home_id[:8]}", name="Front Door Camera", device_type="camera"
        )
    ]
    discovered = client.post(
        "/api/v1/connectivity/discover",
        json={"connector_type": "home_assistant", "home_id": home_id},
        headers=auth,
    ).json()["data"]
    return discovered[0]["id"]


# --- Auth --------------------------------------------------------------------------


def test_every_route_requires_a_session(client) -> None:
    for method, path in (("get", "/api/v1/cameras"), ("get", "/api/v1/cameras/x")):
        assert getattr(client, method)(path).status_code in (401, 403)


# --- Permission gate (reads are gated here, unlike Lock/Switch/Appliance) -----------


def test_list_denied_without_grant_is_400(client, auth) -> None:
    response = client.get("/api/v1/cameras", headers=auth)
    assert response.status_code == 400
    assert "permission" in response.json()["detail"].lower()


def test_get_denied_without_grant_is_400_not_404(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    device_id = _connected_camera(client, auth, fake_connector, home_id)

    response = client.get(f"/api/v1/cameras/{device_id}", headers=auth)

    assert response.status_code == 400
    assert "permission" in response.json()["detail"].lower()


def test_get_unknown_device_after_grant_is_404(client, auth) -> None:
    _grant(client, auth)
    response = client.get("/api/v1/cameras/no-such-device", headers=auth)
    assert response.status_code == 404


def test_get_camera_on_non_camera_device_is_404(client, auth) -> None:
    _grant(client, auth)
    home_id = _home(client, auth)
    switch = client.post(
        "/api/v1/devices",
        json={"home_id": home_id, "name": "Switch", "device_type": "switch"},
        headers=auth,
    ).json()["data"]

    response = client.get(f"/api/v1/cameras/{switch['id']}", headers=auth)

    assert response.status_code == 404


# --- Reads succeed after grant -------------------------------------------------------


def test_reads_succeed_after_grant(client, auth, fake_connector) -> None:
    from jarvis.core.interfaces.connectivity import DeviceState

    home_id = _home(client, auth)
    device_id = _connected_camera(client, auth, fake_connector, home_id)
    fake_connector.states[fake_connector.devices[0].external_id] = DeviceState(
        external_id=fake_connector.devices[0].external_id,
        status="idle",
        attributes={"motion_detection": True},
    )
    _grant(client, auth)

    listed = client.get("/api/v1/cameras", headers=auth)
    assert listed.status_code == 200
    assert listed.json()["meta"]["count"] == 1

    fetched = client.get(f"/api/v1/cameras/{device_id}", headers=auth)
    assert fetched.status_code == 200
    assert fetched.json()["data"]["state"] == "idle"
    assert fetched.json()["data"]["motion_detection"] is True


def test_responses_use_the_documented_envelope(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    _connected_camera(client, auth, fake_connector, home_id)
    _grant(client, auth)

    listed = client.get("/api/v1/cameras", headers=auth)
    assert set(listed.json()) == {"data", "meta"}


# --- Commands ------------------------------------------------------------------------


def test_command_denied_without_grant_is_400(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    device_id = _connected_camera(client, auth, fake_connector, home_id)

    response = client.post(f"/api/v1/cameras/{device_id}/turn_on", headers=auth)

    assert response.status_code == 400
    assert fake_connector.sent_commands == []


@pytest.mark.parametrize(
    "verb", ["turn_on", "turn_off", "enable_motion_detection", "disable_motion_detection"]
)
def test_command_succeeds_after_grant(client, auth, fake_connector, verb: str) -> None:
    home_id = _home(client, auth)
    device_id = _connected_camera(client, auth, fake_connector, home_id)
    _grant(client, auth)

    response = client.post(f"/api/v1/cameras/{device_id}/{verb}", headers=auth)

    assert response.status_code == 200
    assert response.json()["data"]["success"] is True
    assert response.json()["meta"]["success"] is True
    assert fake_connector.sent_commands == [(fake_connector.devices[0].external_id, verb, {})]


def test_command_on_unknown_device_is_400(client, auth) -> None:
    _grant(client, auth)
    response = client.post("/api/v1/cameras/no-such-device/turn_on", headers=auth)
    assert response.status_code == 400


# --- No extra endpoints --------------------------------------------------------------


def test_no_extra_endpoints(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    device_id = _connected_camera(client, auth, fake_connector, home_id)
    _grant(client, auth)

    for method, path in (
        ("post", f"/api/v1/cameras/{device_id}/state"),
        ("post", f"/api/v1/cameras/{device_id}/snapshot"),
        ("post", f"/api/v1/cameras/{device_id}"),
    ):
        assert getattr(client, method)(path, headers=auth).status_code in (404, 405)
