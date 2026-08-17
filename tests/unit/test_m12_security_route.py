"""Security & Safety REST tests -- Milestone 12 Security & Safety
(Read-Only Alert/Status Slice + Manual/On-Demand Action Slice).

Against the real FastAPI app and the real DI container, matching
``test_m12_sensors_route.py``'s pattern. Permission is granted through
the existing generic plugin-permissions route, never ``PermissionModel``
directly.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from jarvis.services.security_service import SECURITY_PRINCIPAL, SMART_HOME_SCOPE
from jarvis.services.sensor_service import SENSOR_PRINCIPAL


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


def _grant(client, auth, principal: str) -> None:
    response = client.post(
        f"/api/v1/plugins/{principal}/permissions/{SMART_HOME_SCOPE}/grant", headers=auth
    )
    assert response.status_code == 200


def _grant_security(client, auth) -> None:
    _grant(client, auth, SECURITY_PRINCIPAL)


def _grant_sensors(client, auth) -> None:
    _grant(client, auth, SENSOR_PRINCIPAL)


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


def _hazard_sensor(external_id: str, device_class: str):
    from jarvis.core.interfaces.connectivity import DiscoveredDevice

    return DiscoveredDevice(
        external_id=external_id,
        name=f"{device_class.title()} Sensor",
        device_type="sensor",
        metadata={"domain": "binary_sensor", "device_class": device_class},
    )


def _lock(external_id: str):
    from jarvis.core.interfaces.connectivity import DiscoveredDevice

    return DiscoveredDevice(external_id=external_id, name="Front Door", device_type="lock")


def _light(external_id: str):
    from jarvis.core.interfaces.connectivity import DiscoveredDevice

    return DiscoveredDevice(external_id=external_id, name="Living Room Light", device_type="light")


def _grant_smart_lock(client, auth) -> None:
    from jarvis.services.smart_lock_service import SMART_LOCK_PRINCIPAL

    _grant(client, auth, SMART_LOCK_PRINCIPAL)


def _grant_smart_lighting(client, auth) -> None:
    from jarvis.services.smart_lighting_service import SMART_LIGHTING_PRINCIPAL

    _grant(client, auth, SMART_LIGHTING_PRINCIPAL)


# --- Auth --------------------------------------------------------------------------


def test_route_requires_a_session(client) -> None:
    assert client.get("/api/v1/security/status").status_code in (401, 403)


# --- Permission gates ----------------------------------------------------------------


def test_denied_without_core_security_grant_is_400(client, auth) -> None:
    response = client.get("/api/v1/security/status", headers=auth)
    assert response.status_code == 400
    assert "permission" in response.json()["detail"].lower()


def test_core_security_granted_but_core_sensors_not_is_400(client, auth, fake_connector) -> None:
    """The genuinely new case this module introduces: two independent
    permission gates compose -- granting core:security alone is not
    enough when a hazard sensor exists (Logic Contract §3)."""
    home_id = _home(client, auth)
    _connect(client, auth)
    _discover(
        client, auth, fake_connector, home_id, [_hazard_sensor("binary_sensor.smoke_1", "smoke")]
    )
    _grant_security(client, auth)

    response = client.get("/api/v1/security/status", headers=auth)

    assert response.status_code == 400
    assert "permission" in response.json()["detail"].lower()


def test_both_grants_succeed(client, auth) -> None:
    _grant_security(client, auth)
    _grant_sensors(client, auth)

    response = client.get("/api/v1/security/status", headers=auth)

    assert response.status_code == 200


# --- Successful aggregation ------------------------------------------------------


def test_empty_home_returns_unknown(client, auth) -> None:
    _home(client, auth)
    _grant_security(client, auth)
    _grant_sensors(client, auth)

    response = client.get("/api/v1/security/status", headers=auth)

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["overall_status"] == "UNKNOWN"
    assert body["meta"]["overall_status"] == "UNKNOWN"


def test_mixed_alerts_returns_critical_with_active_alert(client, auth, fake_connector) -> None:
    from jarvis.core.interfaces.connectivity import DeviceState

    home_id = _home(client, auth)
    _connect(client, auth)
    _discover(
        client,
        auth,
        fake_connector,
        home_id,
        [_hazard_sensor("binary_sensor.smoke_1", "smoke"), _lock("lock.front_door")],
    )
    fake_connector.states["binary_sensor.smoke_1"] = DeviceState(
        external_id="binary_sensor.smoke_1", status="on", attributes={}
    )
    fake_connector.states["lock.front_door"] = DeviceState(
        external_id="lock.front_door", status="locked", attributes={}
    )
    _grant_security(client, auth)
    _grant_sensors(client, auth)

    response = client.get("/api/v1/security/status", headers=auth)

    body = response.json()
    assert body["data"]["overall_status"] == "CRITICAL"
    assert len(body["data"]["active_alerts"]) == 1
    assert body["data"]["active_alerts"][0]["device_class"] == "smoke"
    assert body["data"]["locks"][0]["locked"] is True


def test_unavailable_hazard_sensor_returns_warning(client, auth, fake_connector) -> None:
    from jarvis.core.interfaces.connectivity import DeviceState

    home_id = _home(client, auth)
    _connect(client, auth)
    _discover(client, auth, fake_connector, home_id, [_hazard_sensor("binary_sensor.gas_1", "gas")])
    # Connector-reported "unavailable" -- a real, connector-sourced
    # down signal, absorbed into available=False by SensorService.
    fake_connector.states["binary_sensor.gas_1"] = DeviceState(
        external_id="binary_sensor.gas_1", status="unavailable", attributes={}
    )
    _grant_security(client, auth)
    _grant_sensors(client, auth)

    response = client.get("/api/v1/security/status", headers=auth)

    assert response.json()["data"]["overall_status"] == "WARNING"


def test_response_uses_the_documented_envelope(client, auth) -> None:
    _home(client, auth)
    _grant_security(client, auth)
    _grant_sensors(client, auth)

    response = client.get("/api/v1/security/status", headers=auth)

    assert set(response.json()) == {"data", "meta"}
    assert "overall_status" in response.json()["meta"]


def test_home_id_and_room_id_query_params_accepted(client, auth) -> None:
    home_id = _home(client, auth)
    _grant_security(client, auth)
    _grant_sensors(client, auth)

    response = client.get("/api/v1/security/status", params={"home_id": home_id}, headers=auth)

    assert response.status_code == 200
    assert response.json()["data"]["home_id"] == home_id


# --- No mutation surface, no 404-shaped id route ------------------------------------


def test_no_mutation_route_exists(client, auth) -> None:
    _grant_security(client, auth)
    _grant_sensors(client, auth)
    for method, path in (
        ("post", "/api/v1/security/status"),
        ("put", "/api/v1/security/status"),
        ("delete", "/api/v1/security/status"),
    ):
        assert getattr(client, method)(path, headers=auth).status_code in (404, 405)


def test_no_single_resource_id_route_exists(client, auth) -> None:
    _grant_security(client, auth)
    _grant_sensors(client, auth)
    response = client.get("/api/v1/security/status/no-such-id", headers=auth)
    assert response.status_code == 404


# =====================================================================
# Manual/On-Demand Action Slice (Task Group M)
# =====================================================================


def test_action_routes_require_a_session(client) -> None:
    for path in ("/api/v1/security/panic-mode", "/api/v1/security/vacation-mode"):
        assert client.post(path, json={"home_id": "x"}).status_code in (401, 403)


def test_panic_mode_denied_without_grant_is_400(client, auth) -> None:
    home_id = _home(client, auth)

    response = client.post("/api/v1/security/panic-mode", json={"home_id": home_id}, headers=auth)

    assert response.status_code == 400
    assert "permission" in response.json()["detail"].lower()


def test_vacation_mode_denied_without_grant_is_400(client, auth) -> None:
    home_id = _home(client, auth)

    response = client.post(
        "/api/v1/security/vacation-mode", json={"home_id": home_id}, headers=auth
    )

    assert response.status_code == 400
    assert "permission" in response.json()["detail"].lower()


def test_panic_mode_unknown_home_is_404(client, auth) -> None:
    _grant_security(client, auth)

    response = client.post(
        "/api/v1/security/panic-mode", json={"home_id": "no-such-home"}, headers=auth
    )

    assert response.status_code == 404


def test_vacation_mode_unknown_home_is_404(client, auth) -> None:
    _grant_security(client, auth)

    response = client.post(
        "/api/v1/security/vacation-mode", json={"home_id": "no-such-home"}, headers=auth
    )

    assert response.status_code == 404


def test_panic_mode_missing_home_id_is_422(client, auth) -> None:
    _grant_security(client, auth)

    response = client.post("/api/v1/security/panic-mode", json={}, headers=auth)

    assert response.status_code == 422


def test_panic_mode_empty_home_is_200_no_targets(client, auth) -> None:
    home_id = _home(client, auth)
    _grant_security(client, auth)

    response = client.post("/api/v1/security/panic-mode", json={"home_id": home_id}, headers=auth)

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "NO_TARGETS"
    assert response.json()["meta"]["status"] == "NO_TARGETS"


def test_panic_mode_success(client, auth, fake_connector) -> None:
    from jarvis.core.interfaces.connectivity import DeviceState

    home_id = _home(client, auth)
    _connect(client, auth)
    discovered = _discover(
        client,
        auth,
        fake_connector,
        home_id,
        [_lock("lock.front_door"), _light("light.living_room")],
    )
    fake_connector.states["lock.front_door"] = DeviceState(
        external_id="lock.front_door", status="unlocked", attributes={}
    )
    fake_connector.states["light.living_room"] = DeviceState(
        external_id="light.living_room", status="off", attributes={}
    )
    _grant_security(client, auth)
    _grant_smart_lock(client, auth)
    _grant_smart_lighting(client, auth)

    response = client.post("/api/v1/security/panic-mode", json={"home_id": home_id}, headers=auth)

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["status"] == "SUCCESS"
    assert body["requested_count"] == 2
    assert body["succeeded_count"] == 2
    device_ids = [discovered[0]["id"], discovered[1]["id"]]
    assert {row["device_id"] for row in body["locks"] + body["lights"]} == set(device_ids)


def test_panic_mode_partial_success_is_still_200(client, auth, fake_connector) -> None:
    from jarvis.core.interfaces.connectivity import DeviceState

    home_id = _home(client, auth)
    _connect(client, auth)
    _discover(
        client,
        auth,
        fake_connector,
        home_id,
        [_lock("lock.front_door"), _light("light.living_room")],
    )
    fake_connector.states["lock.front_door"] = DeviceState(
        external_id="lock.front_door", status="unlocked", attributes={}
    )
    fake_connector.states["light.living_room"] = DeviceState(
        external_id="light.living_room", status="off", attributes={}
    )
    _grant_security(client, auth)
    _grant_smart_lock(client, auth)
    # core:smart_lighting deliberately not granted.

    response = client.post("/api/v1/security/panic-mode", json={"home_id": home_id}, headers=auth)

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["status"] == "PARTIAL_SUCCESS"
    assert response.json()["meta"]["status"] == "PARTIAL_SUCCESS"
    assert body["locks"][0]["success"] is True
    assert body["lights"][0]["success"] is False


def test_panic_mode_total_failure_is_still_200(client, auth, fake_connector) -> None:
    from jarvis.core.interfaces.connectivity import DeviceState

    home_id = _home(client, auth)
    _connect(client, auth)
    _discover(client, auth, fake_connector, home_id, [_lock("lock.front_door")])
    fake_connector.states["lock.front_door"] = DeviceState(
        external_id="lock.front_door", status="unlocked", attributes={}
    )
    _grant_security(client, auth)
    # core:smart_locks deliberately not granted.

    response = client.post("/api/v1/security/panic-mode", json={"home_id": home_id}, headers=auth)

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "FAILED"


def test_vacation_mode_success(client, auth, fake_connector) -> None:
    from jarvis.core.interfaces.connectivity import DeviceState

    home_id = _home(client, auth)
    _connect(client, auth)
    _discover(client, auth, fake_connector, home_id, [_lock("lock.front_door")])
    fake_connector.states["lock.front_door"] = DeviceState(
        external_id="lock.front_door", status="locked", attributes={}
    )
    _grant_security(client, auth)
    _grant_smart_lock(client, auth)

    response = client.post(
        "/api/v1/security/vacation-mode", json={"home_id": home_id}, headers=auth
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["mode"] == "vacation"
    assert body["status"] == "SUCCESS"
    assert body["thermostats"] == []


def test_response_envelope_shape_for_action_routes(client, auth) -> None:
    home_id = _home(client, auth)
    _grant_security(client, auth)

    response = client.post("/api/v1/security/panic-mode", json={"home_id": home_id}, headers=auth)

    assert set(response.json()) == {"data", "meta"}
    assert "status" in response.json()["meta"]


def test_no_extra_security_action_routes_exist(client, auth) -> None:
    home_id = _home(client, auth)
    _grant_security(client, auth)
    for path in (
        "/api/v1/security/lockdown",
        "/api/v1/security/panic-mode/schedule",
        "/api/v1/security/emergency-alert",
    ):
        assert client.post(path, json={"home_id": home_id}, headers=auth).status_code in (
            404,
            405,
        )
