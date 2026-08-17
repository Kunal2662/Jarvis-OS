"""Appliance Control REST tests -- Milestone 12 Appliance Control (Core
Appliance Slice: Fans + Covers).

Against the real FastAPI app and the real DI container, matching
``test_m12_smart_switches_route.py``'s pattern. Permission is granted
through the existing generic plugin-permissions route, never
``PermissionModel`` directly.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from jarvis.services.appliance_service import APPLIANCE_PRINCIPAL, SMART_HOME_SCOPE


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
        f"/api/v1/plugins/{APPLIANCE_PRINCIPAL}/permissions/{SMART_HOME_SCOPE}/grant",
        headers=auth,
    )
    assert response.status_code == 200


def _home(client, auth, name: str = "Primary Residence") -> str:
    response = client.post("/api/v1/homes", json={"name": name}, headers=auth)
    assert response.status_code == 201
    return response.json()["data"]["id"]


def _connected_fan(client, auth, fake_connector, home_id: str) -> str:
    from jarvis.core.interfaces.connectivity import DiscoveredDevice

    client.post(
        "/api/v1/connectivity/connectors/home_assistant/connect", json={"config": {}}, headers=auth
    )
    fake_connector.devices = [
        DiscoveredDevice(
            external_id=f"fan.{home_id[:8]}",
            name="Living Room Fan",
            device_type="appliance",
            metadata={"domain": "fan"},
        )
    ]
    discovered = client.post(
        "/api/v1/connectivity/discover",
        json={"connector_type": "home_assistant", "home_id": home_id},
        headers=auth,
    ).json()["data"]
    return discovered[0]["id"]


def _connected_cover(client, auth, fake_connector, home_id: str) -> str:
    from jarvis.core.interfaces.connectivity import DiscoveredDevice

    client.post(
        "/api/v1/connectivity/connectors/home_assistant/connect", json={"config": {}}, headers=auth
    )
    fake_connector.devices = [
        DiscoveredDevice(
            external_id=f"cover.{home_id[:8]}",
            name="Living Room Blind",
            device_type="appliance",
            metadata={"domain": "cover"},
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
        ("get", "/api/v1/appliances/fans"),
        ("get", "/api/v1/appliances/fans/x"),
        ("get", "/api/v1/appliances/covers"),
        ("get", "/api/v1/appliances/covers/x"),
    ):
        assert getattr(client, method)(path).status_code in (401, 403)


def test_fan_responses_use_the_documented_envelope(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    _connected_fan(client, auth, fake_connector, home_id)
    listed = client.get("/api/v1/appliances/fans", headers=auth)
    assert set(listed.json()) == {"data", "meta"}
    assert listed.json()["meta"]["count"] == 1


def test_cover_responses_use_the_documented_envelope(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    _connected_cover(client, auth, fake_connector, home_id)
    listed = client.get("/api/v1/appliances/covers", headers=auth)
    assert set(listed.json()) == {"data", "meta"}
    assert listed.json()["meta"]["count"] == 1


# --- Reads are ungated (unlike Sensors) -----------------------------------------


def test_fan_list_and_get_do_not_require_permission_grant(client, auth, fake_connector) -> None:
    from jarvis.core.interfaces.connectivity import DeviceState

    home_id = _home(client, auth)
    device_id = _connected_fan(client, auth, fake_connector, home_id)
    fake_connector.states[fake_connector.devices[0].external_id] = DeviceState(
        external_id=fake_connector.devices[0].external_id, status="on", attributes={}
    )

    listed = client.get("/api/v1/appliances/fans", headers=auth)
    assert listed.status_code == 200

    fetched = client.get(f"/api/v1/appliances/fans/{device_id}", headers=auth)
    assert fetched.status_code == 200
    assert fetched.json()["data"]["id"] == device_id


def test_cover_list_and_get_do_not_require_permission_grant(client, auth, fake_connector) -> None:
    from jarvis.core.interfaces.connectivity import DeviceState

    home_id = _home(client, auth)
    device_id = _connected_cover(client, auth, fake_connector, home_id)
    fake_connector.states[fake_connector.devices[0].external_id] = DeviceState(
        external_id=fake_connector.devices[0].external_id, status="closed", attributes={}
    )

    listed = client.get("/api/v1/appliances/covers", headers=auth)
    assert listed.status_code == 200

    fetched = client.get(f"/api/v1/appliances/covers/{device_id}", headers=auth)
    assert fetched.status_code == 200
    assert fetched.json()["data"]["id"] == device_id


def test_get_unknown_fan_is_404(client, auth) -> None:
    response = client.get("/api/v1/appliances/fans/no-such-device", headers=auth)
    assert response.status_code == 404


def test_get_unknown_cover_is_404(client, auth) -> None:
    response = client.get("/api/v1/appliances/covers/no-such-device", headers=auth)
    assert response.status_code == 404


def test_get_fan_on_non_appliance_device_is_404(client, auth) -> None:
    home_id = _home(client, auth)
    lock = client.post(
        "/api/v1/devices",
        json={"home_id": home_id, "name": "Front Door", "device_type": "lock"},
        headers=auth,
    ).json()["data"]

    response = client.get(f"/api/v1/appliances/fans/{lock['id']}", headers=auth)

    assert response.status_code == 404


def test_get_fan_on_cover_device_is_404_wrong_domain(client, auth, fake_connector) -> None:
    """A cover id given to the fans route is a real, tested 400/404 --
    see Logic Contract §16."""
    home_id = _home(client, auth)
    cover_id = _connected_cover(client, auth, fake_connector, home_id)

    response = client.get(f"/api/v1/appliances/fans/{cover_id}", headers=auth)

    assert response.status_code == 404


def test_get_cover_on_fan_device_is_404_wrong_domain(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    fan_id = _connected_fan(client, auth, fake_connector, home_id)

    response = client.get(f"/api/v1/appliances/covers/{fan_id}", headers=auth)

    assert response.status_code == 404


# --- Permission gate on mutations only -------------------------------------------


def test_fan_on_denied_without_grant_is_400(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    device_id = _connected_fan(client, auth, fake_connector, home_id)

    response = client.post(f"/api/v1/appliances/fans/{device_id}/on", headers=auth)

    assert response.status_code == 400
    assert "permission" in response.json()["detail"].lower()
    assert fake_connector.sent_commands == []


def test_fan_off_denied_without_grant_is_400(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    device_id = _connected_fan(client, auth, fake_connector, home_id)

    response = client.post(f"/api/v1/appliances/fans/{device_id}/off", headers=auth)

    assert response.status_code == 400
    assert fake_connector.sent_commands == []


def test_cover_open_denied_without_grant_is_400(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    device_id = _connected_cover(client, auth, fake_connector, home_id)

    response = client.post(f"/api/v1/appliances/covers/{device_id}/open", headers=auth)

    assert response.status_code == 400
    assert fake_connector.sent_commands == []


def test_cover_close_denied_without_grant_is_400(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    device_id = _connected_cover(client, auth, fake_connector, home_id)

    response = client.post(f"/api/v1/appliances/covers/{device_id}/close", headers=auth)

    assert response.status_code == 400
    assert fake_connector.sent_commands == []


def test_fan_on_and_off_succeed_after_grant(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    device_id = _connected_fan(client, auth, fake_connector, home_id)
    _grant_smart_home_permission(client, auth)

    turned_on = client.post(f"/api/v1/appliances/fans/{device_id}/on", headers=auth)
    assert turned_on.status_code == 200
    assert turned_on.json()["data"]["success"] is True
    assert turned_on.json()["meta"]["success"] is True

    turned_off = client.post(f"/api/v1/appliances/fans/{device_id}/off", headers=auth)
    assert turned_off.status_code == 200
    assert turned_off.json()["data"]["success"] is True

    assert [c[1] for c in fake_connector.sent_commands] == ["turn_on", "turn_off"]


def test_cover_open_and_close_succeed_after_grant(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    device_id = _connected_cover(client, auth, fake_connector, home_id)
    _grant_smart_home_permission(client, auth)

    opened = client.post(f"/api/v1/appliances/covers/{device_id}/open", headers=auth)
    assert opened.status_code == 200
    assert opened.json()["data"]["success"] is True

    closed = client.post(f"/api/v1/appliances/covers/{device_id}/close", headers=auth)
    assert closed.status_code == 200
    assert closed.json()["data"]["success"] is True

    assert [c[1] for c in fake_connector.sent_commands] == ["open_cover", "close_cover"]


def test_fan_on_unknown_device_is_400(client, auth) -> None:
    response = client.post("/api/v1/appliances/fans/no-such-device/on", headers=auth)
    assert response.status_code == 400


def test_cover_open_unknown_device_is_400(client, auth) -> None:
    response = client.post("/api/v1/appliances/covers/no-such-device/open", headers=auth)
    assert response.status_code == 400


def test_fan_on_a_cover_device_is_400_wrong_domain(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    cover_id = _connected_cover(client, auth, fake_connector, home_id)
    _grant_smart_home_permission(client, auth)

    response = client.post(f"/api/v1/appliances/fans/{cover_id}/on", headers=auth)

    assert response.status_code == 400
    assert fake_connector.sent_commands == []


# --- Connector-level failure surfaces as success: false, not an HTTP error --------


def test_fan_on_reports_connector_rejection_as_success_false(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    device_id = _connected_fan(client, auth, fake_connector, home_id)
    _grant_smart_home_permission(client, auth)
    fake_connector.next_command_succeeds = False

    response = client.post(f"/api/v1/appliances/fans/{device_id}/on", headers=auth)

    assert response.status_code == 200
    assert response.json()["data"]["success"] is False
    assert response.json()["meta"]["success"] is False
