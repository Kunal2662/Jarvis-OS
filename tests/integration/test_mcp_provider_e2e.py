"""End-to-end Provider Framework test -- Milestone 10.5 Task Group C.

Drives the real provider manager, over a **real** transport built by
the real factory, against a **real** peer subprocess, through the real
DI container, with the real M9 ``PermissionModel`` deciding what is
allowed -- and asserts the lifecycle events reach a real WebSocket
subscriber and the health payload reaches M9's real ``HealthMonitor``.

Same single-``asyncio.run``-per-scenario discipline Task Group B's
integration test established: a real subprocess' pipes are bound to the
loop that created them.
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
    session = client.post("/api/v1/sessions", json={}).json()
    return {"Authorization": f"Bearer {session['session_id']}"}, session["session_id"]


def _metadata(**kwargs):
    from jarvis.core.mcp.providers.metadata import ProviderMetadata

    return ProviderMetadata(
        name="Demo Peer",
        version="1.2.3",
        author="jarvis",
        description="A real stdio MCP peer.",
        capabilities=("echo",),
        transport="stdio",
        required_permissions=("agent_tools",),
        **kwargs,
    )


def _config(*, args: list[str] | None = None):
    from jarvis.core.mcp.providers.metadata import ProviderConfig

    return ProviderConfig(
        options={"command": sys.executable, "args": [_PEER_SCRIPT, *(args or [])]}
    )


def test_install_declares_permissions_without_granting_them(client) -> None:
    container = client.container
    manager = container.mcp_provider_manager()
    permissions = container.permission_model()

    asyncio.run(manager.install("demo", _metadata(), _config()))

    assert ("mcp:demo", "agent_tools") in permissions.pending()
    assert manager.resolve_scopes("demo") == set()


def test_full_lifecycle_against_a_real_peer_process(client) -> None:
    """The headline path: install -> connect over a real stdio
    subprocess -> grant -> reconnect with the capability negotiated ->
    suspend -> resume -> remove."""
    from jarvis.core.mcp.providers.metadata import ProviderState
    from jarvis.core.mcp.server import principal_for

    container = client.container
    manager = container.mcp_provider_manager()
    permissions = container.permission_model()

    async def scenario() -> dict:
        try:
            await manager.install("demo", _metadata(), _config())
            await manager.connect("demo")
            before = (await manager.status("demo"))["detail"]["capabilities"]

            await permissions.grant(principal_for("demo"), "agent_tools")
            await manager.disconnect("demo")
            await manager.connect("demo")
            after = (await manager.status("demo"))["detail"]["capabilities"]

            await manager.suspend("demo")
            suspended = manager.registry.require("demo").state
            await manager.resume("demo")
            resumed = manager.registry.require("demo").state

            return {
                "before": before,
                "after": after,
                "suspended": suspended,
                "resumed": resumed,
            }
        finally:
            await manager.remove("demo")

    result = asyncio.run(scenario())

    # Ungranted: the capability is negotiated away. Granted: it appears.
    assert result["before"] == []
    assert result["after"] == ["echo"]
    assert result["suspended"] is ProviderState.SUSPENDED
    assert result["resumed"] is ProviderState.CONNECTED
    assert manager.registry.has("demo") is False


def test_a_failing_provider_does_not_stop_the_others(client) -> None:
    """Fault isolation over real transports, not fakes."""
    from jarvis.core.mcp.providers.metadata import ProviderConfig, ProviderState

    container = client.container
    manager = container.mcp_provider_manager()

    async def scenario() -> dict:
        try:
            await manager.install("good", _metadata(), _config())
            await manager.install(
                "bad",
                _metadata(),
                ProviderConfig(options={"command": "definitely-not-a-real-binary-xyz"}),
            )
            results = await manager.connect_all()
            return {
                "results": results,
                "good": manager.registry.require("good").state,
                "bad": manager.registry.require("bad").state,
            }
        finally:
            await manager.disconnect_all()

    outcome = asyncio.run(scenario())

    assert outcome["results"] == {"good": True, "bad": False}
    assert outcome["good"] is ProviderState.CONNECTED
    assert outcome["bad"] is ProviderState.FAILED


def test_lifecycle_events_relay_over_the_real_websocket(client, auth_headers) -> None:
    _headers, token = auth_headers
    container = client.container
    manager = container.mcp_provider_manager()

    async def scenario() -> None:
        try:
            await manager.install("demo", _metadata(), _config())
            await manager.connect("demo")
            await manager.suspend("demo")
            await manager.resume("demo")
        finally:
            await manager.disconnect_all()

    with client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
        asyncio.run(scenario())
        messages: list[dict] = []
        # Provider events are interleaved with the connection/handshake
        # events Task Groups A and B publish; filter to this category.
        for _ in range(24):
            message = ws.receive_json()
            if message["type"] == "mcp.provider_changed":
                messages.append(message)
            if len(messages) == 5:
                break

    assert [m["payload"]["action"] for m in messages] == [
        "registered",
        "initialized",
        "connected",
        "suspended",
        "resumed",
    ]
    assert messages[-1]["payload"]["state"] == "connected"
    assert all(m["payload"]["provider_id"] == "demo" for m in messages)


def test_provider_health_joins_the_existing_health_snapshot(client) -> None:
    """Provider health rides M9's single ``HealthMonitor`` collector --
    not a second health subsystem."""
    container = client.container
    manager = container.mcp_provider_manager()
    health_monitor = container.health_monitor()

    async def scenario() -> dict:
        try:
            await manager.install("demo", _metadata(), _config())
            await manager.connect("demo")
            health_monitor.register_collector("mcp_providers", manager.collect_health)
            return await health_monitor.snapshot()
        finally:
            await manager.remove("demo")

    snapshot = asyncio.run(scenario())

    assert snapshot["mcp_providers"]["count"] == 1
    assert snapshot["mcp_providers"]["connected"] == ["demo"]
    assert snapshot["mcp_providers"]["unhealthy"] == []


def test_rest_reflects_the_live_provider(client, auth_headers) -> None:
    headers, _token = auth_headers
    container = client.container
    manager = container.mcp_provider_manager()

    async def scenario() -> dict:
        try:
            await manager.install("demo", _metadata(), _config())
            await manager.connect("demo")
            return await asyncio.to_thread(
                lambda: {
                    "list": client.get("/api/v1/mcp/providers", headers=headers).json(),
                    "detail": client.get("/api/v1/mcp/providers/demo", headers=headers).json(),
                    "health": client.get(
                        "/api/v1/mcp/providers/demo/health", headers=headers
                    ).json(),
                    "metadata": client.get(
                        "/api/v1/mcp/providers/demo/metadata", headers=headers
                    ).json(),
                }
            )
        finally:
            await manager.remove("demo")

    result = asyncio.run(scenario())

    assert result["list"]["data"][0]["state"] == "connected"
    assert result["detail"]["data"]["detail"]["agreed_version"] == "2025-06-18"
    assert result["health"]["data"]["healthy"] is True
    assert result["metadata"]["data"]["version"] == "1.2.3"


def test_provider_uses_the_transport_factory_from_di(client) -> None:
    """The provider framework builds its transport through Task Group
    B's registry rather than constructing one itself -- proven by the
    connection reporting the transport type the factory produced."""
    container = client.container
    manager = container.mcp_provider_manager()
    client_runtime = container.mcp_client_runtime()

    async def scenario() -> str:
        try:
            await manager.install("demo", _metadata(), _config())
            await manager.connect("demo")
            return client_runtime.get("demo").transport.transport_type
        finally:
            await manager.remove("demo")

    assert asyncio.run(scenario()) == "stdio"
