"""Event Viewer REST tests -- Milestone 12 Developer Tools (Event
Viewer Slice).

Against the real FastAPI app and real DI container, matching every
other M12 devtools route test's pattern. `DeviceEventLog` is started
via the container directly (mirroring how `test_devtools_route.py`
starts `DebugConsole` directly) -- the app's own startup hook only
attaches it when `settings.devtools.device_event_log_enabled` is true
and the runtime lifecycle actually runs, which this bare `TestClient`
fixture does not drive.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest


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


def _send_command(client, auth, device_id: str, command: str, payload: dict | None = None):
    return client.post(
        f"/api/v1/connectivity/devices/{device_id}/command",
        json={"command": command, "payload": payload or {}},
        headers=auth,
    )


def _events(client, auth, **params):
    return client.get("/api/v1/devtools/events", params=params, headers=auth)


# --- Auth ------------------------------------------------------------------------


def test_route_requires_a_session(client) -> None:
    assert client.get("/api/v1/devtools/events").status_code == 401


def test_no_permission_grant_needed_to_reach_the_route(client, auth) -> None:
    assert _events(client, auth).status_code == 200


# --- Not started / empty ------------------------------------------------------------


def test_never_started_reports_not_running_and_empty(client, auth) -> None:
    response = _events(client, auth)
    assert response.status_code == 200
    assert response.json()["data"] == []
    assert response.json()["meta"] == {"count": 0, "running": False}


def test_started_with_no_commands_yet(client, auth) -> None:
    client.container.device_event_log().start()

    response = _events(client, auth)

    assert response.json()["data"] == []
    assert response.json()["meta"] == {"count": 0, "running": True}


# --- Real command activity ----------------------------------------------------------


def test_a_sent_command_is_surfaced(client, auth, fake_connector) -> None:
    from jarvis.core.interfaces.connectivity import DiscoveredDevice

    client.container.device_event_log().start()
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

    response = _send_command(client, auth, device_id, "lock", {"code": "1234"})
    assert response.status_code == 200

    body = _events(client, auth).json()
    assert body["meta"]["count"] == 1
    [event] = body["data"]
    assert event["device_id"] == device_id
    assert event["command"] == "lock"
    assert event["success"] is True
    assert set(event) == {"at", "device_id", "command", "success", "detail"}


def test_command_payload_never_appears_in_the_response(client, auth, fake_connector) -> None:
    from jarvis.core.interfaces.connectivity import DiscoveredDevice

    client.container.device_event_log().start()
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

    _send_command(client, auth, device_id, "lock", {"code": "sh-secret-pin"})

    response = _events(client, auth)
    assert "sh-secret-pin" not in response.text


def test_device_id_filter_excludes_other_devices(client, auth, fake_connector) -> None:
    from jarvis.core.interfaces.connectivity import DiscoveredDevice

    client.container.device_event_log().start()
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

    _send_command(client, auth, device_a, "lock", {})
    _send_command(client, auth, device_b, "unlock", {})

    body = _events(client, auth, device_id=device_a).json()
    assert body["meta"]["count"] == 1
    assert body["data"][0]["device_id"] == device_a


def test_unknown_device_id_filter_is_not_an_error(client, auth) -> None:
    client.container.device_event_log().start()

    response = _events(client, auth, device_id="no-such-device")

    assert response.status_code == 200
    assert response.json()["data"] == []


# --- Clear -------------------------------------------------------------------------


def test_clear_events(client, auth, fake_connector) -> None:
    from jarvis.core.interfaces.connectivity import DiscoveredDevice

    client.container.device_event_log().start()
    home_id = _home(client, auth)
    _connect(client, auth)
    discovered = _discover(
        client,
        auth,
        fake_connector,
        home_id,
        [DiscoveredDevice(external_id="lock.x", name="X", device_type="lock")],
    )
    _send_command(client, auth, discovered[0]["id"], "lock", {})

    response = client.delete("/api/v1/devtools/events", headers=auth)
    assert response.status_code == 200
    assert response.json()["data"]["cleared"] is True
    assert _events(client, auth).json()["data"] == []


# --- REST ------------------------------------------------------------------------


def test_response_uses_the_documented_envelope(client, auth) -> None:
    assert set(_events(client, auth).json()) == {"data", "meta"}


# --- Architecture guards --------------------------------------------------------------


def test_event_not_added_to_the_relay() -> None:
    """Deliberately not relayed over WebSocket -- backend-only,
    matching every M12 Developer Tools slice's own scope (Logic
    Contract §3/§10)."""
    from jarvis.core.events.events import DeviceCommandExecutedEvent
    from jarvis.core.lifecycle.runtime_ws_hub import EVENT_TYPE_NAMES, UNPUBLISHED_EVENT_TYPES

    assert DeviceCommandExecutedEvent not in EVENT_TYPE_NAMES
    assert "DeviceCommandExecutedEvent" in UNPUBLISHED_EVENT_TYPES


def test_no_eventbus_scheduler_analytics_memory_reference_in_the_route() -> None:
    import inspect

    from jarvis.infrastructure.api.routes import devtools as devtools_module

    source = inspect.getsource(devtools_module)
    for forbidden in ("Scheduler", "Analytics", "MemoryService"):
        assert forbidden not in source


def test_no_agent_tool_for_event_viewer() -> None:
    from jarvis.agents.tools.registry import build_tool_registry

    tools = build_tool_registry()
    names = {t.name for t in tools}
    assert "get_device_events" not in names
    assert "device_events" not in names
