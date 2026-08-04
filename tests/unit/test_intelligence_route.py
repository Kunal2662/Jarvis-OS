"""Integration tests for the Intelligence Layer API's real FastAPI wiring
-- ``/api/v1/goals`` + ``/api/v1/intelligence/*`` (Milestone 10B). Real,
in-process ``TestClient`` against a real temp-file SQLite database,
matching ``test_knowledge_route.py``'s established pattern."""

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
    session = client.post("/api/v1/sessions", json={}).json()["data"]
    return {"Authorization": f"Bearer {session['session_id']}"}


def test_create_goal_requires_auth(client) -> None:
    response = client.post("/api/v1/goals", json={"title": "Learn Rust"})
    assert response.status_code == 401


def test_create_then_list_then_get_goal(client, auth_headers) -> None:
    create = client.post("/api/v1/goals", json={"title": "Learn Rust"}, headers=auth_headers)
    assert create.status_code == 201
    goal_id = create.json()["data"]["id"]

    listing = client.get("/api/v1/goals", headers=auth_headers)
    assert listing.status_code == 200
    assert any(g["id"] == goal_id for g in listing.json()["data"])

    detail = client.get(f"/api/v1/goals/{goal_id}", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.json()["data"]["title"] == "Learn Rust"
    assert detail.json()["data"]["children"] == []


def test_create_goal_rejects_empty_title(client, auth_headers) -> None:
    response = client.post("/api/v1/goals", json={"title": "   "}, headers=auth_headers)
    assert response.status_code == 422


def test_get_unknown_goal_returns_not_found_meta(client, auth_headers) -> None:
    response = client.get("/api/v1/goals/does-not-exist", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["meta"]["found"] is False


def test_update_goal_progress_over_rest(client, auth_headers) -> None:
    create = client.post("/api/v1/goals", json={"title": "Write a book"}, headers=auth_headers)
    goal_id = create.json()["data"]["id"]

    response = client.patch(
        f"/api/v1/goals/{goal_id}/progress", json={"progress_percent": 60}, headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["data"]["progress_percent"] == 60


def test_complete_goal_over_rest(client, auth_headers) -> None:
    create = client.post("/api/v1/goals", json={"title": "Finish report"}, headers=auth_headers)
    goal_id = create.json()["data"]["id"]

    response = client.post(f"/api/v1/goals/{goal_id}/complete", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "completed"


def test_delete_goal_over_rest(client, auth_headers) -> None:
    create = client.post("/api/v1/goals", json={"title": "Temp goal"}, headers=auth_headers)
    goal_id = create.json()["data"]["id"]

    response = client.delete(f"/api/v1/goals/{goal_id}", headers=auth_headers)
    assert response.status_code == 200
    assert (
        client.get(f"/api/v1/goals/{goal_id}", headers=auth_headers).json()["meta"]["found"]
        is False
    )


def test_context_endpoint(client, auth_headers) -> None:
    response = client.get("/api/v1/intelligence/context", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()["data"]
    assert "hour_of_day" in body
    assert "day_of_week" in body


def test_suggestions_endpoint(client, auth_headers) -> None:
    response = client.get("/api/v1/intelligence/suggestions", headers=auth_headers)
    assert response.status_code == 200
    assert "count" in response.json()["meta"]


def test_briefing_endpoint(client, auth_headers) -> None:
    response = client.get("/api/v1/intelligence/briefing", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()["data"]
    assert "goals_due_soon" in body
    assert "top_suggestions" in body


def test_set_then_get_then_list_preference(client, auth_headers) -> None:
    set_response = client.post(
        "/api/v1/intelligence/preferences",
        json={"key": "theme", "value": "dark"},
        headers=auth_headers,
    )
    assert set_response.status_code == 200
    assert set_response.json()["data"]["value"] == "dark"

    get_response = client.get("/api/v1/intelligence/preferences/theme", headers=auth_headers)
    assert get_response.status_code == 200
    assert get_response.json()["data"]["value"] == "dark"

    list_response = client.get("/api/v1/intelligence/preferences", headers=auth_headers)
    assert list_response.status_code == 200
    assert list_response.json()["meta"]["count"] == 1


def test_get_unknown_preference_returns_not_found_meta(client, auth_headers) -> None:
    response = client.get("/api/v1/intelligence/preferences/does-not-exist", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["meta"]["found"] is False
