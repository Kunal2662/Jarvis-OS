"""MQTT Debug Console REST tests -- Milestone 12 Developer Tools (MQTT
Debug Console Slice).

Against the real FastAPI app, the real DI container's own default
connector registry (never overridden -- this exercises the actual
production `build_mqtt_connector` factory), and a real local MQTT
broker (`tests/fakes/fake_mqtt_broker.py`'s `FakeMqttBroker`), matching
`test_mqtt_connector.py`'s own established discipline: a genuine TCP
peer speaking real MQTT wire packets, never a mocked client.

**Connecting is done directly through `ConnectivityService.connect`,
not the `POST /connectivity/connectors/mqtt/connect` REST route.** The
`FakeMqttBroker` fixture's own asyncio server only makes progress while
*something* on its event loop is actively awaiting -- a synchronous
`TestClient.post()` call blocks the calling thread without yielding
back to that loop, starving the broker mid-handshake and hanging the
test. Calling `ConnectivityService.connect()` directly, awaited from
the same async test function that also awaits `broker.publish(...)`,
keeps both cooperating on one loop -- exactly how `test_mqtt_
connector.py` already drives the identical broker fixture. Once
connected, the actual capability under test (`GET /devtools/mqtt/
messages`) is read through the real, synchronous `TestClient` as usual
-- a plain buffer read needs no concurrent broker activity, so there is
nothing left to starve at that point.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import pytest


def _wait_for(predicate, *, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("Condition not met within timeout.")


async def _wait_for_async(predicate, *, timeout: float = 3.0, interval: float = 0.02) -> bool:
    elapsed = 0.0
    while elapsed < timeout:
        if predicate():
            return True
        await asyncio.sleep(interval)
        elapsed += interval
    return predicate()


async def _wait_for_subscription(broker, topic_filter: str, *, timeout: float = 3.0) -> bool:
    return await _wait_for_async(
        lambda: topic_filter in dict(broker.received_subscribes()), timeout=timeout
    )


@pytest.fixture
async def broker():
    from tests.fakes.fake_mqtt_broker import FakeMqttBroker

    b = FakeMqttBroker()
    await b.start()
    yield b
    await b.stop()


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


async def _connect_mqtt(client, broker) -> Any:
    """Connects the real `mqtt` connector directly through the shared
    `ConnectivityService` singleton the app's own routes also use --
    see the module docstring for why this bypasses the REST connect
    route. Returns the live connector instance."""
    service = client.container.connectivity_service()
    await service.connect(
        "mqtt",
        {
            "host": "127.0.0.1",
            "port": broker.port,
            "use_tls": False,
            "discovery_window_seconds": 0.1,
            "reconnect_delay_seconds": 0.05,
        },
    )
    return service.get_connector("mqtt")


async def _disconnect_mqtt(client) -> None:
    await client.container.connectivity_service().disconnect("mqtt")


def _messages(client, auth, **params):
    return client.get("/api/v1/devtools/mqtt/messages", params=params, headers=auth)


_NATIVE_DISCOVERY_TOPIC = "jarvis/discovery/announce"


# --- Auth ------------------------------------------------------------------------


def test_route_requires_a_session(client) -> None:
    assert client.get("/api/v1/devtools/mqtt/messages").status_code == 401


def test_no_permission_grant_needed_to_reach_the_route(client, auth) -> None:
    response = _messages(client, auth)
    assert response.status_code == 200


# --- No connector / not connected --------------------------------------------------


def test_no_connector_ever_created_reports_not_connected(client, auth) -> None:
    response = _messages(client, auth)

    assert response.status_code == 200
    body = response.json()
    assert body["data"] == []
    assert body["meta"] == {"connected": False, "count": 0}


@pytest.mark.asyncio
async def test_disconnected_after_having_connected_reports_not_connected(
    client, auth, broker
) -> None:
    await _connect_mqtt(client, broker)
    await _disconnect_mqtt(client)

    response = _messages(client, auth)

    assert response.json()["meta"]["connected"] is False
    assert response.json()["data"] == []


# --- Connected, real traffic ---------------------------------------------------------


@pytest.mark.asyncio
async def test_connected_with_no_messages_yet(client, auth, broker) -> None:
    await _connect_mqtt(client, broker)

    response = _messages(client, auth)

    assert response.status_code == 200
    assert response.json()["data"] == []
    assert response.json()["meta"] == {"connected": True, "count": 0}


@pytest.mark.asyncio
async def test_a_real_published_message_is_surfaced(client, auth, broker) -> None:
    await _connect_mqtt(client, broker)

    await broker.publish(
        "homeassistant/light/livingroom/kitchen_light/config",
        json.dumps({"name": "Kitchen Light", "unique_id": "kitchen_light_1"}).encode(),
        retain=True,
    )
    await _wait_for_async(lambda: _messages(client, auth).json()["meta"]["count"] >= 1)

    body = _messages(client, auth).json()
    assert body["meta"]["connected"] is True
    [message] = body["data"]
    assert message["topic"] == "homeassistant/light/livingroom/kitchen_light/config"
    assert "Kitchen Light" in message["payload"]
    assert set(message) == {"at", "topic", "payload", "qos"}


@pytest.mark.asyncio
async def test_limit_is_respected(client, auth, broker) -> None:
    await _connect_mqtt(client, broker)
    await _wait_for_subscription(broker, _NATIVE_DISCOVERY_TOPIC)

    for i in range(5):
        await broker.publish(_NATIVE_DISCOVERY_TOPIC, str(i).encode())
        await _wait_for_async(lambda i=i: _messages(client, auth).json()["meta"]["count"] >= i + 1)

    body = _messages(client, auth, limit=2).json()

    assert len(body["data"]) == 2
    assert body["meta"]["count"] == 2


@pytest.mark.asyncio
async def test_secrets_never_appear_in_the_response(client, auth, broker) -> None:
    await _connect_mqtt(client, broker)
    await _wait_for_subscription(broker, _NATIVE_DISCOVERY_TOPIC)

    await broker.publish(
        _NATIVE_DISCOVERY_TOPIC, json.dumps({"api_key": "sh-real-secret-value"}).encode()
    )
    await _wait_for_async(lambda: _messages(client, auth).json()["meta"]["count"] >= 1)

    response = _messages(client, auth)
    assert "sh-real-secret-value" not in response.text


# --- REST ------------------------------------------------------------------------


def test_response_uses_the_documented_envelope(client, auth) -> None:
    response = _messages(client, auth)
    assert set(response.json()) == {"data", "meta"}


def test_no_mutation_endpoints_exist(client, auth) -> None:
    for method in ("post", "put", "delete", "patch"):
        assert getattr(client, method)(
            "/api/v1/devtools/mqtt/messages", headers=auth
        ).status_code in (404, 405)


# --- Architecture guards --------------------------------------------------------------


def _devtools_route_code() -> str:
    import inspect

    from jarvis.infrastructure.api.routes import devtools as devtools_module

    return inspect.getsource(devtools_module)


def test_devtools_route_never_imports_a_concrete_connector() -> None:
    import inspect

    from jarvis.infrastructure.api.routes import devtools as devtools_module

    import_lines = "\n".join(
        line
        for line in inspect.getsource(devtools_module).splitlines()
        if line.strip().startswith(("import ", "from "))
    )
    assert "MqttConnector" not in import_lines
    assert "HomeAssistantConnector" not in import_lines
    assert "ConnectorCredentialStore" not in import_lines


def test_no_eventbus_scheduler_analytics_memory_reference() -> None:
    source = _devtools_route_code()
    for forbidden in ("EventBus", "event_bus", "Scheduler", "Analytics", "MemoryService"):
        assert forbidden not in source


def test_no_agent_tool_for_mqtt_debug_console() -> None:
    from jarvis.agents.tools.registry import build_tool_registry

    tools = build_tool_registry()
    names = {t.name for t in tools}
    assert "get_mqtt_debug_messages" not in names
    assert "mqtt_messages" not in names
