"""Thermostats REST tests -- Milestone 12 Appliance Control (Climate /
Thermostat Slice).

Against the real FastAPI app and the real DI container, matching
``test_m12_appliances_route.py``'s pattern. Permission is granted
through the existing generic plugin-permissions route, never
``PermissionModel`` directly.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from jarvis.services.thermostat_service import SMART_HOME_SCOPE, THERMOSTAT_PRINCIPAL


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
        f"/api/v1/plugins/{THERMOSTAT_PRINCIPAL}/permissions/{SMART_HOME_SCOPE}/grant",
        headers=auth,
    )
    assert response.status_code == 200


def _home(client, auth, name: str = "Primary Residence") -> str:
    response = client.post("/api/v1/homes", json={"name": name}, headers=auth)
    assert response.status_code == 201
    return response.json()["data"]["id"]


def _connected_thermostat(client, auth, fake_connector, home_id: str) -> str:
    from jarvis.core.interfaces.connectivity import DeviceState, DiscoveredDevice

    client.post(
        "/api/v1/connectivity/connectors/home_assistant/connect", json={"config": {}}, headers=auth
    )
    external_id = "climate.living_room"
    fake_connector.devices = [
        DiscoveredDevice(
            external_id=external_id,
            name="Living Room AC",
            device_type="thermostat",
            metadata={"domain": "climate"},
        )
    ]
    fake_connector.states[external_id] = DeviceState(
        external_id=external_id,
        status="cool",
        attributes={
            "current_temperature": 24.5,
            "temperature": 22.0,
            "hvac_modes": ["off", "cool", "heat"],
            "min_temp": 16.0,
            "max_temp": 30.0,
        },
    )
    discovered = client.post(
        "/api/v1/connectivity/discover",
        json={"connector_type": "home_assistant", "home_id": home_id},
        headers=auth,
    ).json()["data"]
    return discovered[0]["id"]


# --- Auth --------------------------------------------------------------------------


def test_every_route_requires_a_session(client) -> None:
    assert client.get("/api/v1/thermostats").status_code in (401, 403)
    assert client.get("/api/v1/thermostats/x").status_code in (401, 403)
    assert client.post("/api/v1/thermostats/x/state", json={}).status_code in (401, 403)


# --- Reads (ungated) ----------------------------------------------------------------


def test_list_is_ungated(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    _connected_thermostat(client, auth, fake_connector, home_id)

    response = client.get("/api/v1/thermostats", headers=auth)

    assert response.status_code == 200
    assert response.json()["meta"]["count"] == 1


def test_get_is_ungated_and_returns_live_state(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    device_id = _connected_thermostat(client, auth, fake_connector, home_id)

    body = client.get(f"/api/v1/thermostats/{device_id}", headers=auth).json()["data"]

    assert body["current_temperature"] == 24.5
    assert body["target_temperature"] == 22.0
    assert body["hvac_mode"] == "cool"
    assert body["hvac_modes"] == ["off", "cool", "heat"]
    assert body["available"] is True


def test_get_unknown_device_is_404(client, auth) -> None:
    assert client.get("/api/v1/thermostats/no-such-device", headers=auth).status_code == 404


def test_get_wrong_device_type_is_404(client, auth) -> None:
    home_id = _home(client, auth)
    switch = client.post(
        "/api/v1/devices",
        json={"home_id": home_id, "name": "Switch", "device_type": "switch"},
        headers=auth,
    ).json()["data"]

    assert client.get(f"/api/v1/thermostats/{switch['id']}", headers=auth).status_code == 404


def test_responses_use_the_documented_envelope(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    _connected_thermostat(client, auth, fake_connector, home_id)

    assert set(client.get("/api/v1/thermostats", headers=auth).json()) == {"data", "meta"}


# --- Mutation -----------------------------------------------------------------------


def test_mutation_denied_without_grant_is_400(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    device_id = _connected_thermostat(client, auth, fake_connector, home_id)

    response = client.post(
        f"/api/v1/thermostats/{device_id}/state", json={"temperature": 21.0}, headers=auth
    )

    assert response.status_code == 400
    assert "permission" in response.json()["detail"].lower()


def test_temperature_only_mutation(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    device_id = _connected_thermostat(client, auth, fake_connector, home_id)
    _grant(client, auth)

    response = client.post(
        f"/api/v1/thermostats/{device_id}/state", json={"temperature": 21.0}, headers=auth
    )

    assert response.status_code == 200
    assert response.json()["meta"]["success"] is True
    assert fake_connector.sent_commands[-1][1] == "set_temperature"


def test_mode_only_mutation(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    device_id = _connected_thermostat(client, auth, fake_connector, home_id)
    _grant(client, auth)

    response = client.post(
        f"/api/v1/thermostats/{device_id}/state", json={"hvac_mode": "heat"}, headers=auth
    )

    assert response.status_code == 200
    assert fake_connector.sent_commands[-1] == (
        "climate.living_room",
        "set_hvac_mode",
        {"hvac_mode": "heat"},
    )


def test_combined_mutation(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    device_id = _connected_thermostat(client, auth, fake_connector, home_id)
    _grant(client, auth)

    response = client.post(
        f"/api/v1/thermostats/{device_id}/state",
        json={"temperature": 20.0, "hvac_mode": "cool"},
        headers=auth,
    )

    assert response.status_code == 200
    assert [c[1] for c in fake_connector.sent_commands[-2:]] == [
        "set_hvac_mode",
        "set_temperature",
    ]


def test_empty_body_is_400(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    device_id = _connected_thermostat(client, auth, fake_connector, home_id)
    _grant(client, auth)

    response = client.post(f"/api/v1/thermostats/{device_id}/state", json={}, headers=auth)

    assert response.status_code == 400
    assert "at least one" in response.json()["detail"]


def test_out_of_range_temperature_is_400(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    device_id = _connected_thermostat(client, auth, fake_connector, home_id)
    _grant(client, auth)

    response = client.post(
        f"/api/v1/thermostats/{device_id}/state", json={"temperature": 99.0}, headers=auth
    )

    assert response.status_code == 400
    assert "maximum" in response.json()["detail"]


def test_unsupported_mode_is_400(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    device_id = _connected_thermostat(client, auth, fake_connector, home_id)
    _grant(client, auth)

    response = client.post(
        f"/api/v1/thermostats/{device_id}/state", json={"hvac_mode": "dry"}, headers=auth
    )

    assert response.status_code == 400
    assert "not supported" in response.json()["detail"]


def test_mutation_unknown_device_is_400(client, auth) -> None:
    _grant(client, auth)
    response = client.post(
        "/api/v1/thermostats/no-such-device/state", json={"temperature": 21.0}, headers=auth
    )
    assert response.status_code == 400


def test_mutation_wrong_device_type_is_400(client, auth) -> None:
    _grant(client, auth)
    home_id = _home(client, auth)
    switch = client.post(
        "/api/v1/devices",
        json={"home_id": home_id, "name": "Switch", "device_type": "switch"},
        headers=auth,
    ).json()["data"]

    response = client.post(
        f"/api/v1/thermostats/{switch['id']}/state", json={"temperature": 21.0}, headers=auth
    )

    assert response.status_code == 400
    assert "not a thermostat" in response.json()["detail"]


def test_unavailable_device_still_reads_200(client, auth, fake_connector) -> None:
    from jarvis.core.interfaces.connectivity import DeviceState

    home_id = _home(client, auth)
    device_id = _connected_thermostat(client, auth, fake_connector, home_id)
    fake_connector.states["climate.living_room"] = DeviceState(
        external_id="climate.living_room", status="unavailable", attributes={}
    )

    body = client.get(f"/api/v1/thermostats/{device_id}", headers=auth)

    assert body.status_code == 200
    assert body.json()["data"]["available"] is False
    assert body.json()["data"]["hvac_mode"] is None


# --- No extra endpoints -------------------------------------------------------------


def test_no_extra_thermostat_endpoints(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    device_id = _connected_thermostat(client, auth, fake_connector, home_id)
    _grant(client, auth)

    for method, path in (
        ("post", f"/api/v1/thermostats/{device_id}/temperature"),
        ("post", f"/api/v1/thermostats/{device_id}/mode"),
        ("post", f"/api/v1/thermostats/{device_id}/fan_mode"),
        ("post", f"/api/v1/thermostats/{device_id}/preset"),
        ("delete", f"/api/v1/thermostats/{device_id}"),
    ):
        assert getattr(client, method)(path, headers=auth).status_code in (404, 405)
