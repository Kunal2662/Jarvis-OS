"""Route tests for the MCP platform API -- Milestone 10.5 Task Group A,
deliverable 9. Real in-process ``TestClient`` against a real temp-file
SQLite database and the real DI container, matching
``test_intelligence_route.py``'s established pattern."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

pytest.importorskip("langgraph")
pytest.importorskip("langchain_core")


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
def auth_headers(client):
    session = client.post("/api/v1/sessions", json={}).json()
    return {"Authorization": f"Bearer {session['session_id']}"}


def test_status_requires_auth(client) -> None:
    assert client.get("/api/v1/mcp/status").status_code == 401


def test_capabilities_requires_auth(client) -> None:
    assert client.get("/api/v1/mcp/capabilities").status_code == 401


def test_status_reports_both_runtimes(client, auth_headers) -> None:
    response = client.get("/api/v1/mcp/status", headers=auth_headers)
    assert response.status_code == 200

    body = response.json()["data"]
    assert body["protocol_version"] == "2025-06-18"
    assert body["server"]["id"] == "jarvis"
    assert body["client"]["connection_count"] == 0
    assert "healthy" in response.json()["meta"]


def test_status_reflects_a_started_server(client, auth_headers) -> None:
    asyncio.run(client.container.mcp_server_runtime().start())

    body = client.get("/api/v1/mcp/status", headers=auth_headers).json()["data"]

    assert body["server"]["state"] == "running"
    assert body["server"]["healthy"] is True


def test_capabilities_starts_empty_then_reflects_exposure(client, auth_headers) -> None:
    from jarvis.core.interfaces.mcp import MCPCapability

    assert client.get("/api/v1/mcp/capabilities", headers=auth_headers).json()["meta"]["count"] == 0

    server = client.container.mcp_server_runtime()
    asyncio.run(server.expose(MCPCapability(name="echo", permissions=("agent_tools",))))

    body = client.get("/api/v1/mcp/capabilities", headers=auth_headers).json()
    assert body["meta"]["count"] == 1
    assert body["data"][0]["name"] == "echo"
    assert body["data"][0]["permissions"] == ["agent_tools"]


def test_capabilities_filters_by_kind(client, auth_headers) -> None:
    from jarvis.core.interfaces.mcp import MCPCapability

    server = client.container.mcp_server_runtime()
    asyncio.run(server.expose(MCPCapability(name="t", kind="tool")))
    asyncio.run(server.expose(MCPCapability(name="r", kind="resource")))

    body = client.get("/api/v1/mcp/capabilities?kind=resource", headers=auth_headers).json()

    assert [c["name"] for c in body["data"]] == ["r"]


def test_connections_starts_empty(client, auth_headers) -> None:
    response = client.get("/api/v1/mcp/connections", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["meta"]["count"] == 0


def test_connections_reports_a_registered_peer(client, auth_headers) -> None:
    from jarvis.core.mcp.transport import InProcessTransport

    server = client.container.mcp_server_runtime()
    runtime = client.container.mcp_client_runtime()
    runtime.register_connection("self", InProcessTransport(server, client_id="self"))

    body = client.get("/api/v1/mcp/connections", headers=auth_headers).json()

    assert body["meta"]["count"] == 1
    assert body["data"][0]["server_id"] == "self"
    assert body["data"][0]["state"] == "disconnected"
    assert body["data"][0]["transport"] == "in_process"


def test_transports_reports_the_whole_vocabulary(client, auth_headers) -> None:
    """Task Group A shipped the abstraction with nothing registered and
    this endpoint returned a bare ``{known, registered}`` pair. Task
    Group B registered all five and reshaped the response into one
    descriptor per transport -- an intra-milestone shape change, with
    the old pair's information preserved (``data[].id`` is the former
    ``known``; ``meta.registered`` is the former ``registered``)."""
    body = client.get("/api/v1/mcp/transports", headers=auth_headers).json()

    assert sorted(t["id"] for t in body["data"]) == [
        "http",
        "in_process",
        "ipc",
        "stdio",
        "websocket",
    ]
    assert sorted(body["meta"]["registered"]) == [
        "http",
        "in_process",
        "ipc",
        "stdio",
        "websocket",
    ]
    assert body["meta"]["count"] == 5
