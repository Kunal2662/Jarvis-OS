"""End-to-end MCP platform test -- Milestone 10.5 Task Group A.

Exercises the real client runtime against the real server runtime over
the real ``InProcessTransport``, driven by the real DI container, with
the real M9 ``PermissionModel`` deciding what is allowed -- plus the
real Runtime WebSocket relay carrying the resulting events. The same
"REST/runtime write side + WebSocket read side exercised together"
discipline ``test_knowledge_platform_e2e.py`` and
``test_intelligence_platform_e2e.py`` established.
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
    container.runtime_ws_hub().start()

    with TestClient(app) as test_client:
        test_client.container = container  # type: ignore[attr-defined]
        yield test_client

    asyncio.run(database.dispose())


@pytest.fixture
def auth_headers(client):
    session = client.post("/api/v1/sessions", json={}).json()
    return {"Authorization": f"Bearer {session['session_id']}"}, session["session_id"]


def _wire(container, *, expose_echo: bool = True):
    """Registers a loopback connection: JARVIS's own MCP client talking
    to JARVIS's own MCP server, over the in-process transport."""
    from jarvis.core.interfaces.mcp import MCPCapability
    from jarvis.core.mcp.transport import InProcessTransport

    server = container.mcp_server_runtime()
    runtime = container.mcp_client_runtime()

    asyncio.run(server.start())
    if expose_echo:

        async def _echo(params):
            return {"echoed": params.get("text", "")}

        asyncio.run(
            server.expose(
                MCPCapability(name="echo", kind="tool", permissions=("agent_tools",)), _echo
            )
        )
    runtime.register_connection("self", InProcessTransport(server, client_id="peer"))
    return server, runtime


def test_full_lifecycle_from_denied_to_granted_over_the_real_permission_model(client) -> None:
    """The headline path: an ungranted capability is negotiated away,
    the grant flows through M9's real store, and a reconnect makes it
    genuinely callable."""
    from jarvis.core.mcp.server import principal_for

    container = client.container
    server, runtime = _wire(container)
    permissions = container.permission_model()

    # 1. Connect with nothing granted -- succeeds, but negotiates zero
    #    capabilities (least-privilege by construction).
    assert asyncio.run(runtime.connect("self", granted_scopes=server.granted_scopes("peer")))
    connection = runtime.get("self")
    assert connection.capabilities.names == ()
    assert [name for name, _ in connection.rejected] == ["echo"]

    # 2. The connect declared the scope as PENDING in the shared store.
    assert ("mcp:peer", "agent_tools") in permissions.pending()

    # 3. Grant, reconnect, and the capability becomes real.
    asyncio.run(permissions.grant(principal_for("peer"), "agent_tools"))
    assert asyncio.run(runtime.reconnect("self", granted_scopes=server.granted_scopes("peer")))
    assert runtime.get("self").capabilities.names == ("echo",)

    # 4. It genuinely executes, end to end, through the transport.
    assert asyncio.run(runtime.call("self", "echo", {"text": "hi"})) == {"result": {"echoed": "hi"}}


def test_permission_grant_persists_across_a_new_permission_model(client, tmp_path: Path) -> None:
    """MCP grants ride M9's existing persisted store -- proven by
    reading them back through a second model instance over the same
    file, not by trusting in-memory state."""
    from jarvis.core.config import paths as _paths
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.mcp.server import principal_for
    from jarvis.core.plugins.permissions import PermissionModel

    container = client.container
    permissions = container.permission_model()
    asyncio.run(permissions.grant(principal_for("peer"), "agent_tools"))

    store = _paths.config_dir(container.settings().resolved_data_dir) / "plugin_permissions.json"
    reloaded = PermissionModel(EventBus(), store_path=store)

    assert reloaded.is_granted("mcp:peer", "agent_tools") is True


def test_events_relay_over_the_real_websocket(client, auth_headers) -> None:
    """Connection-state and capability changes reach a real WebSocket
    subscriber, not just an in-process listener."""
    _headers, token = auth_headers
    container = client.container

    with client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
        _server, runtime = _wire(container)
        # expose() published mcp.capabilities_changed.
        assert ws.receive_json()["type"] == "mcp.capabilities_changed"

        asyncio.run(runtime.connect("self", granted_scopes=set()))

        types = [ws.receive_json()["type"] for _ in range(3)]
        assert types == [
            "mcp.connection_changed",  # connecting
            "mcp.capabilities_changed",  # discovery replaced the peer set
            "mcp.connection_changed",  # connected
        ]


def test_permission_denial_relays_over_the_real_websocket(client, auth_headers) -> None:
    _headers, token = auth_headers
    container = client.container
    server, _runtime = _wire(container)

    with client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
        permitted, _reason = asyncio.run(server.check_permitted("peer", "echo"))
        assert permitted is False

        message = ws.receive_json()
        assert message["type"] == "mcp.permission_denied"
        assert message["payload"]["principal"] == "mcp:peer"
        assert message["payload"]["capability"] == "echo"


def test_rest_status_reflects_the_live_runtime(client, auth_headers) -> None:
    headers, _token = auth_headers
    container = client.container
    server, runtime = _wire(container)
    asyncio.run(runtime.connect("self", granted_scopes=server.granted_scopes("peer")))

    status = client.get("/api/v1/mcp/status", headers=headers).json()["data"]
    connections = client.get("/api/v1/mcp/connections", headers=headers).json()["data"]

    assert status["server"]["state"] == "running"
    assert status["client"]["connection_count"] == 1
    assert connections[0]["state"] == "connected"
    assert connections[0]["agreed_version"] == "2025-06-18"
    # The ungranted capability is reported with its reason, not hidden.
    assert connections[0]["rejected"][0]["name"] == "echo"


def test_mcp_health_joins_the_existing_health_snapshot(client) -> None:
    """MCP health rides M9's ``HealthMonitor.register_collector``
    extension point -- one health channel, not a second one."""
    container = client.container
    server, runtime = _wire(container)
    monitor = container.health_monitor()

    async def _collect():
        return {
            "server_running": server.is_running,
            "capability_count": len(server.capabilities),
            "connection_count": len(runtime.server_ids),
        }

    monitor.register_collector("mcp", _collect)
    snapshot = asyncio.run(monitor.snapshot())

    assert snapshot["mcp"]["server_running"] is True
    assert snapshot["mcp"]["capability_count"] == 1
    assert snapshot["mcp"]["connection_count"] == 1


def test_no_network_transport_ships_in_task_group_a(client, auth_headers) -> None:
    """Guards the scope boundary: the abstraction is real, the network
    transports are explicitly future work."""
    headers, _token = auth_headers

    body = client.get("/api/v1/mcp/transports", headers=headers).json()["data"]

    assert body["registered"] == []
    assert set(body["known"]) == {"in_process", "stdio", "websocket", "http", "ipc"}
