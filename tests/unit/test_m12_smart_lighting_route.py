"""Smart Lighting REST tests -- Milestone 12 Connectivity REST + Smart
Lighting.

Against the real FastAPI app and the real DI container, matching
``test_smart_home_route.py``'s pattern. Permission is granted through
the *existing*, already-shipped generic plugin-permissions route
(``POST /api/v1/plugins/{principal}/permissions/{scope}/grant``) --
these tests never call ``PermissionModel`` directly, proving the REST
surface a real operator would actually use works end to end.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from jarvis.services.smart_lighting_service import SMART_HOME_SCOPE, SMART_LIGHTING_PRINCIPAL


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
        f"/api/v1/plugins/{SMART_LIGHTING_PRINCIPAL}/permissions/{SMART_HOME_SCOPE}/grant",
        headers=auth,
    )
    assert response.status_code == 200


def _home(client, auth, name: str = "Primary Residence") -> str:
    response = client.post("/api/v1/homes", json={"name": name}, headers=auth)
    assert response.status_code == 201
    return response.json()["data"]["id"]


def _connected_light(
    client, auth, fake_connector, home_id: str, *, room_id: str | None = None
) -> str:
    """Registers a light and connects the fake connector, then makes
    the device's `external_id`/`connector_type` match by going through
    discovery -- the same real path `ConnectivityService.send_command`
    relies on, never a hand-rolled shortcut."""
    from jarvis.core.interfaces.connectivity import DiscoveredDevice

    client.post(
        "/api/v1/connectivity/connectors/home_assistant/connect", json={"config": {}}, headers=auth
    )
    fake_connector.devices = [
        DiscoveredDevice(external_id=f"light.{home_id[:8]}", name="Lamp", device_type="light")
    ]
    discovered = client.post(
        "/api/v1/connectivity/discover",
        json={"connector_type": "home_assistant", "home_id": home_id},
        headers=auth,
    ).json()["data"]
    device_id = discovered[0]["id"]
    if room_id is not None:
        client.patch(f"/api/v1/devices/{device_id}", json={"room_id": room_id}, headers=auth)
    return device_id


# --- Auth + envelope ------------------------------------------------------------


def test_every_route_requires_a_session(client) -> None:
    for method, path in (
        ("get", "/api/v1/smart-lighting/lights"),
        ("get", "/api/v1/smart-lighting/scenes"),
    ):
        assert getattr(client, method)(path).status_code in (401, 403)


# --- Permission gate ----------------------------------------------------------


def test_set_light_state_denied_without_grant_is_400(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    device_id = _connected_light(client, auth, fake_connector, home_id)

    response = client.post(
        f"/api/v1/smart-lighting/lights/{device_id}/state", json={"on": True}, headers=auth
    )

    assert response.status_code == 400
    assert "permission" in response.json()["detail"].lower()
    assert fake_connector.sent_commands == []


def test_set_light_state_succeeds_after_grant(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    device_id = _connected_light(client, auth, fake_connector, home_id)
    _grant_smart_home_permission(client, auth)

    response = client.post(
        f"/api/v1/smart-lighting/lights/{device_id}/state", json={"on": True}, headers=auth
    )

    assert response.status_code == 200
    assert response.json()["data"]["success"] is True
    assert response.json()["meta"]["success"] is True


def test_grant_is_reusable_via_the_existing_generic_plugin_route(client, auth) -> None:
    """No new grant endpoint was added -- the existing, generic
    ``/plugins/{id}/permissions/{scope}/grant`` route (Milestone 9 Task
    Group E) is what this module reuses. Confirm it reports the
    principal in its own pending-permissions listing before grant."""
    # `smart_lighting_service` is a lazy DI singleton -- declare() (which
    # populates the pending list) only runs once something constructs
    # it, so touch any of its routes first.
    client.get("/api/v1/smart-lighting/lights", headers=auth)

    pending = client.get("/api/v1/permissions/pending", headers=auth).json()["data"]
    assert any(
        row["plugin_id"] == SMART_LIGHTING_PRINCIPAL and row["scope"] == SMART_HOME_SCOPE
        for row in pending
    )


# --- Lights ----------------------------------------------------------------------


def test_get_light_not_found_is_404(client, auth) -> None:
    response = client.get("/api/v1/smart-lighting/lights/no-such-device", headers=auth)
    assert response.status_code == 404


def test_list_and_get_light_round_trip(client, auth, fake_connector) -> None:
    from jarvis.core.interfaces.connectivity import DeviceState

    home_id = _home(client, auth)
    device_id = _connected_light(client, auth, fake_connector, home_id)
    fake_connector.states[fake_connector.devices[0].external_id] = DeviceState(
        external_id=fake_connector.devices[0].external_id, status="on", attributes={}
    )

    listed = client.get("/api/v1/smart-lighting/lights", headers=auth)
    assert listed.status_code == 200
    assert listed.json()["meta"]["count"] == 1

    fetched = client.get(f"/api/v1/smart-lighting/lights/{device_id}", headers=auth)
    assert fetched.status_code == 200
    assert fetched.json()["data"]["id"] == device_id
    assert fetched.json()["data"]["on"] is True


def test_set_light_state_validation_error_is_400(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    device_id = _connected_light(client, auth, fake_connector, home_id)
    _grant_smart_home_permission(client, auth)

    response = client.post(
        f"/api/v1/smart-lighting/lights/{device_id}/state",
        json={"brightness": 500},
        headers=auth,
    )

    assert response.status_code == 400


# --- Room / group fan-out -----------------------------------------------------


def test_set_room_state_controls_every_light(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    room_response = client.post(
        "/api/v1/smart-home/rooms", json={"home_id": home_id, "name": "Living Room"}, headers=auth
    )
    room_id = room_response.json()["data"]["id"]
    device_id = _connected_light(client, auth, fake_connector, home_id, room_id=room_id)
    _grant_smart_home_permission(client, auth)

    response = client.post(
        f"/api/v1/smart-lighting/rooms/{room_id}/state", json={"on": True}, headers=auth
    )

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["count"] == 1
    assert body["meta"]["succeeded"] == 1
    assert body["data"][0]["device_id"] == device_id


def test_set_group_state_ignores_non_light_members(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    group = client.post(
        "/api/v1/smart-home/device-groups",
        json={"home_id": home_id, "name": "Movie Night"},
        headers=auth,
    ).json()["data"]
    light_id = _connected_light(client, auth, fake_connector, home_id)
    switch = client.post(
        "/api/v1/devices",
        json={"home_id": home_id, "name": "Switch", "device_type": "switch"},
        headers=auth,
    ).json()["data"]
    client.post(
        f"/api/v1/smart-home/device-groups/{group['id']}/members",
        json={"device_id": light_id},
        headers=auth,
    )
    client.post(
        f"/api/v1/smart-home/device-groups/{group['id']}/members",
        json={"device_id": switch["id"]},
        headers=auth,
    )
    _grant_smart_home_permission(client, auth)

    response = client.post(
        f"/api/v1/smart-lighting/groups/{group['id']}/state", json={"on": True}, headers=auth
    )

    assert response.status_code == 200
    assert [row["device_id"] for row in response.json()["data"]] == [light_id]


# --- Scenes ----------------------------------------------------------------------


def test_scene_lifecycle(client, auth, fake_connector) -> None:
    home_id = _home(client, auth)
    device_id = _connected_light(client, auth, fake_connector, home_id)
    _grant_smart_home_permission(client, auth)

    created = client.post(
        "/api/v1/smart-lighting/scenes",
        json={
            "home_id": home_id,
            "name": "Movie Night",
            "targets": [{"device_id": device_id, "on": True, "brightness": 15}],
        },
        headers=auth,
    )
    assert created.status_code == 201
    scene_id = created.json()["data"]["id"]

    listed = client.get("/api/v1/smart-lighting/scenes", headers=auth)
    assert listed.json()["meta"]["count"] == 1

    fetched = client.get(f"/api/v1/smart-lighting/scenes/{scene_id}", headers=auth)
    assert fetched.status_code == 200

    applied = client.post(f"/api/v1/smart-lighting/scenes/{scene_id}/apply", headers=auth)
    assert applied.status_code == 200
    assert applied.json()["data"][0]["success"] is True
    assert fake_connector.sent_commands == [
        (fake_connector.devices[0].external_id, "turn_on", {"brightness_pct": 15})
    ]

    deleted = client.delete(f"/api/v1/smart-lighting/scenes/{scene_id}", headers=auth)
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/smart-lighting/scenes/{scene_id}", headers=auth).status_code == 404


def test_create_scene_without_permission_is_400(client, auth) -> None:
    home_id = _home(client, auth)
    response = client.post(
        "/api/v1/smart-lighting/scenes",
        json={
            "home_id": home_id,
            "name": "Movie Night",
            "targets": [{"device_id": "x", "on": True}],
        },
        headers=auth,
    )
    assert response.status_code == 400


def test_delete_unknown_scene_is_404(client, auth) -> None:
    _grant_smart_home_permission(client, auth)
    response = client.delete("/api/v1/smart-lighting/scenes/no-such-scene", headers=auth)
    assert response.status_code == 404
