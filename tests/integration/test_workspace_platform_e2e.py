"""Workspace platform end-to-end -- Milestone 11 Task Group A.

Drives the real DI container, the real REST app, the real EventBus and
the real ``RuntimeWebSocketHub``. The unit tests prove each piece; this
proves they are wired to each other -- that a REST write reaches a
WebSocket subscriber, and that the three search sources are registered
in the *shared* ``SearchService`` rather than a private one.
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

    container.runtime_ws_hub().stop()
    asyncio.run(database.dispose())


@pytest.fixture
def auth(client):
    session = client.post("/api/v1/sessions", json={}).json()["data"]
    return {"Authorization": f"Bearer {session['session_id']}"}, session["session_id"]


def test_rest_writes_reach_a_real_websocket_subscriber(client, auth) -> None:
    """One EventBus, one relay -- not a second notification path bolted
    onto the workspace domain."""
    headers, token = auth

    with client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
        workspace_id = client.post(
            "/api/v1/workspaces", json={"name": "Live"}, headers=headers
        ).json()["data"]["id"]
        project_id = client.post(
            "/api/v1/projects", json={"workspace_id": workspace_id, "name": "P"}, headers=headers
        ).json()["data"]["id"]
        client.post(
            "/api/v1/notes", json={"workspace_id": workspace_id, "title": "N"}, headers=headers
        )

        received = [ws.receive_json() for _ in range(3)]

    assert [frame["type"] for frame in received] == [
        "workspace.updated",
        "project.updated",
        "note.updated",
    ]
    assert received[0]["payload"]["workspace_id"] == workspace_id
    assert received[0]["payload"]["action"] == "created"
    assert received[1]["payload"]["project_id"] == project_id


def test_the_three_sources_join_the_shared_search_service(client) -> None:
    """Registered through M10A's provider registry with no change to
    ``SearchService`` itself -- which is the extensibility that registry
    was built for."""
    search = client.container.search_service()

    assert {"workspaces", "projects", "notes"} <= {s.source_type for s in search.get_sources()}


def test_workspace_content_is_findable_through_universal_search(client, auth) -> None:
    headers, _ = auth
    workspace_id = client.post(
        "/api/v1/workspaces", json={"name": "Quantum research"}, headers=headers
    ).json()["data"]["id"]
    client.post(
        "/api/v1/projects",
        json={"workspace_id": workspace_id, "name": "Quantum error correction"},
        headers=headers,
    )
    client.post(
        "/api/v1/notes",
        json={"workspace_id": workspace_id, "title": "Quantum notes"},
        headers=headers,
    )

    results = asyncio.run(client.container.search_service().search("quantum", top_k=20))

    assert {"workspaces", "projects", "notes"} <= {r.source for r in results}


def test_the_manager_reads_the_containers_own_service(client, auth) -> None:
    """One ``WorkspaceService`` singleton behind both the REST routes and
    the manager -- so the two can never disagree about what exists."""
    headers, _ = auth
    container = client.container
    workspace_id = client.post(
        "/api/v1/workspaces", json={"name": "Shared"}, headers=headers
    ).json()["data"]["id"]

    overview = asyncio.run(container.workspace_manager().overview(workspace_id))

    assert overview["workspace"]["name"] == "Shared"
    assert container.workspace_service() is container.workspace_service()


def test_deleting_a_workspace_cascades_through_the_real_database(client, auth) -> None:
    headers, _ = auth
    workspace_id = client.post(
        "/api/v1/workspaces", json={"name": "Doomed"}, headers=headers
    ).json()["data"]["id"]
    note_id = client.post(
        "/api/v1/notes", json={"workspace_id": workspace_id, "title": "N"}, headers=headers
    ).json()["data"]["id"]

    assert client.delete(f"/api/v1/workspaces/{workspace_id}", headers=headers).status_code == 204

    assert client.get(f"/api/v1/notes/{note_id}", headers=headers).status_code == 404
    assert client.get("/api/v1/notes", headers=headers).json()["meta"]["count"] == 0
