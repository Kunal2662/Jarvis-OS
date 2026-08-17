"""Alarm control panels REST tests -- Milestone 12 Security & Safety
(alarm_control_panel Integration Slice).

Against the real FastAPI app and the real DI container, matching
``test_m12_sirens_route.py``'s pattern. Permission is granted through
the existing generic plugin-permissions route, never ``PermissionModel``
directly.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from jarvis.services.alarm_control_panel_service import (
    ALARM_CONTROL_PANEL_PRINCIPAL,
    SMART_HOME_SCOPE,
)


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
        f"/api/v1/plugins/{ALARM_CONTROL_PANEL_PRINCIPAL}/permissions/{SMART_HOME_SCOPE}/grant",
        headers=auth,
    )
    assert response.status_code == 200


def _home(client, auth, name: str = "Primary Residence") -> str:
    response = client.post("/api/v1/homes", json={"name": name}, headers=auth)
    assert response.status_code == 201
    return response.json()["data"]["id"]


def _connected_panel(client, auth, fake_connector, home_id: str) -> str:
    from jarvis.core.interfaces.connectivity import DiscoveredDevice

    client.post(
        "/api/v1/connectivity/connectors/home_assistant/connect", json={"config": {}}, headers=auth
    )
    fake_connector.devices = [
        DiscoveredDevice(
            external_id=f"alarm_control_panel.{home_id[:8]}",
            name="Front Panel",
            device_type="other",
            metadata={"domain": "alarm_control_panel"},
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
    assert client.get("/api/v1/alarm-control-panels").status_code in (401, 403)


def test_responses_use_the_documented_envelope(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    _connected_panel(client, auth, fake_connector, home_id)
    listed = client.get("/api/v1/alarm-control-panels", headers=auth)
    assert set(listed.json()) == {"data", "meta"}
    assert listed.json()["meta"]["count"] == 1


# --- Permission gate ----------------------------------------------------------


def test_arm_home_denied_without_grant_is_400(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    device_id = _connected_panel(client, auth, fake_connector, home_id)

    response = client.post(f"/api/v1/alarm-control-panels/{device_id}/arm_home", headers=auth)

    assert response.status_code == 400
    assert "permission" in response.json()["detail"].lower()
    assert fake_connector.sent_commands == []


def test_arm_away_denied_without_grant_is_400(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    device_id = _connected_panel(client, auth, fake_connector, home_id)

    response = client.post(f"/api/v1/alarm-control-panels/{device_id}/arm_away", headers=auth)

    assert response.status_code == 400
    assert fake_connector.sent_commands == []


def test_disarm_denied_without_grant_is_400(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    device_id = _connected_panel(client, auth, fake_connector, home_id)

    response = client.post(f"/api/v1/alarm-control-panels/{device_id}/disarm", headers=auth)

    assert response.status_code == 400
    assert fake_connector.sent_commands == []


def test_arm_home_arm_away_disarm_succeed_after_grant(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    device_id = _connected_panel(client, auth, fake_connector, home_id)
    _grant_smart_home_permission(client, auth)

    armed_home = client.post(f"/api/v1/alarm-control-panels/{device_id}/arm_home", headers=auth)
    assert armed_home.status_code == 200
    assert armed_home.json()["data"]["success"] is True
    assert armed_home.json()["meta"]["success"] is True

    armed_away = client.post(f"/api/v1/alarm-control-panels/{device_id}/arm_away", headers=auth)
    assert armed_away.status_code == 200
    assert armed_away.json()["data"]["success"] is True

    disarmed = client.post(f"/api/v1/alarm-control-panels/{device_id}/disarm", headers=auth)
    assert disarmed.status_code == 200
    assert disarmed.json()["data"]["success"] is True

    assert [c[1] for c in fake_connector.sent_commands] == [
        "alarm_arm_home",
        "alarm_arm_away",
        "alarm_disarm",
    ]
    for _external_id, _command, payload in fake_connector.sent_commands:
        assert payload == {}


# --- Lists / gets ----------------------------------------------------------------


def test_get_alarm_control_panel_not_found_is_404(client, auth) -> None:
    response = client.get("/api/v1/alarm-control-panels/no-such-device", headers=auth)
    assert response.status_code == 404


def test_arm_home_unknown_device_is_400(client, auth) -> None:
    response = client.post("/api/v1/alarm-control-panels/no-such-device/arm_home", headers=auth)
    assert response.status_code == 400


def test_arm_away_unknown_device_is_400(client, auth) -> None:
    response = client.post("/api/v1/alarm-control-panels/no-such-device/arm_away", headers=auth)
    assert response.status_code == 400


def test_disarm_unknown_device_is_400(client, auth) -> None:
    response = client.post("/api/v1/alarm-control-panels/no-such-device/disarm", headers=auth)
    assert response.status_code == 400


def test_list_and_get_alarm_control_panel_round_trip(client, auth, fake_connector) -> None:
    from jarvis.core.interfaces.connectivity import DeviceState

    home_id = _home(client, auth)
    device_id = _connected_panel(client, auth, fake_connector, home_id)
    fake_connector.states[fake_connector.devices[0].external_id] = DeviceState(
        external_id=fake_connector.devices[0].external_id, status="armed_home", attributes={}
    )

    listed = client.get("/api/v1/alarm-control-panels", headers=auth)
    assert listed.status_code == 200
    assert listed.json()["meta"]["count"] == 1

    fetched = client.get(f"/api/v1/alarm-control-panels/{device_id}", headers=auth)
    assert fetched.status_code == 200
    assert fetched.json()["data"]["id"] == device_id
    assert fetched.json()["data"]["state"] == "armed_home"


def test_get_alarm_control_panel_on_non_panel_other_device_is_404(client, auth) -> None:
    home_id = _home(client, auth)
    other = client.post(
        "/api/v1/devices",
        json={"home_id": home_id, "name": "Mystery Entity", "device_type": "other"},
        headers=auth,
    ).json()["data"]

    response = client.get(f"/api/v1/alarm-control-panels/{other['id']}", headers=auth)

    assert response.status_code == 404


def test_get_alarm_control_panel_on_switch_device_is_404(client, auth) -> None:
    home_id = _home(client, auth)
    switch = client.post(
        "/api/v1/devices",
        json={"home_id": home_id, "name": "Switch", "device_type": "switch"},
        headers=auth,
    ).json()["data"]

    response = client.get(f"/api/v1/alarm-control-panels/{switch['id']}", headers=auth)

    assert response.status_code == 404


def test_get_alarm_control_panel_on_siren_device_is_404(client, auth) -> None:
    """A sibling ``device_type="other"`` category (siren) must never
    false-match through the REST layer either."""
    home_id = _home(client, auth)
    siren = client.post(
        "/api/v1/devices",
        json={
            "home_id": home_id,
            "name": "Front Yard Siren",
            "device_type": "other",
        },
        headers=auth,
    ).json()["data"]

    response = client.get(f"/api/v1/alarm-control-panels/{siren['id']}", headers=auth)

    assert response.status_code == 404


def test_no_code_or_pin_query_or_body_parameter_is_accepted(client, auth, fake_connector) -> None:
    """A caller attempting to smuggle a code through as a query
    parameter is silently ignored, not accepted -- the route has no
    such parameter declared."""
    home_id = _home(client, auth)
    device_id = _connected_panel(client, auth, fake_connector, home_id)
    _grant_smart_home_permission(client, auth)

    response = client.post(
        f"/api/v1/alarm-control-panels/{device_id}/disarm",
        params={"code": "1234", "pin": "0000"},
        headers=auth,
    )

    assert response.status_code == 200
    assert len(fake_connector.sent_commands) == 1
    _external_id, command, payload = fake_connector.sent_commands[0]
    assert command == "alarm_disarm"
    assert payload == {}
