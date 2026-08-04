"""End-to-end MCP transport test -- Milestone 10.5 Task Group B.

Drives the real client runtime, over a **real** transport, against a
**real** peer process, through the real DI container, with the real M9
``PermissionModel`` filtering capabilities -- and asserts the resulting
events reach a real WebSocket subscriber.

Uses stdio as the representative transport: it is the only one whose
peer is a genuine separate OS process, so it exercises the most of the
stack (subprocess lifecycle, stream framing, correlation, handshake,
negotiation, permission filtering, teardown) in one pass. The other
three transports' own wire behaviour is covered in
``tests/unit/test_mcp_transports_live.py`` against real servers.

**One event loop per test, deliberately.** A real subprocess' pipes are
bound to the loop that created them, so every transport interaction in
a given test runs inside a single :func:`asyncio.run` scenario rather
than one call per ``asyncio.run``. Where a scenario also needs the
synchronous ``TestClient``, it reaches it through
:func:`asyncio.to_thread` -- which keeps the loop single while still
exercising the real HTTP surface.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

_PEER_SCRIPT = str(Path(__file__).resolve().parents[1] / "fixtures" / "mcp_stdio_peer.py")


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
    container.runtime_ws_hub().start()

    with TestClient(app) as test_client:
        test_client.container = container  # type: ignore[attr-defined]
        yield test_client

    asyncio.run(database.dispose())


@pytest.fixture
def auth_headers(client):
    session = client.post("/api/v1/sessions", json={}).json()["data"]
    return {"Authorization": f"Bearer {session['session_id']}"}, session["session_id"]


def _register_stdio_peer(container, *, args: list[str] | None = None, server_id: str = "peer"):
    """Builds the peer connection through the real DI-provided factory,
    not by hand -- so the factory wiring is part of what's tested."""
    registry = container.mcp_transport_registry()
    transport = registry.create(
        "stdio", {"command": sys.executable, "args": [_PEER_SCRIPT, *(args or [])]}
    )
    runtime = container.mcp_client_runtime()
    runtime.register_connection(server_id, transport)
    return runtime, transport


def test_full_stack_over_a_real_subprocess_peer(client) -> None:
    """The headline path: DI factory -> real stdio transport -> real
    peer process -> handshake -> discovery -> permission-filtered
    negotiation -> a real capability call."""
    container = client.container
    runtime, _transport = _register_stdio_peer(container)

    async def scenario() -> dict:
        try:
            connected = await runtime.connect("peer", granted_scopes={"agent_tools"})
            connection = runtime.get("peer")
            call = await runtime.call("peer", "echo", {"text": "over stdio"})
            return {
                "connected": connected,
                "version": connection.agreed_version,
                "transport": connection.transport.transport_type,
                "capabilities": connection.capabilities.names,
                "rejected": [name for name, _ in connection.rejected],
                "call": call,
            }
        finally:
            await runtime.disconnect("peer")

    result = asyncio.run(scenario())

    assert result["connected"] is True
    assert result["version"] == "2025-06-18"
    assert result["transport"] == "stdio"
    # 'echo' needs agent_tools (granted); 'read_secret' needs filesystem
    # (not granted) and is dropped with a reason.
    assert result["capabilities"] == ("echo",)
    assert result["rejected"] == ["read_secret"]
    assert result["call"]["result"]["echoed"] == "over stdio"


def test_ungranted_capability_cannot_be_called_over_a_real_transport(client) -> None:
    from jarvis.core.interfaces.mcp import MCPError

    container = client.container
    runtime, _ = _register_stdio_peer(container)

    async def scenario() -> str:
        try:
            await runtime.connect("peer", granted_scopes=set())
            try:
                await runtime.call("peer", "read_secret")
            except MCPError as err:
                return str(err)
            return ""
        finally:
            await runtime.disconnect("peer")

    assert "was not negotiated" in asyncio.run(scenario())


def test_handshake_failure_over_a_real_peer_is_reported(client) -> None:
    """The peer is told to refuse version agreement; the connection must
    land in FAILED with the peer's own reason, not hang or crash."""
    from jarvis.core.mcp.client import MCPConnectionState

    container = client.container
    runtime, _ = _register_stdio_peer(container, args=["--fail-handshake"])

    async def scenario() -> tuple[bool, object, str]:
        try:
            ok = await runtime.connect("peer")
            connection = runtime.get("peer")
            return ok, connection.state, connection.error
        finally:
            await runtime.disconnect("peer")

    ok, state, error = asyncio.run(scenario())

    assert ok is False
    assert state is MCPConnectionState.FAILED
    assert "No shared protocol version" in error


