"""Water Heater REST tests -- Milestone 12 Appliance Control (Water
Heater Core Slice).

Against the real FastAPI app and the real DI container, matching
``test_m12_thermostats_route.py``'s/``test_m12_media_players_route.py``'s
pattern. Permission is granted through the existing generic
plugin-permissions route, never ``PermissionModel`` directly.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from jarvis.services.water_heater_service import SMART_HOME_SCOPE, WATER_HEATER_PRINCIPAL

_EXTERNAL_ID = "water_heater.tank"


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
        f"/api/v1/plugins/{WATER_HEATER_PRINCIPAL}/permissions/{SMART_HOME_SCOPE}/grant",
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


def _water_heater(external_id: str = _EXTERNAL_ID):
    from jarvis.core.interfaces.connectivity import DiscoveredDevice

    return DiscoveredDevice(
        external_id=external_id,
        name="Basement Water Heater",
        device_type="appliance",
        metadata={"domain": "water_heater"},
    )


# --- Auth ------------------------------------------------------------------------


def test_routes_require_a_session(client) -> None:
    for method, path in (
        ("get", "/api/v1/appliances/water-heaters"),
        ("get", "/api/v1/appliances/water-heaters/x"),
    ):
        assert getattr(client, method)(path).status_code in (401, 403)


# --- Reads are ungated ---------------------------------------------------------------


def test_reads_succeed_without_grant(client, auth) -> None:
    _home(client, auth)
    assert client.get("/api/v1/appliances/water-heaters", headers=auth).status_code == 200


# --- List / get --------------------------------------------------------------------


def test_list_get(client, auth, fake_connector) -> None:
    from jarvis.core.interfaces.connectivity import DeviceState

    home_id = _home(client, auth)
    _connect(client, auth)
    discovered = _discover(client, auth, fake_connector, home_id, [_water_heater()])
    device_id = discovered[0]["id"]
    fake_connector.states[_EXTERNAL_ID] = DeviceState(
        external_id=_EXTERNAL_ID,
        status="eco",
        attributes={"temperature": 55.0, "current_temperature": 48.0},
    )

    listed = client.get("/api/v1/appliances/water-heaters", headers=auth)
    assert listed.status_code == 200
    assert listed.json()["meta"]["count"] == 1

    fetched = client.get(f"/api/v1/appliances/water-heaters/{device_id}", headers=auth)
    assert fetched.status_code == 200
    assert fetched.json()["data"]["state"] == "eco"
    assert fetched.json()["data"]["operation_mode"] == "eco"
    assert fetched.json()["data"]["target_temperature"] == 55.0
    assert fetched.json()["data"]["current_temperature"] == 48.0


def test_get_unavailable_device_is_still_200(client, auth, fake_connector) -> None:
    from jarvis.core.interfaces.connectivity import DeviceState

    home_id = _home(client, auth)
    _connect(client, auth)
    discovered = _discover(client, auth, fake_connector, home_id, [_water_heater()])
    device_id = discovered[0]["id"]
    fake_connector.states[_EXTERNAL_ID] = DeviceState(
        external_id=_EXTERNAL_ID, status="unavailable", attributes={}
    )

    response = client.get(f"/api/v1/appliances/water-heaters/{device_id}", headers=auth)

    assert response.status_code == 200
    assert response.json()["data"]["available"] is False
    assert response.json()["data"]["state"] is None


def test_get_unknown_is_404(client, auth) -> None:
    response = client.get("/api/v1/appliances/water-heaters/no-such-device", headers=auth)
    assert response.status_code == 404


def test_get_wrong_type_is_404(client, auth) -> None:
    home_id = _home(client, auth)
    switch = client.post(
        "/api/v1/devices",
        json={"home_id": home_id, "name": "Switch", "device_type": "switch"},
        headers=auth,
    ).json()["data"]

    response = client.get(f"/api/v1/appliances/water-heaters/{switch['id']}", headers=auth)

    assert response.status_code == 404


def test_get_wrong_domain_is_404(client, auth) -> None:
    """An appliance-typed device that is a different appliance category
    (e.g. a media player) must not resolve as a water heater."""
    home_id = _home(client, auth)
    device = client.post(
        "/api/v1/devices",
        json={
            "home_id": home_id,
            "name": "Speaker",
            "device_type": "appliance",
            "metadata": {"domain": "media_player"},
        },
        headers=auth,
    ).json()["data"]

    response = client.get(f"/api/v1/appliances/water-heaters/{device['id']}", headers=auth)

    assert response.status_code == 404


# --- State mutation endpoint ---------------------------------------------------------


def test_no_extra_endpoints(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    _connect(client, auth)
    discovered = _discover(client, auth, fake_connector, home_id, [_water_heater()])
    device_id = discovered[0]["id"]
    _grant(client, auth)

    for method, path in (
        ("post", f"/api/v1/appliances/water-heaters/{device_id}/turn_on"),
        ("post", f"/api/v1/appliances/water-heaters/{device_id}/turn_off"),
        ("post", f"/api/v1/appliances/water-heaters/{device_id}/away_mode"),
        ("post", f"/api/v1/appliances/water-heaters/{device_id}"),
    ):
        assert getattr(client, method)(path, headers=auth).status_code in (404, 405)


def test_state_denied_without_grant_is_400(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    _connect(client, auth)
    discovered = _discover(client, auth, fake_connector, home_id, [_water_heater()])
    device_id = discovered[0]["id"]

    response = client.post(
        f"/api/v1/appliances/water-heaters/{device_id}/state",
        json={"temperature": 55.0},
        headers=auth,
    )

    assert response.status_code == 400
    assert "permission" in response.json()["detail"].lower()


def test_combined_state_update_succeeds_after_grant(client, auth, fake_connector) -> None:
    from jarvis.core.interfaces.connectivity import DeviceState

    home_id = _home(client, auth)
    _connect(client, auth)
    discovered = _discover(client, auth, fake_connector, home_id, [_water_heater()])
    device_id = discovered[0]["id"]
    fake_connector.states[_EXTERNAL_ID] = DeviceState(
        external_id=_EXTERNAL_ID, status="off", attributes={"operation_list": ["eco", "electric"]}
    )
    _grant(client, auth)

    response = client.post(
        f"/api/v1/appliances/water-heaters/{device_id}/state",
        json={"on": True, "operation_mode": "electric", "temperature": 55.0},
        headers=auth,
    )

    assert response.status_code == 200
    assert response.json()["data"]["success"] is True
    assert fake_connector.sent_commands == [
        (_EXTERNAL_ID, "turn_on", {}),
        (_EXTERNAL_ID, "set_operation_mode", {"operation_mode": "electric"}),
        (_EXTERNAL_ID, "set_temperature", {"temperature": 55.0}),
    ]


def test_partial_failure_response(client, auth, fake_connector) -> None:
    from jarvis.core.interfaces.connectivity import DeviceState

    home_id = _home(client, auth)
    _connect(client, auth)
    discovered = _discover(client, auth, fake_connector, home_id, [_water_heater()])
    device_id = discovered[0]["id"]
    fake_connector.states[_EXTERNAL_ID] = DeviceState(
        external_id=_EXTERNAL_ID, status="off", attributes={}
    )
    _grant(client, auth)
    fake_connector.next_command_succeeds = False

    response = client.post(
        f"/api/v1/appliances/water-heaters/{device_id}/state",
        json={"on": True, "temperature": 55.0},
        headers=auth,
    )

    assert response.status_code == 200
    assert response.json()["data"]["success"] is False
    assert response.json()["meta"]["success"] is False


def test_empty_body_is_400(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    _connect(client, auth)
    discovered = _discover(client, auth, fake_connector, home_id, [_water_heater()])
    device_id = discovered[0]["id"]
    _grant(client, auth)

    response = client.post(
        f"/api/v1/appliances/water-heaters/{device_id}/state", json={}, headers=auth
    )

    assert response.status_code == 400


def test_malformed_temperature_type_is_422(client, auth, fake_connector) -> None:
    """Pydantic's own schema validation rejects a non-numeric
    temperature before the request ever reaches the service layer."""
    home_id = _home(client, auth)
    _connect(client, auth)
    discovered = _discover(client, auth, fake_connector, home_id, [_water_heater()])
    device_id = discovered[0]["id"]
    _grant(client, auth)

    response = client.post(
        f"/api/v1/appliances/water-heaters/{device_id}/state",
        json={"temperature": "hot"},
        headers=auth,
    )

    assert response.status_code == 422


def test_invalid_on_type_is_422(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    _connect(client, auth)
    discovered = _discover(client, auth, fake_connector, home_id, [_water_heater()])
    device_id = discovered[0]["id"]
    _grant(client, auth)

    response = client.post(
        f"/api/v1/appliances/water-heaters/{device_id}/state",
        json={"on": ["not", "a", "bool"]},
        headers=auth,
    )

    assert response.status_code == 422


def test_bad_operation_mode_is_400(client, auth, fake_connector) -> None:
    from jarvis.core.interfaces.connectivity import DeviceState

    home_id = _home(client, auth)
    _connect(client, auth)
    discovered = _discover(client, auth, fake_connector, home_id, [_water_heater()])
    device_id = discovered[0]["id"]
    fake_connector.states[_EXTERNAL_ID] = DeviceState(
        external_id=_EXTERNAL_ID, status="eco", attributes={"operation_list": ["eco", "electric"]}
    )
    _grant(client, auth)

    response = client.post(
        f"/api/v1/appliances/water-heaters/{device_id}/state",
        json={"operation_mode": "gas"},
        headers=auth,
    )

    assert response.status_code == 400


# --- Envelope shape ----------------------------------------------------------------


def test_response_uses_the_documented_envelope(client, auth) -> None:
    _home(client, auth)
    listed = client.get("/api/v1/appliances/water-heaters", headers=auth)
    assert set(listed.json()) == {"data", "meta"}
