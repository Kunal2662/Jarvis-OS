"""Sensors REST tests -- Milestone 12 Sensors.

Against the real FastAPI app and the real DI container, matching
``test_m12_smart_locks_route.py``'s pattern. Permission is granted
through the existing generic plugin-permissions route, never
``PermissionModel`` directly.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from jarvis.services.sensor_service import SENSOR_PRINCIPAL, SMART_HOME_SCOPE


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


def _grant_smart_home_permission(client, auth) -> None:
    response = client.post(
        f"/api/v1/plugins/{SENSOR_PRINCIPAL}/permissions/{SMART_HOME_SCOPE}/grant",
        headers=auth,
    )
    assert response.status_code == 200


def _home(client, auth, name: str = "Primary Residence") -> str:
    response = client.post("/api/v1/homes", json={"name": name}, headers=auth)
    assert response.status_code == 201
    return response.json()["data"]["id"]


def _connected_sensor(client, auth, fake_connector, home_id: str) -> str:
    from jarvis.core.interfaces.connectivity import DiscoveredDevice

    client.post(
        "/api/v1/connectivity/connectors/home_assistant/connect", json={"config": {}}, headers=auth
    )
    fake_connector.devices = [
        DiscoveredDevice(
            external_id=f"sensor.{home_id[:8]}",
            name="Living Room Temp",
            device_type="sensor",
            metadata={"domain": "sensor", "device_class": "temperature"},
        )
    ]
    discovered = client.post(
        "/api/v1/connectivity/discover",
        json={"connector_type": "home_assistant", "home_id": home_id},
        headers=auth,
    ).json()["data"]
    return discovered[0]["id"]


# --- Auth ------------------------------------------------------------------------


def test_every_route_requires_a_session(client) -> None:
    for method, path in (("get", "/api/v1/sensors"), ("get", "/api/v1/sensors/x")):
        assert getattr(client, method)(path).status_code in (401, 403)


# --- Permission gate (the genuinely new case -- reads are gated here) -----------


def test_list_denied_without_grant_is_400(client, auth) -> None:
    response = client.get("/api/v1/sensors", headers=auth)
    assert response.status_code == 400
    assert "permission" in response.json()["detail"].lower()


def test_get_denied_without_grant_is_400_not_404(client, auth, fake_connector) -> None:
    """The distinguishing case this module introduces: an existing
    sensor, ungranted permission -> 400, never confused with 404
    'does not exist'."""
    home_id = _home(client, auth)
    device_id = _connected_sensor(client, auth, fake_connector, home_id)

    response = client.get(f"/api/v1/sensors/{device_id}", headers=auth)

    assert response.status_code == 400
    assert "permission" in response.json()["detail"].lower()


def test_get_unknown_device_after_grant_is_404(client, auth) -> None:
    _grant_smart_home_permission(client, auth)
    response = client.get("/api/v1/sensors/no-such-device", headers=auth)
    assert response.status_code == 404


def test_reads_succeed_after_grant(client, auth, fake_connector) -> None:
    from jarvis.core.interfaces.connectivity import DeviceState

    home_id = _home(client, auth)
    device_id = _connected_sensor(client, auth, fake_connector, home_id)
    fake_connector.states[fake_connector.devices[0].external_id] = DeviceState(
        external_id=fake_connector.devices[0].external_id, status="21.5", attributes={}
    )
    _grant_smart_home_permission(client, auth)

    listed = client.get("/api/v1/sensors", headers=auth)
    assert listed.status_code == 200
    assert listed.json()["meta"]["count"] == 1

    fetched = client.get(f"/api/v1/sensors/{device_id}", headers=auth)
    assert fetched.status_code == 200
    assert fetched.json()["data"]["id"] == device_id


# --- Envelope + payload shape ----------------------------------------------------


def test_responses_use_the_documented_envelope(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    _connected_sensor(client, auth, fake_connector, home_id)
    _grant_smart_home_permission(client, auth)

    listed = client.get("/api/v1/sensors", headers=auth)
    assert set(listed.json()) == {"data", "meta"}


def test_list_payload_has_device_class_and_kind_but_no_live_fields(
    client, auth, fake_connector
) -> None:
    home_id = _home(client, auth)
    _connected_sensor(client, auth, fake_connector, home_id)
    _grant_smart_home_permission(client, auth)

    row = client.get("/api/v1/sensors", headers=auth).json()["data"][0]

    assert row["device_class"] == "temperature"
    assert row["kind"] == "numeric"
    assert "value" not in row


def test_get_payload_includes_live_reading(client, auth, fake_connector) -> None:
    from jarvis.core.interfaces.connectivity import DeviceState

    home_id = _home(client, auth)
    device_id = _connected_sensor(client, auth, fake_connector, home_id)
    fake_connector.states[fake_connector.devices[0].external_id] = DeviceState(
        external_id=fake_connector.devices[0].external_id,
        status="21.5",
        attributes={"unit_of_measurement": "°C"},
    )
    _grant_smart_home_permission(client, auth)

    fetched = client.get(f"/api/v1/sensors/{device_id}", headers=auth).json()["data"]

    assert fetched["value"] == 21.5
    assert fetched["unit"] == "°C"
    assert fetched["available"] is True


def test_get_sensor_on_non_sensor_device_is_404(client, auth) -> None:
    _grant_smart_home_permission(client, auth)
    home_id = _home(client, auth)
    switch = client.post(
        "/api/v1/devices",
        json={"home_id": home_id, "name": "Switch", "device_type": "switch"},
        headers=auth,
    ).json()["data"]

    response = client.get(f"/api/v1/sensors/{switch['id']}", headers=auth)

    assert response.status_code == 404


# --- No mutation route exists -----------------------------------------------------


def test_no_mutation_route_exists(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    device_id = _connected_sensor(client, auth, fake_connector, home_id)
    _grant_smart_home_permission(client, auth)

    for method, path in (
        ("post", f"/api/v1/sensors/{device_id}"),
        ("post", f"/api/v1/sensors/{device_id}/state"),
        ("put", f"/api/v1/sensors/{device_id}"),
        ("patch", f"/api/v1/sensors/{device_id}"),
        ("delete", f"/api/v1/sensors/{device_id}"),
    ):
        assert getattr(client, method)(path, headers=auth).status_code in (404, 405)
