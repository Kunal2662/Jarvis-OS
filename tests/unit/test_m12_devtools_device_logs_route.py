"""Device Logs REST tests -- Milestone 12 Developer Tools (Device Logs
Slice).

Same real FastAPI app + real DI container pattern as
``test_m12_device_diagnostics_route.py``. The Debug Console sink must
be explicitly started for a test to observe anything -- it is off by
default in every environment (Device Diagnostics' own precedent), so
each test that expects captured entries starts/stops it around the
command it sends, matching ``test_devtools_route.py``'s own pattern.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest


def _wait_for(predicate, *, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("Condition not met within timeout.")


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


def _bare_device(client, auth, home_id: str, device_type: str, name: str = "X") -> dict:
    response = client.post(
        "/api/v1/devices",
        json={"home_id": home_id, "name": name, "device_type": device_type},
        headers=auth,
    )
    assert response.status_code == 201
    return response.json()["data"]


def _logs(client, auth, device_id: str, **params):
    return client.get(f"/api/v1/devtools/devices/{device_id}/logs", params=params, headers=auth)


def _send_command(client, auth, device_id: str, command: str, payload: dict | None = None):
    return client.post(
        f"/api/v1/connectivity/devices/{device_id}/command",
        json={"command": command, "payload": payload or {}},
        headers=auth,
    )


# --- Auth ------------------------------------------------------------------------


def test_route_requires_a_session(client) -> None:
    assert client.get("/api/v1/devtools/devices/x/logs").status_code == 401


def test_no_permission_grant_needed_to_reach_the_route(client, auth) -> None:
    home_id = _home(client, auth)
    device = _bare_device(client, auth, home_id, "light")
    response = _logs(client, auth, device["id"])
    assert response.status_code == 200


# --- REST ------------------------------------------------------------------------


def test_unknown_device_is_404(client, auth) -> None:
    assert _logs(client, auth, "no-such-device").status_code == 404


def test_device_with_no_commands_sent_returns_an_empty_list(client, auth) -> None:
    home_id = _home(client, auth)
    device = _bare_device(client, auth, home_id, "light")

    response = _logs(client, auth, device["id"])

    assert response.status_code == 200
    assert response.json()["data"] == []
    assert response.json()["meta"] == {"device_id": device["id"], "count": 0}


def test_response_uses_the_documented_envelope(client, auth) -> None:
    home_id = _home(client, auth)
    device = _bare_device(client, auth, home_id, "light")

    response = _logs(client, auth, device["id"])

    assert set(response.json()) == {"data", "meta"}


def test_no_mutation_endpoints_exist(client, auth) -> None:
    home_id = _home(client, auth)
    device = _bare_device(client, auth, home_id, "light")
    path = f"/api/v1/devtools/devices/{device['id']}/logs"

    for method in ("post", "put", "delete", "patch"):
        assert getattr(client, method)(path, headers=auth).status_code in (404, 405)


# --- Real command activity ---------------------------------------------------------


def test_a_sent_command_is_surfaced_in_the_devices_own_logs(client, auth, fake_connector) -> None:
    from jarvis.core.interfaces.connectivity import DiscoveredDevice

    home_id = _home(client, auth)
    _connect(client, auth)
    discovered = _discover(
        client,
        auth,
        fake_connector,
        home_id,
        [DiscoveredDevice(external_id="lock.x", name="Front Door", device_type="lock")],
    )
    device_id = discovered[0]["id"]

    console = client.container.debug_console()
    console.start(level="DEBUG")
    try:
        response = _send_command(client, auth, device_id, "lock", {"code": "1234"})
        assert response.status_code == 200
        _wait_for(lambda: len(console) >= 1)
    finally:
        console.stop()

    logs = _logs(client, auth, device_id).json()["data"]
    assert len(logs) == 1
    assert "lock" in logs[0]["message"]
    assert logs[0]["level"] == "INFO"


def test_command_payload_never_appears_in_the_devices_own_logs(
    client, auth, fake_connector
) -> None:
    from jarvis.core.interfaces.connectivity import DiscoveredDevice

    home_id = _home(client, auth)
    _connect(client, auth)
    discovered = _discover(
        client,
        auth,
        fake_connector,
        home_id,
        [DiscoveredDevice(external_id="lock.x", name="Front Door", device_type="lock")],
    )
    device_id = discovered[0]["id"]

    console = client.container.debug_console()
    console.start(level="DEBUG")
    try:
        _send_command(client, auth, device_id, "lock", {"code": "sh-secret-pin"})
        _wait_for(lambda: len(console) >= 1)
    finally:
        console.stop()

    response = _logs(client, auth, device_id)
    assert "sh-secret-pin" not in response.text


def test_a_different_devices_commands_are_excluded(client, auth, fake_connector) -> None:
    from jarvis.core.interfaces.connectivity import DiscoveredDevice

    home_id = _home(client, auth)
    _connect(client, auth)
    discovered = _discover(
        client,
        auth,
        fake_connector,
        home_id,
        [
            DiscoveredDevice(external_id="lock.a", name="A", device_type="lock"),
            DiscoveredDevice(external_id="lock.b", name="B", device_type="lock"),
        ],
    )
    device_a, device_b = discovered[0]["id"], discovered[1]["id"]

    console = client.container.debug_console()
    console.start(level="DEBUG")
    try:
        _send_command(client, auth, device_a, "lock", {})
        _send_command(client, auth, device_b, "unlock", {})
        _wait_for(lambda: len(console) >= 2)
    finally:
        console.stop()

    logs_a = _logs(client, auth, device_a).json()["data"]
    assert len(logs_a) == 1
    assert device_b not in logs_a[0]["message"]


# --- Architecture guards --------------------------------------------------------------


def _devtools_route_code() -> str:
    import inspect

    from jarvis.infrastructure.api.routes import devtools as devtools_module

    return inspect.getsource(devtools_module)


def test_no_eventbus_scheduler_analytics_memory_reference() -> None:
    source = _devtools_route_code()
    for forbidden in ("EventBus", "event_bus", "Scheduler", "Analytics", "MemoryService"):
        assert forbidden not in source


def test_no_agent_tool_for_device_logs() -> None:
    from jarvis.agents.tools.registry import build_tool_registry

    tools = build_tool_registry()
    names = {t.name for t in tools}
    assert "get_device_logs" not in names
    assert "device_logs" not in names
