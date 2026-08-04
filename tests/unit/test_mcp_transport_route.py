"""Route tests for the transport/heartbeat MCP endpoints -- Milestone
10.5 Task Group B, deliverable 9. Real ``TestClient`` against the real
DI container, matching ``test_mcp_route.py``'s pattern."""

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


def test_transports_requires_auth(client) -> None:
    assert client.get("/api/v1/mcp/transports").status_code == 401


def test_transport_detail_requires_auth(client) -> None:
    assert client.get("/api/v1/mcp/transports/stdio").status_code == 401


def test_heartbeat_requires_auth(client) -> None:
    assert client.get("/api/v1/mcp/heartbeat").status_code == 401


def test_transports_lists_every_known_transport(client, auth_headers) -> None:
    body = client.get("/api/v1/mcp/transports", headers=auth_headers).json()

    assert body["meta"]["count"] == 5
    assert {t["id"] for t in body["data"]} == {
        "in_process",
        "stdio",
        "websocket",
        "http",
        "ipc",
    }


def test_transports_are_all_registered_now(client, auth_headers) -> None:
    """Task Group A reported an empty ``registered`` list here; Task
    Group B is the pass that fills it."""
    body = client.get("/api/v1/mcp/transports", headers=auth_headers).json()

    assert all(t["registered"] for t in body["data"])
    assert set(body["meta"]["registered"]) == {
        "in_process",
        "stdio",
        "websocket",
        "http",
        "ipc",
    }


def test_transport_detail_returns_traits(client, auth_headers) -> None:
    body = client.get("/api/v1/mcp/transports/stdio", headers=auth_headers).json()

    assert body["data"]["id"] == "stdio"
    assert body["data"]["registered"] is True
    assert body["data"]["requires_subprocess"] is True
    assert body["data"]["connections"] == []
    assert body["meta"]["connection_count"] == 0


def test_transport_detail_unknown_id_is_404(client, auth_headers) -> None:
    response = client.get("/api/v1/mcp/transports/carrier_pigeon", headers=auth_headers)
    assert response.status_code == 404


def test_transport_detail_lists_connections_using_it(client, auth_headers) -> None:
    from jarvis.core.mcp.transport import InProcessTransport

    container = client.container
    runtime = container.mcp_client_runtime()
    runtime.register_connection(
        "self", InProcessTransport(container.mcp_server_runtime(), client_id="peer")
    )

    body = client.get("/api/v1/mcp/transports/in_process", headers=auth_headers).json()

    assert body["meta"]["connection_count"] == 1
    assert body["data"]["connections"][0]["server_id"] == "self"


def test_heartbeat_starts_empty(client, auth_headers) -> None:
    body = client.get("/api/v1/mcp/heartbeat", headers=auth_headers).json()

    assert body["data"] == []
    assert body["meta"]["running"] is False


def test_heartbeat_reports_a_probe_result(client, auth_headers) -> None:
    from jarvis.core.mcp.transport import InProcessTransport

    container = client.container
    server = container.mcp_server_runtime()
    runtime = container.mcp_client_runtime()
    asyncio.run(server.start())
    runtime.register_connection("self", InProcessTransport(server, client_id="peer"))
    asyncio.run(runtime.connect("self"))

    asyncio.run(container.mcp_heartbeat_monitor().beat_once())

    body = client.get("/api/v1/mcp/heartbeat", headers=auth_headers).json()
    assert body["meta"]["count"] == 1
    assert body["data"][0]["server_id"] == "self"
    assert body["data"][0]["healthy"] is True


def test_status_still_works_after_the_task_group_b_changes(client, auth_headers) -> None:
    """Backward compatibility: Task Group A's status shape is unchanged
    except for ``registered_transports`` now being populated."""
    body = client.get("/api/v1/mcp/status", headers=auth_headers).json()["data"]

    assert body["protocol_version"] == "2025-06-18"
    assert body["server"]["id"] == "jarvis"
    assert len(body["registered_transports"]) == 5
