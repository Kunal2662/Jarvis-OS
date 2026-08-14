"""Smart Home Memory REST tests -- Milestone 12 Smart Home Memory
(Manual/On-Demand Device Snapshot Slice).

Against the real FastAPI app and the real DI container, matching
``test_m12_water_heaters_route.py``'s own pattern. Permission is
granted through the existing generic plugin-permissions route, never
``PermissionModel`` directly.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from jarvis.services.smart_home_memory_service import (
    SMART_HOME_MEMORY_PRINCIPAL,
    SMART_HOME_SCOPE,
)

_LIGHT_EXTERNAL_ID = "light.living_room"


@pytest.fixture
def fake_connector():
    from tests.fakes.fake_device_connector import FakeDeviceConnector

    return FakeDeviceConnector()


@pytest.fixture
def client(tmp_path: Path, fake_connector, monkeypatch):
    from fastapi.testclient import TestClient

    from jarvis.core.config.settings import Settings
    from jarvis.core.connectivity.registry import ConnectorFactoryRegistry
    from jarvis.core.di.container import Container
    from jarvis.infrastructure.api.fastapi_server import create_app

    monkeypatch.setenv("JARVIS_OPENAI_ENABLED", "false")
    monkeypatch.setenv("JARVIS_OLLAMA_ENABLED", "true")

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
        f"/api/v1/plugins/{SMART_HOME_MEMORY_PRINCIPAL}/permissions/{SMART_HOME_SCOPE}/grant",
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


def _light_device(external_id: str = _LIGHT_EXTERNAL_ID):
    from jarvis.core.interfaces.connectivity import DiscoveredDevice

    return DiscoveredDevice(external_id=external_id, name="Living Room Light", device_type="light")


def _register_light(client, auth, fake_connector) -> str:
    from jarvis.core.interfaces.connectivity import DeviceState

    home_id = _home(client, auth)
    _connect(client, auth)
    discovered = _discover(client, auth, fake_connector, home_id, [_light_device()])
    # A default seeded state so callers that don't care about specific
    # values (list/filter/limit tests) don't trip the fake connector's
    # own "no state seeded" KeyError -- callers that do care overwrite
    # this before creating a snapshot.
    fake_connector.states[_LIGHT_EXTERNAL_ID] = DeviceState(
        external_id=_LIGHT_EXTERNAL_ID, status="on", attributes={}
    )
    return discovered[0]["id"]


# --- Auth ------------------------------------------------------------------------


def test_routes_require_a_session(client) -> None:
    assert client.post(
        "/api/v1/smart-home/memory/snapshots", json={"device_id": "x"}
    ).status_code in (401, 403)
    assert client.get("/api/v1/smart-home/memory/snapshots").status_code in (401, 403)


# --- Create snapshot ---------------------------------------------------------------


def test_create_denied_without_grant_is_400(client, auth, fake_connector) -> None:
    device_id = _register_light(client, auth, fake_connector)

    response = client.post(
        "/api/v1/smart-home/memory/snapshots", json={"device_id": device_id}, headers=auth
    )

    assert response.status_code == 400
    assert "permission" in response.json()["detail"].lower()


def test_create_unknown_device_is_404(client, auth) -> None:
    _grant(client, auth)
    response = client.post(
        "/api/v1/smart-home/memory/snapshots", json={"device_id": "no-such-device"}, headers=auth
    )
    assert response.status_code == 404


def test_create_unsupported_category_is_400(client, auth) -> None:
    home_id = _home(client, auth)
    _grant(client, auth)
    sensor = client.post(
        "/api/v1/devices",
        json={"home_id": home_id, "name": "Motion Sensor", "device_type": "sensor"},
        headers=auth,
    ).json()["data"]

    response = client.post(
        "/api/v1/smart-home/memory/snapshots", json={"device_id": sensor["id"]}, headers=auth
    )

    assert response.status_code == 400
    assert "only supported for" in response.json()["detail"]


def test_create_success_after_grant(client, auth, fake_connector) -> None:
    from jarvis.core.interfaces.connectivity import DeviceState

    device_id = _register_light(client, auth, fake_connector)
    fake_connector.states[_LIGHT_EXTERNAL_ID] = DeviceState(
        external_id=_LIGHT_EXTERNAL_ID, status="on", attributes={"brightness": 60}
    )
    _grant(client, auth)

    response = client.post(
        "/api/v1/smart-home/memory/snapshots", json={"device_id": device_id}, headers=auth
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["device_id"] == device_id
    assert body["data"]["device_type"] == "light"
    assert body["data"]["memory_id"]
    assert body["meta"]["device_id"] == device_id


def test_create_unavailable_device_is_still_200(client, auth, fake_connector) -> None:
    """The connector reports the device as unavailable -- the snapshot
    must still be created, honestly capturing that state rather than
    erroring (Logic Contract §18)."""
    from jarvis.core.interfaces.connectivity import DeviceState

    device_id = _register_light(client, auth, fake_connector)
    fake_connector.states[_LIGHT_EXTERNAL_ID] = DeviceState(
        external_id=_LIGHT_EXTERNAL_ID, status="unavailable", attributes={}
    )
    _grant(client, auth)

    response = client.post(
        "/api/v1/smart-home/memory/snapshots", json={"device_id": device_id}, headers=auth
    )

    assert response.status_code == 200
    snapshot = client.get(
        "/api/v1/smart-home/memory/snapshots",
        params={"device_id": device_id},
        headers=auth,
    ).json()["data"][0]
    # A light's own normalized payload has no `available` field -- an
    # unrecognized/unavailable status string simply can't be parsed
    # into on/off, so `on` stays None (never fabricated).
    assert snapshot["state"]["on"] is None


def test_no_extra_endpoints(client, auth, fake_connector) -> None:
    device_id = _register_light(client, auth, fake_connector)
    _grant(client, auth)

    for method, path in (
        ("put", "/api/v1/smart-home/memory/snapshots"),
        ("delete", "/api/v1/smart-home/memory/snapshots"),
        ("get", f"/api/v1/smart-home/memory/snapshots/{device_id}"),
        ("post", f"/api/v1/smart-home/memory/snapshots/{device_id}"),
    ):
        assert getattr(client, method)(path, headers=auth).status_code in (404, 405)


# --- List snapshots -----------------------------------------------------------------


def test_list_denied_without_grant_is_400(client, auth) -> None:
    response = client.get("/api/v1/smart-home/memory/snapshots", headers=auth)
    assert response.status_code == 400


def test_list_empty_after_grant(client, auth) -> None:
    _grant(client, auth)
    response = client.get("/api/v1/smart-home/memory/snapshots", headers=auth)
    assert response.status_code == 200
    assert response.json()["data"] == []
    assert response.json()["meta"]["count"] == 0


def test_list_returns_created_snapshot(client, auth, fake_connector) -> None:
    device_id = _register_light(client, auth, fake_connector)
    _grant(client, auth)
    client.post("/api/v1/smart-home/memory/snapshots", json={"device_id": device_id}, headers=auth)

    response = client.get("/api/v1/smart-home/memory/snapshots", headers=auth)

    assert response.status_code == 200
    assert response.json()["meta"]["count"] == 1
    assert response.json()["data"][0]["device_id"] == device_id


def test_list_filters_by_device_id(client, auth, fake_connector) -> None:
    device_id = _register_light(client, auth, fake_connector)
    _grant(client, auth)
    client.post("/api/v1/smart-home/memory/snapshots", json={"device_id": device_id}, headers=auth)

    matching = client.get(
        "/api/v1/smart-home/memory/snapshots", params={"device_id": device_id}, headers=auth
    )
    assert matching.json()["meta"]["count"] == 1

    non_matching = client.get(
        "/api/v1/smart-home/memory/snapshots", params={"device_id": "other-device"}, headers=auth
    )
    assert non_matching.json()["meta"]["count"] == 0


def test_list_respects_limit(client, auth, fake_connector) -> None:
    device_id = _register_light(client, auth, fake_connector)
    _grant(client, auth)
    for _ in range(3):
        client.post(
            "/api/v1/smart-home/memory/snapshots", json={"device_id": device_id}, headers=auth
        )

    response = client.get("/api/v1/smart-home/memory/snapshots", params={"limit": 2}, headers=auth)

    assert response.json()["meta"]["count"] == 2


# --- Envelope shape ------------------------------------------------------------------


def test_response_uses_the_documented_envelope(client, auth) -> None:
    _grant(client, auth)
    listed = client.get("/api/v1/smart-home/memory/snapshots", headers=auth)
    assert set(listed.json()) == {"data", "meta"}
