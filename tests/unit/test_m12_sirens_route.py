"""Sirens REST tests -- Milestone 12 Security & Safety (Siren
Integration Slice).

Against the real FastAPI app and the real DI container, matching
``test_m12_smart_locks_route.py``'s pattern. Permission is granted
through the existing generic plugin-permissions route, never
``PermissionModel`` directly.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from jarvis.services.siren_service import SIREN_PRINCIPAL, SMART_HOME_SCOPE


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
        f"/api/v1/plugins/{SIREN_PRINCIPAL}/permissions/{SMART_HOME_SCOPE}/grant",
        headers=auth,
    )
    assert response.status_code == 200


def _home(client, auth, name: str = "Primary Residence") -> str:
    response = client.post("/api/v1/homes", json={"name": name}, headers=auth)
    assert response.status_code == 201
    return response.json()["data"]["id"]


def _connected_siren(client, auth, fake_connector, home_id: str) -> str:
    from jarvis.core.interfaces.connectivity import DiscoveredDevice

    client.post(
        "/api/v1/connectivity/connectors/home_assistant/connect", json={"config": {}}, headers=auth
    )
    fake_connector.devices = [
        DiscoveredDevice(
            external_id=f"siren.{home_id[:8]}",
            name="Front Yard Siren",
            device_type="other",
            metadata={"domain": "siren"},
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
    assert client.get("/api/v1/sirens").status_code in (401, 403)


def test_responses_use_the_documented_envelope(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    _connected_siren(client, auth, fake_connector, home_id)
    listed = client.get("/api/v1/sirens", headers=auth)
    assert set(listed.json()) == {"data", "meta"}
    assert listed.json()["meta"]["count"] == 1


# --- Permission gate ----------------------------------------------------------


def test_turn_on_denied_without_grant_is_400(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    device_id = _connected_siren(client, auth, fake_connector, home_id)

    response = client.post(f"/api/v1/sirens/{device_id}/turn_on", headers=auth)

    assert response.status_code == 400
    assert "permission" in response.json()["detail"].lower()
    assert fake_connector.sent_commands == []


def test_turn_off_denied_without_grant_is_400(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    device_id = _connected_siren(client, auth, fake_connector, home_id)

    response = client.post(f"/api/v1/sirens/{device_id}/turn_off", headers=auth)

    assert response.status_code == 400
    assert fake_connector.sent_commands == []


def test_turn_on_and_turn_off_succeed_after_grant(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    device_id = _connected_siren(client, auth, fake_connector, home_id)
    _grant_smart_home_permission(client, auth)

    turned_on = client.post(f"/api/v1/sirens/{device_id}/turn_on", headers=auth)
    assert turned_on.status_code == 200
    assert turned_on.json()["data"]["success"] is True
    assert turned_on.json()["meta"]["success"] is True

    turned_off = client.post(f"/api/v1/sirens/{device_id}/turn_off", headers=auth)
    assert turned_off.status_code == 200
    assert turned_off.json()["data"]["success"] is True

    assert [c[1] for c in fake_connector.sent_commands] == ["turn_on", "turn_off"]


# --- Lists / gets ----------------------------------------------------------------


def test_get_siren_not_found_is_404(client, auth) -> None:
    response = client.get("/api/v1/sirens/no-such-device", headers=auth)
    assert response.status_code == 404


def test_turn_on_unknown_device_is_400(client, auth) -> None:
    response = client.post("/api/v1/sirens/no-such-device/turn_on", headers=auth)
    assert response.status_code == 400


def test_list_and_get_siren_round_trip(client, auth, fake_connector) -> None:
    from jarvis.core.interfaces.connectivity import DeviceState

    home_id = _home(client, auth)
    device_id = _connected_siren(client, auth, fake_connector, home_id)
    fake_connector.states[fake_connector.devices[0].external_id] = DeviceState(
        external_id=fake_connector.devices[0].external_id, status="on", attributes={}
    )

    listed = client.get("/api/v1/sirens", headers=auth)
    assert listed.status_code == 200
    assert listed.json()["meta"]["count"] == 1

    fetched = client.get(f"/api/v1/sirens/{device_id}", headers=auth)
    assert fetched.status_code == 200
    assert fetched.json()["data"]["id"] == device_id
    assert fetched.json()["data"]["on"] is True


def test_get_siren_on_non_siren_other_device_is_404(client, auth) -> None:
    home_id = _home(client, auth)
    other = client.post(
        "/api/v1/devices",
        json={"home_id": home_id, "name": "Mystery Entity", "device_type": "other"},
        headers=auth,
    ).json()["data"]

    response = client.get(f"/api/v1/sirens/{other['id']}", headers=auth)

    assert response.status_code == 404


def test_get_siren_on_switch_device_is_404(client, auth) -> None:
    home_id = _home(client, auth)
    switch = client.post(
        "/api/v1/devices",
        json={"home_id": home_id, "name": "Switch", "device_type": "switch"},
        headers=auth,
    ).json()["data"]

    response = client.get(f"/api/v1/sirens/{switch['id']}", headers=auth)

    assert response.status_code == 404