def test_reconnect_recovers_a_real_transport(client) -> None:
    container = client.container
    runtime, transport = _register_stdio_peer(container)

    async def scenario() -> tuple[int | None, int | None, tuple[str, ...]]:
        try:
            await runtime.connect("peer", granted_scopes={"agent_tools"})
            first_pid = transport.pid
            await runtime.reconnect("peer", granted_scopes={"agent_tools"})
            return first_pid, transport.pid, runtime.get("peer").capabilities.names
        finally:
            await runtime.disconnect("peer")

    first_pid, second_pid, capabilities = asyncio.run(scenario())

    # A genuinely new child process, and the connection works again.
    assert first_pid is not None
    assert second_pid is not None
    assert first_pid != second_pid
    assert capabilities == ("echo",)


def test_transport_lifecycle_events_relay_over_the_real_websocket(client, auth_headers) -> None:
    _headers, token = auth_headers
    container = client.container
    runtime, _ = _register_stdio_peer(container)

    async def scenario() -> None:
        try:
            await runtime.connect("peer", granted_scopes={"agent_tools"})
        finally:
            await runtime.disconnect("peer")

    with client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
        asyncio.run(scenario())
        seen = [ws.receive_json()["type"] for _ in range(5)]

    assert seen == [
        "mcp.connection_changed",  # connecting
        "mcp.handshake_completed",
        "mcp.capabilities_changed",
        "mcp.negotiation_completed",
        "mcp.connection_changed",  # connected
    ]


def test_transport_failure_publishes_its_own_event(client, auth_headers) -> None:
    """A transport failure is distinct from a permission denial or a
    negotiation rejection -- both of those are the protocol working."""
    _headers, token = auth_headers
    container = client.container
    registry = container.mcp_transport_registry()
    runtime = container.mcp_client_runtime()
    runtime.register_connection(
        "dead", registry.create("stdio", {"command": "definitely-not-a-real-binary-xyz"})
    )

    with client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
        assert asyncio.run(runtime.connect("dead")) is False
        messages = [ws.receive_json() for _ in range(3)]

    names = [m["type"] for m in messages]
    assert "mcp.transport_failed" in names
    failure = next(m for m in messages if m["type"] == "mcp.transport_failed")
    assert failure["payload"]["transport_type"] == "stdio"
    assert "cannot start" in failure["payload"]["detail"]


def test_heartbeat_probes_a_real_peer_and_relays(client, auth_headers) -> None:
    _headers, token = auth_headers
    container = client.container
    runtime, _ = _register_stdio_peer(container)
    monitor = container.mcp_heartbeat_monitor()

    async def scenario() -> bool:
        try:
            await runtime.connect("peer", granted_scopes={"agent_tools"})
            (result,) = await monitor.beat_once()
            return result.healthy
        finally:
            await runtime.disconnect("peer")

    with client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
        assert asyncio.run(scenario()) is True
        # Five connect events precede the heartbeat.
        messages = [ws.receive_json() for _ in range(6)]

    heartbeat = messages[-1]
    assert heartbeat["type"] == "mcp.heartbeat"
    assert heartbeat["payload"]["server_id"] == "peer"
    assert heartbeat["payload"]["healthy"] is True


def test_rest_transport_endpoints_reflect_the_live_connection(client, auth_headers) -> None:
    headers, _token = auth_headers
    container = client.container
    runtime, _ = _register_stdio_peer(container)

    async def scenario() -> dict:
        try:
            await runtime.connect("peer", granted_scopes={"agent_tools"})
            # to_thread keeps this scenario on one loop while still
            # exercising the real HTTP surface.
            return await asyncio.to_thread(
                lambda: client.get("/api/v1/mcp/transports/stdio", headers=headers).json()
            )
        finally:
            await runtime.disconnect("peer")

    detail = asyncio.run(scenario())

    assert detail["meta"]["connection_count"] == 1
    assert detail["data"]["connections"][0]["server_id"] == "peer"
    assert detail["data"]["connections"][0]["state"] == "connected"
    assert detail["data"]["connections"][0]["agreed_version"] == "2025-06-18"


def test_mcp_health_snapshot_includes_transports_and_heartbeats(client) -> None:
    """Transport and heartbeat visibility ride M9's single health
    snapshot -- not a second health channel."""
    container = client.container
    runtime, _ = _register_stdio_peer(container)
    monitor = container.mcp_heartbeat_monitor()
    health_monitor = container.health_monitor()

    async def _collect() -> dict:
        return {
            "registered_transports": list(container.mcp_transport_registry().registered_types),
            "heartbeats": list(monitor.snapshot()),
        }

    async def scenario() -> dict:
        try:
            await runtime.connect("peer", granted_scopes={"agent_tools"})
            await monitor.beat_once()
            health_monitor.register_collector("mcp", _collect)
            return await health_monitor.snapshot()
        finally:
            await runtime.disconnect("peer")

    snapshot = asyncio.run(scenario())

    assert "stdio" in snapshot["mcp"]["registered_transports"]
    assert snapshot["mcp"]["heartbeats"][0]["server_id"] == "peer"
