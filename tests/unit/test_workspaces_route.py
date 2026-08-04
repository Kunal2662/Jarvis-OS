"""Workspace REST tests -- Milestone 11 Task Group A.

Against the real FastAPI app and the real DI container, matching
``test_intelligence_route.py``'s pattern: a real session token, the real
Bearer dependency, and a real temp-file database behind it.
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
    with TestClient(app) as test_client:
        test_client.container = container  # type: ignore[attr-defined]
        yield test_client

    asyncio.run(database.dispose())


@pytest.fixture
def auth(client):
    session = client.post("/api/v1/sessions", json={}).json()["data"]
    return {"Authorization": f"Bearer {session['session_id']}"}


def _workspace(client, auth, name: str = "Research") -> str:
    response = client.post("/api/v1/workspaces", json={"name": name}, headers=auth)
    assert response.status_code == 201
    return response.json()["data"]["id"]


# --- Auth + envelope ------------------------------------------------------------


def test_every_route_requires_a_session(client) -> None:
    for method, path in (
        ("get", "/api/v1/workspaces"),
        ("get", "/api/v1/projects"),
        ("get", "/api/v1/notes"),
    ):
        assert getattr(client, method)(path).status_code in (401, 403)


def test_responses_use_the_documented_envelope(client, auth) -> None:
    """``{data, meta}`` for every successful response, per
    ``ARCHITECTURE.md`` §5 -- the same contract every resource router
    since M9 Task Group E follows."""
    created = client.post("/api/v1/workspaces", json={"name": "Enveloped"}, headers=auth)
    listed = client.get("/api/v1/workspaces", headers=auth)

    for response in (created, listed):
        assert set(response.json()) == {"data", "meta"}
    assert created.json()["meta"]["created"] is True
    assert listed.json()["meta"]["count"] == 1


# --- Workspaces -----------------------------------------------------------------


def test_workspace_crud_round_trip(client, auth) -> None:
    workspace_id = _workspace(client, auth)

    fetched = client.get(f"/api/v1/workspaces/{workspace_id}", headers=auth)
    assert fetched.json()["data"]["name"] == "Research"

    patched = client.patch(
        f"/api/v1/workspaces/{workspace_id}", json={"name": "Renamed"}, headers=auth
    )
    assert patched.json()["data"]["name"] == "Renamed"

    assert client.delete(f"/api/v1/workspaces/{workspace_id}", headers=auth).status_code == 204
    assert client.get(f"/api/v1/workspaces/{workspace_id}", headers=auth).status_code == 404


def test_invalid_input_is_400_not_500(client, auth) -> None:
    """A ``ServiceError`` means the caller asked for something invalid.
    Nothing broke, so it must not read as a server fault."""
    empty = client.post("/api/v1/workspaces", json={"name": "  "}, headers=auth)
    bad_status = client.get("/api/v1/workspaces?status=activ", headers=auth)

    assert empty.status_code == 400
    assert bad_status.status_code == 400


def test_missing_rows_are_404(client, auth) -> None:
    assert client.get("/api/v1/workspaces/nope", headers=auth).status_code == 404
    assert client.get("/api/v1/projects/nope", headers=auth).status_code == 404
    assert client.get("/api/v1/notes/nope", headers=auth).status_code == 404
    assert client.delete("/api/v1/notes/nope", headers=auth).status_code == 404


def test_metadata_route_reports_derived_counts(client, auth) -> None:
    workspace_id = _workspace(client, auth)
    client.post("/api/v1/projects", json={"workspace_id": workspace_id, "name": "P"}, headers=auth)
    client.post("/api/v1/notes", json={"workspace_id": workspace_id, "title": "N"}, headers=auth)

    data = client.get(f"/api/v1/workspaces/{workspace_id}/metadata", headers=auth).json()["data"]

    assert data["project_count"] == 1
    assert data["note_count"] == 1


def test_overview_and_context_are_served_by_the_manager(client, auth) -> None:
    workspace_id = _workspace(client, auth)

    overview = client.get(f"/api/v1/workspaces/{workspace_id}/overview", headers=auth)
    context = client.get(f"/api/v1/workspaces/{workspace_id}/context", headers=auth)

    assert set(overview.json()["data"]) >= {"workspace", "projects", "notes", "metadata"}
    # Context is the overview plus the neighbours -- additive by design.
    assert set(context.json()["data"]) >= set(overview.json()["data"])
    assert "related_knowledge" in context.json()["data"]


def test_overview_of_an_unknown_workspace_is_404(client, auth) -> None:
    assert client.get("/api/v1/workspaces/nope/overview", headers=auth).status_code == 404


# --- Projects -------------------------------------------------------------------


def test_project_crud_and_workspace_filter(client, auth) -> None:
    one = _workspace(client, auth, "One")
    two = _workspace(client, auth, "Two")
    client.post("/api/v1/projects", json={"workspace_id": one, "name": "A"}, headers=auth)
    client.post("/api/v1/projects", json={"workspace_id": two, "name": "B"}, headers=auth)

    filtered = client.get(f"/api/v1/projects?workspace_id={one}", headers=auth).json()

    assert [p["name"] for p in filtered["data"]] == ["A"]
    assert filtered["meta"]["count"] == 1


def test_creating_a_project_in_a_missing_workspace_is_400(client, auth) -> None:
    response = client.post(
        "/api/v1/projects", json={"workspace_id": "nope", "name": "Orphan"}, headers=auth
    )

    assert response.status_code == 400


def test_deleting_a_project_keeps_its_notes(client, auth) -> None:
    workspace_id = _workspace(client, auth)
    project_id = client.post(
        "/api/v1/projects", json={"workspace_id": workspace_id, "name": "P"}, headers=auth
    ).json()["data"]["id"]
    note_id = client.post(
        "/api/v1/notes",
        json={"workspace_id": workspace_id, "title": "Survivor", "project_id": project_id},
        headers=auth,
    ).json()["data"]["id"]

    assert client.delete(f"/api/v1/projects/{project_id}", headers=auth).status_code == 204

    note = client.get(f"/api/v1/notes/{note_id}", headers=auth)
    assert note.status_code == 200
    assert note.json()["data"]["project_id"] is None


# --- Notes ----------------------------------------------------------------------


def test_note_crud_round_trip(client, auth) -> None:
    workspace_id = _workspace(client, auth)
    note_id = client.post(
        "/api/v1/notes",
        json={"workspace_id": workspace_id, "title": "Draft", "content": "body"},
        headers=auth,
    ).json()["data"]["id"]

    patched = client.patch(
        f"/api/v1/notes/{note_id}", json={"title": "Final", "pinned": True}, headers=auth
    ).json()["data"]

    assert patched["title"] == "Final"
    assert patched["pinned"] is True
    assert client.delete(f"/api/v1/notes/{note_id}", headers=auth).status_code == 204


def test_clear_project_unfiles_a_note(client, auth) -> None:
    workspace_id = _workspace(client, auth)
    project_id = client.post(
        "/api/v1/projects", json={"workspace_id": workspace_id, "name": "P"}, headers=auth
    ).json()["data"]["id"]
    note_id = client.post(
        "/api/v1/notes",
        json={"workspace_id": workspace_id, "title": "N", "project_id": project_id},
        headers=auth,
    ).json()["data"]["id"]

    # A plain PATCH leaves the filing alone...
    unchanged = client.patch(f"/api/v1/notes/{note_id}", json={"title": "N2"}, headers=auth).json()[
        "data"
    ]
    assert unchanged["project_id"] == project_id

    # ...and clear_project is how you actually unfile it.
    cleared = client.patch(
        f"/api/v1/notes/{note_id}", json={"clear_project": True}, headers=auth
    ).json()["data"]
    assert cleared["project_id"] is None


def test_a_note_cannot_span_two_workspaces(client, auth) -> None:
    one = _workspace(client, auth, "One")
    two = _workspace(client, auth, "Two")
    project_id = client.post(
        "/api/v1/projects", json={"workspace_id": two, "name": "Elsewhere"}, headers=auth
    ).json()["data"]["id"]

    response = client.post(
        "/api/v1/notes",
        json={"workspace_id": one, "title": "Confused", "project_id": project_id},
        headers=auth,
    )

    assert response.status_code == 400
