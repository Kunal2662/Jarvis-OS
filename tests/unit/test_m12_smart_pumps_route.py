"""Smart Pumps REST tests -- Milestone 12 Smart Pumps (Switch-Backed
Device Slice).

Against the real FastAPI app and the real DI container, matching
``test_m12_smart_switches_route.py``'s pattern. Permission is granted
through the existing generic plugin-permissions route (the switch
service's own ``core:smart_switch`` grant -- the pump surface declares
none of its own), never ``PermissionModel`` directly.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from jarvis.services.smart_switch_service import SMART_HOME_SCOPE, SMART_SWITCH_PRINCIPAL


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
    """The switch service's existing grant -- the pump surface inherits
    it via delegation and requires nothing more."""
    response = client.post(
        f"/api/v1/plugins/{SMART_SWITCH_PRINCIPAL}/permissions/{SMART_HOME_SCOPE}/grant",
        headers=auth,
    )
    assert response.status_code == 200


def _home(client, auth, name: str = "Primary Residence") -> str:
    response = client.post("/api/v1/homes", json={"name": name}, headers=auth)
    assert response.status_code == 201
    return response.json()["data"]["id"]


def _connected_pump(client, auth, fake_connector, home_id: str) -> str:
    from jarvis.core.interfaces.connectivity import DiscoveredDevice

    client.post(
        "/api/v1/connectivity/connectors/home_assistant/connect", json={"config": {}}, headers=auth
    )
    fake_connector.devices = [
        DiscoveredDevice(
            external_id=f"switch.{home_id[:8]}", name="Water Pump", device_type="switch"
        )
    ]
    discovered = client.post(
        "/api/v1/connectivity/discover",
        json={"connector_type": "home_assistant", "home_id": home_id},
        headers=auth,
    ).json()["data"]
    return discovered[0]["id"]


# --- Auth + envelope ------------------------------------------------------------


def test_every_route_requires_a_session(client) -> None:
    for method, path in (
        ("get", "/api/v1/pumps/x"),
        ("post", "/api/v1/pumps/x/on"),
        ("post", "/api/v1/pumps/x/off"),
    ):
        assert getattr(client, method)(path).status_code in (401, 403)


def test_responses_use_the_documented_envelope(client, auth, fake_connector) -> None:
    from jarvis.core.interfaces.connectivity import DeviceState

    home_id = _home(client, auth)
    device_id = _connected_pump(client, auth, fake_connector, home_id)
    fake_connector.states[fake_connector.devices[0].external_id] = DeviceState(
        external_id=fake_connector.devices[0].external_id, status="on", attributes={}
    )

    response = client.get(f"/api/v1/pumps/{device_id}", headers=auth)

    assert set(response.json()) == {"data", "meta"}
    assert response.json()["data"]["kind"] == "pump"


def test_no_pump_list_route_exists(client, auth) -> None:
    """Deliberate: ``GET /switches`` already enumerates every
    pump-controllable device, so a ``GET /pumps`` list route would be a
    duplicate surface. Pinned so it is never added by accident."""
    response = client.get("/api/v1/pumps", headers=auth)
    assert response.status_code == 404


# --- Reads are ungated -----------------------------------------------------------


def test_get_state_does_not_require_permission_grant(client, auth, fake_connector) -> None:
    from jarvis.core.interfaces.connectivity import DeviceState

    home_id = _home(client, auth)
    device_id = _connected_pump(client, auth, fake_connector, home_id)
    fake_connector.states[fake_connector.devices[0].external_id] = DeviceState(
        external_id=fake_connector.devices[0].external_id, status="on", attributes={}
    )

    response = client.get(f"/api/v1/pumps/{device_id}", headers=auth)

    assert response.status_code == 200
    assert response.json()["data"]["id"] == device_id
    assert response.json()["data"]["on"] is True


def test_get_unknown_pump_is_404(client, auth) -> None:
    response = client.get("/api/v1/pumps/no-such-device", headers=auth)
    assert response.status_code == 404


def test_get_pump_on_non_switch_device_is_404(client, auth) -> None:
    home_id = _home(client, auth)
    lock = client.post(
        "/api/v1/devices",
        json={"home_id": home_id, "name": "Front Door", "device_type": "lock"},
        headers=auth,
    ).json()["data"]

    response = client.get(f"/api/v1/pumps/{lock['id']}", headers=auth)

    assert response.status_code == 404
    assert "not a pump" in response.json()["detail"]


# --- Permission gate on mutations only --------------------------------------------


def test_pump_on_denied_without_grant_is_400(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    device_id = _connected_pump(client, auth, fake_connector, home_id)

    response = client.post(f"/api/v1/pumps/{device_id}/on", headers=auth)

    assert response.status_code == 400
    assert "permission" in response.json()["detail"].lower()
    assert fake_connector.sent_commands == []


def test_pump_off_denied_without_grant_is_400(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    device_id = _connected_pump(client, auth, fake_connector, home_id)

    response = client.post(f"/api/v1/pumps/{device_id}/off", headers=auth)

    assert response.status_code == 400
    assert fake_connector.sent_commands == []


def test_pump_on_and_off_succeed_after_grant(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    device_id = _connected_pump(client, auth, fake_connector, home_id)
    _grant_smart_home_permission(client, auth)

    turned_on = client.post(f"/api/v1/pumps/{device_id}/on", headers=auth)
    assert turned_on.status_code == 200
    assert turned_on.json()["data"]["success"] is True
    assert turned_on.json()["data"]["kind"] == "pump"
    assert turned_on.json()["meta"]["success"] is True

    turned_off = client.post(f"/api/v1/pumps/{device_id}/off", headers=auth)
    assert turned_off.status_code == 200
    assert turned_off.json()["data"]["success"] is True
    assert turned_off.json()["meta"]["success"] is True

    assert [c[1] for c in fake_connector.sent_commands] == ["turn_on", "turn_off"]


def test_pump_on_unknown_device_is_400(client, auth) -> None:
    response = client.post("/api/v1/pumps/no-such-device/on", headers=auth)
    assert response.status_code == 400


def test_pump_on_non_switch_device_is_400(client, auth, fake_connector) -> None:
    """Even fully granted, a lock is never pump-controllable -- the
    pump identity check rejects it with a pump-flavored error."""
    home_id = _home(client, auth)
    _connected_pump(client, auth, fake_connector, home_id)
    lock = client.post(
        "/api/v1/devices",
        json={"home_id": home_id, "name": "Front Door", "device_type": "lock"},
        headers=auth,
    ).json()["data"]
    _grant_smart_home_permission(client, auth)

    response = client.post(f"/api/v1/pumps/{lock['id']}/on", headers=auth)

    assert response.status_code == 400
    assert "not a pump" in response.json()["detail"]
    assert fake_connector.sent_commands == []
