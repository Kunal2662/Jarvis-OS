"""Device Simulator REST tests -- Milestone 12 Developer Tools (Device
Simulator Slice).

Against the real FastAPI app and the real DI container, with
`settings.devtools.simulator_enabled=True` so the container's own
Option C factory-swap is exercised end-to-end. No permission grant is
involved anywhere in this file -- these routes have no
`PermissionModel` gate, by deliberate design (Logic Contract §9),
matching every other devtools route.
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
    settings = Settings(data_dir=str(tmp_path / "data"), devtools={"simulator_enabled": True})
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


def _define(client, auth, **overrides) -> dict:
    body = {"device_type": "light", **overrides}
    response = client.post("/api/v1/devtools/simulator/devices", json=body, headers=auth)
    assert response.status_code == 200
    return response.json()["data"]


# --- Auth ------------------------------------------------------------------------


def test_routes_require_a_session(client) -> None:
    assert (
        client.post("/api/v1/devtools/simulator/devices", json={"device_type": "light"}).status_code
        == 401
    )
    assert client.get("/api/v1/devtools/simulator/devices").status_code == 401
    assert client.delete("/api/v1/devtools/simulator/devices/x").status_code == 401
    assert client.post("/api/v1/devtools/simulator/devices/x/fault", json={}).status_code == 401
    assert client.post("/api/v1/devtools/simulator/reset").status_code == 401


def test_no_permission_grant_needed(client, auth) -> None:
    """No `PermissionModel` gate -- a bare authenticated session is
    sufficient, matching every other devtools capability (Logic
    Contract §9)."""
    response = client.get("/api/v1/devtools/simulator/devices", headers=auth)
    assert response.status_code == 200


# --- Define / list -----------------------------------------------------------------


def test_define_and_list_device(client, auth) -> None:
    device = _define(client, auth, device_type="light", external_id="light.x")
    assert device["device_type"] == "light"
    assert device["status"] == "off"

    listed = client.get("/api/v1/devtools/simulator/devices", headers=auth)
    assert listed.status_code == 200
    assert listed.json()["meta"]["count"] == 1
    assert listed.json()["data"][0]["external_id"] == "light.x"


def test_define_invalid_device_type_is_400(client, auth) -> None:
    response = client.post(
        "/api/v1/devtools/simulator/devices", json={"device_type": "camera"}, headers=auth
    )
    assert response.status_code == 400


def test_define_generates_external_id_when_omitted(client, auth) -> None:
    device = _define(client, auth, device_type="switch")
    assert device["external_id"].startswith("simulator.switch.")


# --- Delete --------------------------------------------------------------------------


def test_delete_device(client, auth) -> None:
    _define(client, auth, device_type="lock", external_id="lock.x")

    response = client.delete("/api/v1/devtools/simulator/devices/lock.x", headers=auth)

    assert response.status_code == 200
    assert response.json()["data"]["deleted"] is True
    assert (
        client.get("/api/v1/devtools/simulator/devices", headers=auth).json()["meta"]["count"] == 0
    )


def test_delete_unknown_device_reports_false_not_error(client, auth) -> None:
    response = client.delete("/api/v1/devtools/simulator/devices/no-such-device", headers=auth)
    assert response.status_code == 200
    assert response.json()["data"]["deleted"] is False


# --- Fault -----------------------------------------------------------------------------


def test_set_fault_unavailable(client, auth) -> None:
    _define(client, auth, device_type="switch", external_id="switch.x")

    response = client.post(
        "/api/v1/devtools/simulator/devices/switch.x/fault",
        json={"unavailable": True},
        headers=auth,
    )

    assert response.status_code == 200
    assert response.json()["data"]["unavailable"] is True


def test_set_fault_unknown_device_is_404(client, auth) -> None:
    response = client.post(
        "/api/v1/devtools/simulator/devices/no-such-device/fault",
        json={"unavailable": True},
        headers=auth,
    )
    assert response.status_code == 404


# --- Reset -----------------------------------------------------------------------------


def test_reset_clears_roster(client, auth) -> None:
    _define(client, auth, device_type="light", external_id="light.a")
    _define(client, auth, device_type="switch", external_id="switch.b")

    response = client.post("/api/v1/devtools/simulator/reset", headers=auth)

    assert response.status_code == 200
    assert response.json()["data"]["cleared"] == 2
    assert (
        client.get("/api/v1/devtools/simulator/devices", headers=auth).json()["meta"]["count"] == 0
    )


# --- Generic Connectivity integration through REST, no duplicate simulator API --------


def test_generic_discovery_and_command_reach_the_simulator(client, auth) -> None:
    """No `/devtools/simulator/discover`, `/import`, `/state/{id}`, or
    `/command/{id}` exists -- the existing, unmodified generic
    Connectivity Layer routes are the only path (Logic Contract §10)."""
    _define(client, auth, device_type="light", external_id="light.x")
    home = client.post("/api/v1/homes", json={"name": "Primary Residence"}, headers=auth).json()[
        "data"
    ]

    connect = client.post(
        "/api/v1/connectivity/connectors/home_assistant/connect", json={"config": {}}, headers=auth
    )
    assert connect.status_code == 200

    discovered = client.post(
        "/api/v1/connectivity/discover",
        json={"connector_type": "home_assistant", "home_id": home["id"]},
        headers=auth,
    )
    assert discovered.status_code == 200
    devices = discovered.json()["data"]
    assert len(devices) == 1
    device_id = devices[0]["id"]

    command = client.post(
        f"/api/v1/connectivity/devices/{device_id}/command",
        json={"command": "turn_on", "payload": {}},
        headers=auth,
    )
    assert command.status_code == 200
    assert command.json()["data"]["success"] is True


def test_no_simulator_specific_discover_import_state_command_routes(client, auth) -> None:
    for path in (
        "/api/v1/devtools/simulator/discover",
        "/api/v1/devtools/simulator/import",
        "/api/v1/devtools/simulator/state/x",
        "/api/v1/devtools/simulator/command/x",
    ):
        assert client.get(path, headers=auth).status_code == 404
        assert client.post(path, headers=auth).status_code == 404


# --- Envelope shape --------------------------------------------------------------------


def test_response_envelope_shape(client, auth) -> None:
    response = client.get("/api/v1/devtools/simulator/devices", headers=auth)
    assert set(response.json()) == {"data", "meta"}
