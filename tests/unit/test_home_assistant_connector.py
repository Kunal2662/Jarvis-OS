"""HomeAssistantConnector tests against a **real** local HTTP server --
Milestone 12 Task Group B, Phase 2.

Mirrors ``test_mcp_transports_live.py``'s own ``http_server`` fixture
pattern: a real ``http.server.HTTPServer`` standing in for Home
Assistant's REST API, not a mocked ``httpx`` client. The connector's
entire job is HTTP framing, auth headers and entity mapping -- a
stubbed transport would exercise none of that.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

import pytest

from jarvis.core.connectivity.connectors.home_assistant import HomeAssistantConnector
from jarvis.core.interfaces.connectivity import ConnectivityError, ConnectorNotConnectedError

_TOKEN = "test-long-lived-token"

#: One entity per mapped domain, plus a non-device domain
#: (``automation``) and one deliberately malformed record (no ``.`` in
#: its id) -- both must be silently skipped by ``discover()`` without
#: aborting the batch.
_ENTITIES = [
    {
        "entity_id": "light.kitchen",
        "state": "on",
        "attributes": {"friendly_name": "Kitchen Light"},
        "last_updated": "2026-08-07T10:00:00+00:00",
    },
    {
        "entity_id": "lock.front_door",
        "state": "locked",
        "attributes": {"friendly_name": "Front Door"},
        "last_updated": "2026-08-07T10:00:00+00:00",
    },
    {
        "entity_id": "sensor.living_room_temp",
        "state": "21.5",
        "attributes": {"friendly_name": "Living Room Temp", "unit_of_measurement": "C"},
        "last_updated": "2026-08-07T10:00:00+00:00",
    },
    {
        "entity_id": "automation.morning_routine",
        "state": "on",
        "attributes": {"friendly_name": "Morning Routine"},
    },
    {"entity_id": "malformed-no-domain", "state": "on"},
]


def _make_handler(calls: list[tuple[str, str, dict]]):
    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: object) -> None:  # silence the test log
            return

        def _authorized(self) -> bool:
            return self.headers.get("Authorization") == f"Bearer {_TOKEN}"

        def _write_json(self, status: int, payload: object) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if not self._authorized():
                self._write_json(401, {"message": "Unauthorized"})
                return
            path = urlparse(self.path).path
            if path == "/api/":
                self._write_json(200, {"message": "API running."})
            elif path == "/api/states":
                self._write_json(200, _ENTITIES)
            elif path.startswith("/api/states/"):
                entity_id = path.removeprefix("/api/states/")
                entity = next((e for e in _ENTITIES if e["entity_id"] == entity_id), None)
                if entity is None:
                    self._write_json(404, {"message": "Entity not found"})
                else:
                    self._write_json(200, entity)
            else:
                self._write_json(404, {"message": "not found"})

        def do_POST(self) -> None:
            if not self._authorized():
                self._write_json(401, {"message": "Unauthorized"})
                return
            path = urlparse(self.path).path
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
            if path.startswith("/api/services/"):
                domain, _, service = path.removeprefix("/api/services/").partition("/")
                calls.append((domain, service, body))
                if body.get("entity_id") == "lock.jammed":
                    self._write_json(400, {"message": "failed to lock"})
                    return
                self._write_json(200, [])
                return
            self._write_json(404, {"message": "not found"})

    return _Handler


@pytest.fixture
def calls() -> list[tuple[str, str, dict]]:
    return []


@pytest.fixture
def ha_server(calls: list[tuple[str, str, dict]]):
    server = HTTPServer(("127.0.0.1", 0), _make_handler(calls))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


# --- construction ---------------------------------------------------------------


def test_requires_a_base_url() -> None:
    with pytest.raises(ConnectivityError, match="base_url"):
        HomeAssistantConnector("", _TOKEN)


def test_requires_a_token() -> None:
    with pytest.raises(ConnectivityError, match="token"):
        HomeAssistantConnector("http://127.0.0.1:8123", "")


def test_connector_type_and_initial_state() -> None:
    connector = HomeAssistantConnector("http://127.0.0.1:8123", _TOKEN)
    assert connector.connector_type == "home_assistant"
    assert connector.is_connected is False


# --- connect / disconnect --------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_probes_and_succeeds(ha_server: str) -> None:
    connector = HomeAssistantConnector(ha_server, _TOKEN)
    try:
        await connector.connect()
        assert connector.is_connected is True
    finally:
        await connector.disconnect()


@pytest.mark.asyncio
async def test_connect_is_idempotent(ha_server: str) -> None:
    connector = HomeAssistantConnector(ha_server, _TOKEN)
    try:
        await connector.connect()
        await connector.connect()
        assert connector.is_connected is True
    finally:
        await connector.disconnect()


@pytest.mark.asyncio
async def test_connect_with_wrong_token_fails(ha_server: str) -> None:
    connector = HomeAssistantConnector(ha_server, "wrong-token")
    with pytest.raises(ConnectivityError, match="cannot reach"):
        await connector.connect()
    assert connector.is_connected is False


@pytest.mark.asyncio
async def test_connect_unreachable_host_fails() -> None:
    connector = HomeAssistantConnector("http://127.0.0.1:9", _TOKEN)
    with pytest.raises(ConnectivityError, match="cannot reach"):
        await connector.connect()
    assert connector.is_connected is False


@pytest.mark.asyncio
async def test_disconnect_is_idempotent(ha_server: str) -> None:
    connector = HomeAssistantConnector(ha_server, _TOKEN)
    await connector.connect()
    await connector.disconnect()
    await connector.disconnect()
    assert connector.is_connected is False


@pytest.mark.asyncio
async def test_disconnect_before_connect_is_safe() -> None:
    await HomeAssistantConnector("http://127.0.0.1:8123", _TOKEN).disconnect()


# --- discover ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_discover_requires_a_connection(ha_server: str) -> None:
    connector = HomeAssistantConnector(ha_server, _TOKEN)
    with pytest.raises(ConnectorNotConnectedError):
        await connector.discover()


@pytest.mark.asyncio
async def test_discover_maps_known_domains_and_skips_non_devices(ha_server: str) -> None:
    """``automation.morning_routine`` and the malformed record are both
    absent from the result -- one for not being a device domain, the
    other via the fault-isolation the Logic Contract requires -- yet
    neither prevents the three real devices from being discovered."""
    connector = HomeAssistantConnector(ha_server, _TOKEN)
    try:
        await connector.connect()
        devices = await connector.discover()
    finally:
        await connector.disconnect()

    by_id = {d.external_id: d for d in devices}
    assert set(by_id) == {"light.kitchen", "lock.front_door", "sensor.living_room_temp"}
    assert by_id["light.kitchen"].device_type == "light"
    assert by_id["light.kitchen"].name == "Kitchen Light"
    assert by_id["light.kitchen"].metadata == {"domain": "light"}
    assert by_id["lock.front_door"].device_type == "lock"
    assert by_id["sensor.living_room_temp"].device_type == "sensor"


@pytest.mark.asyncio
async def test_discovered_device_falls_back_to_entity_id_without_friendly_name(
    ha_server: str,
) -> None:
    connector = HomeAssistantConnector(ha_server, _TOKEN)
    try:
        await connector.connect()
        devices = await connector.discover()
    finally:
        await connector.disconnect()

    # sensor.living_room_temp has a friendly_name; assert the mapping
    # honors it rather than always falling back to the entity id.
    by_id = {d.external_id: d for d in devices}
    assert by_id["sensor.living_room_temp"].name == "Living Room Temp"


# --- read_state ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_state_returns_status_attributes_and_timestamp(ha_server: str) -> None:
    connector = HomeAssistantConnector(ha_server, _TOKEN)
    try:
        await connector.connect()
        state = await connector.read_state("light.kitchen")
    finally:
        await connector.disconnect()

    assert state.external_id == "light.kitchen"
    assert state.status == "on"
    assert state.attributes["friendly_name"] == "Kitchen Light"
    assert state.observed_at is not None


@pytest.mark.asyncio
async def test_read_state_unknown_entity_raises(ha_server: str) -> None:
    connector = HomeAssistantConnector(ha_server, _TOKEN)
    try:
        await connector.connect()
        with pytest.raises(ConnectivityError, match="unknown entity"):
            await connector.read_state("light.does_not_exist")
    finally:
        await connector.disconnect()


@pytest.mark.asyncio
async def test_read_state_requires_a_connection(ha_server: str) -> None:
    connector = HomeAssistantConnector(ha_server, _TOKEN)
    with pytest.raises(ConnectorNotConnectedError):
        await connector.read_state("light.kitchen")


# --- send_command ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_command_calls_the_matching_service(
    ha_server: str, calls: list[tuple[str, str, dict]]
) -> None:
    connector = HomeAssistantConnector(ha_server, _TOKEN)
    try:
        await connector.connect()
        result = await connector.send_command("light.kitchen", "turn_off", {})
    finally:
        await connector.disconnect()

    assert result.success is True
    assert result.external_id == "light.kitchen"
    assert result.command == "turn_off"
    assert calls == [("light", "turn_off", {"entity_id": "light.kitchen"})]


@pytest.mark.asyncio
async def test_send_command_forwards_extra_payload_fields(
    ha_server: str, calls: list[tuple[str, str, dict]]
) -> None:
    connector = HomeAssistantConnector(ha_server, _TOKEN)
    try:
        await connector.connect()
        await connector.send_command("light.kitchen", "turn_on", {"brightness": 128})
    finally:
        await connector.disconnect()

    assert calls == [("light", "turn_on", {"entity_id": "light.kitchen", "brightness": 128})]


@pytest.mark.asyncio
async def test_send_command_reports_a_device_rejection_without_raising(ha_server: str) -> None:
    connector = HomeAssistantConnector(ha_server, _TOKEN)
    try:
        await connector.connect()
        result = await connector.send_command("lock.jammed", "lock", {})
    finally:
        await connector.disconnect()

    assert result.success is False
    assert result.detail


@pytest.mark.asyncio
async def test_send_command_rejects_a_malformed_entity_id(ha_server: str) -> None:
    connector = HomeAssistantConnector(ha_server, _TOKEN)
    try:
        await connector.connect()
        with pytest.raises(ConnectivityError, match="not a valid"):
            await connector.send_command("not-an-entity-id", "toggle", {})
    finally:
        await connector.disconnect()


@pytest.mark.asyncio
async def test_send_command_requires_a_connection(ha_server: str) -> None:
    connector = HomeAssistantConnector(ha_server, _TOKEN)
    with pytest.raises(ConnectorNotConnectedError):
        await connector.send_command("light.kitchen", "turn_on", {})
