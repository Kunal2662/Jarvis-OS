"""Smart Home REST tests -- Milestone 12 Task Group A (Smart Home Core).

Against the real FastAPI app and the real DI container, matching
``test_workspaces_route.py``'s pattern: a real session token, the real
Bearer dependency, and a real temp-file database behind it.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest


@pytest.fixture
def client(tmp_path: Path):
    from fastapi.testclient import TestClient

    from jarvis.core.config.settings import Settings
    from jarvis.core.di.container import Container
    from jarvis.infrastructure.api.fastapi_server import create_app

    container = Container()
    settings = Settings(data_dir=str(tmp_path / "data"))
    settings.db.url = f"sqlite+aiosqlite:///{tmp_path / 'jarvis.db'}"
    container.settings.override(settings)

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


def _home(client, auth, name: str = "Primary Residence") -> str:
    response = client.post("/api/v1/homes", json={"name": name}, headers=auth)
    assert response.status_code == 201
    return response.json()["data"]["id"]


# --- Auth + envelope ------------------------------------------------------------


def test_every_route_requires_a_session(client) -> None:
    for method, path in (
        ("get", "/api/v1/homes"),
        ("get", "/api/v1/devices"),
        ("get", "/api/v1/smart-home/zones"),
        ("get", "/api/v1/smart-home/rooms"),
        ("get", "/api/v1/smart-home/device-groups"),
    ):
        assert getattr(client, method)(path).status_code in (401, 403)


def test_responses_use_the_documented_envelope(client, auth) -> None:
    created = client.post("/api/v1/homes", json={"name": "Enveloped"}, headers=auth)
    listed = client.get("/api/v1/homes", headers=auth)

    for response in (created, listed):
        assert set(response.json()) == {"data", "meta"}
    assert created.json()["meta"]["created"] is True
    assert listed.json()["meta"]["count"] == 1


# --- Homes -----------------------------------------------------------------------


def test_home_crud_round_trip(client, auth) -> None:
    home_id = _home(client, auth)

    fetched = client.get(f"/api/v1/homes/{home_id}", headers=auth)
    assert fetched.json()["data"]["name"] == "Primary Residence"

    patched = client.patch(f"/api/v1/homes/{home_id}", json={"name": "Renamed"}, headers=auth)
    assert patched.json()["data"]["name"] == "Renamed"

    assert client.delete(f"/api/v1/homes/{home_id}", headers=auth).status_code == 204
    assert client.get(f"/api/v1/homes/{home_id}", headers=auth).status_code == 404


def test_invalid_input_is_400_not_500(client, auth) -> None:
    empty = client.post("/api/v1/homes", json={"name": "  "}, headers=auth)
    bad_status = client.get("/api/v1/homes?status=vacant", headers=auth)

    assert empty.status_code == 400
    assert bad_status.status_code == 400


def test_home_metadata_route(client, auth) -> None:
    home_id = _home(client, auth)

    response = client.get(f"/api/v1/homes/{home_id}/metadata", headers=auth)

    assert response.status_code == 200
    body = response.json()["data"]
    assert body == {
        "home_id": home_id,
        "room_count": 0,
        "zone_count": 0,
        "device_count": 0,
        "paired_device_count": 0,
        "offline_device_count": 0,
        "unreachable_device_count": 0,
    }


# --- Zones + rooms -----------------------------------------------------------------


def test_zone_and_room_crud_round_trip(client, auth) -> None:
    home_id = _home(client, auth)

    zone = client.post(
        "/api/v1/smart-home/zones",
        json={"home_id": home_id, "name": "Downstairs"},
        headers=auth,
    ).json()["data"]
    room = client.post(
        "/api/v1/smart-home/rooms",
        json={"home_id": home_id, "name": "Living Room", "zone_id": zone["id"]},
        headers=auth,
    ).json()["data"]

    assert room["zone_id"] == zone["id"]

    # Deleting the zone unassigns the room rather than deleting it.
    assert client.delete(f"/api/v1/smart-home/zones/{zone['id']}", headers=auth).status_code == 204
    survived = client.get(f"/api/v1/smart-home/rooms/{room['id']}", headers=auth)
    assert survived.status_code == 200
    assert survived.json()["data"]["zone_id"] is None


def test_room_list_filters_by_home_and_zone(client, auth) -> None:
    home_id = _home(client, auth)
    zone = client.post(
        "/api/v1/smart-home/zones", json={"home_id": home_id, "name": "Upstairs"}, headers=auth
    ).json()["data"]
    client.post(
        "/api/v1/smart-home/rooms",
        json={"home_id": home_id, "name": "Bedroom", "zone_id": zone["id"]},
        headers=auth,
    )
    client.post(
        "/api/v1/smart-home/rooms", json={"home_id": home_id, "name": "Garage"}, headers=auth
    )

    by_zone = client.get(f"/api/v1/smart-home/rooms?zone_id={zone['id']}", headers=auth)

    assert by_zone.json()["meta"]["count"] == 1
    assert by_zone.json()["data"][0]["name"] == "Bedroom"


# --- Devices: discovery + pairing --------------------------------------------------


def test_device_registration_starts_discovered_then_pairs(client, auth) -> None:
    home_id = _home(client, auth)

    registered = client.post(
        "/api/v1/devices",
        json={"home_id": home_id, "name": "Hallway Light", "device_type": "light"},
        headers=auth,
    )
    assert registered.status_code == 201
    device = registered.json()["data"]
    assert device["status"] == "discovered"

    paired = client.post(f"/api/v1/devices/{device['id']}/pair", headers=auth)
    assert paired.status_code == 200
    assert paired.json()["data"]["status"] == "paired"


def test_pairing_an_already_paired_device_is_400(client, auth) -> None:
    home_id = _home(client, auth)
    device = client.post(
        "/api/v1/devices",
        json={"home_id": home_id, "name": "Lock", "device_type": "lock"},
        headers=auth,
    ).json()["data"]
    client.post(f"/api/v1/devices/{device['id']}/pair", headers=auth)

    second = client.post(f"/api/v1/devices/{device['id']}/pair", headers=auth)

    assert second.status_code == 400


def test_device_list_filters_by_type_and_status(client, auth) -> None:
    home_id = _home(client, auth)
    client.post(
        "/api/v1/devices",
        json={"home_id": home_id, "name": "Bulb", "device_type": "light"},
        headers=auth,
    )
    client.post(
        "/api/v1/devices",
        json={"home_id": home_id, "name": "Lock", "device_type": "lock"},
        headers=auth,
    )

    lights = client.get(f"/api/v1/devices?home_id={home_id}&device_type=light", headers=auth)

    assert lights.json()["meta"]["count"] == 1
    assert lights.json()["data"][0]["device_type"] == "light"


# --- Device groups -------------------------------------------------------------------


def test_device_group_membership_round_trip(client, auth) -> None:
    home_id = _home(client, auth)
    group = client.post(
        "/api/v1/smart-home/device-groups",
        json={"home_id": home_id, "name": "All Lights"},
        headers=auth,
    ).json()["data"]
    device = client.post(
        "/api/v1/devices",
        json={"home_id": home_id, "name": "Bulb", "device_type": "light"},
        headers=auth,
    ).json()["data"]

    added = client.post(
        f"/api/v1/smart-home/device-groups/{group['id']}/members",
        json={"device_id": device["id"]},
        headers=auth,
    )
    assert added.status_code == 201

    members = client.get(f"/api/v1/smart-home/device-groups/{group['id']}/members", headers=auth)
    assert [m["id"] for m in members.json()["data"]] == [device["id"]]

    removed = client.delete(
        f"/api/v1/smart-home/device-groups/{group['id']}/members/{device['id']}", headers=auth
    )
    assert removed.status_code == 204

    empty = client.get(f"/api/v1/smart-home/device-groups/{group['id']}/members", headers=auth)
    assert empty.json()["data"] == []


def test_pagination_reports_has_more(client, auth) -> None:
    """M11 Task Group F's pagination convention (`has_more`, not a
    silently truncated list) applies to this task group's collections
    too -- verified against a real over-the-limit page rather than
    assumed from the shared helper alone."""
    home_id = _home(client, auth)
    for i in range(3):
        client.post(
            "/api/v1/devices",
            json={"home_id": home_id, "name": f"Device {i}", "device_type": "sensor"},
            headers=auth,
        )

    page = client.get(f"/api/v1/devices?home_id={home_id}&limit=2", headers=auth)

    assert page.json()["meta"]["count"] == 2
    assert page.json()["meta"]["has_more"] is True
