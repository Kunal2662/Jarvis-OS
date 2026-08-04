"""Integration tests for the Universal Search & Knowledge Platform API's
real FastAPI wiring -- ``/api/v1/search`` + ``/api/v1/knowledge/*``
(Milestone 10A). Real, in-process ``TestClient`` against a real temp-file
SQLite database, matching ``test_agent_route.py``'s established pattern."""

from __future__ import annotations

import asyncio
import json
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
    from tests.fakes.fake_llm import FakeLLM

    container = Container()
    settings = Settings(data_dir=str(tmp_path / "data"))
    settings.db.url = f"sqlite+aiosqlite:///{tmp_path / 'jarvis.db'}"
    container.settings.override(settings)
    container.llm_provider.override(
        FakeLLM(
            json.dumps(
                {
                    "entities": [
                        {"name": "Project X", "type": "project", "description": "A project."}
                    ],
                    "relationships": [],
                }
            )
        )
    )

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


def test_search_requires_auth(client) -> None:
    assert client.post("/api/v1/search", json={"query": "x"}).status_code == 401


def test_search_returns_envelope(client, auth_headers) -> None:
    response = client.post("/api/v1/search", json={"query": "anything"}, headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert "data" in body
    assert "sources" in body["meta"]
    # Grows as new searchable subsystems register: M10A shipped memory/
    # knowledge/commands, M10B added goals, and M11 Task Group A added
    # the three workspace sources. A registry that accepts a new source
    # without SearchService changing is exactly what M10A built.
    assert set(body["meta"]["sources"]) == {
        "memory",
        "knowledge",
        "goals",
        "commands",
        "workspaces",
        "projects",
        "notes",
    }


def test_learn_then_get_entity(client, auth_headers) -> None:
    learn_response = client.post(
        "/api/v1/knowledge/learn", params={"limit": 20}, headers=auth_headers
    )
    assert learn_response.status_code == 200

    # No memories exist yet in this fresh DB, so learn() is a no-op; seed
    # the graph directly via the correction endpoint instead, which always
    # extracts from its own statement text.
    correct_response = client.post(
        "/api/v1/knowledge/correct",
        json={"statement": "Project X is an important initiative."},
        headers=auth_headers,
    )
    assert correct_response.status_code == 200

    entity_response = client.get("/api/v1/knowledge/entities/Project X", headers=auth_headers)
    assert entity_response.status_code == 200
    body = entity_response.json()
    assert body["meta"]["found"] is True
    assert body["data"]["name"] == "Project X"


def test_get_unknown_entity_returns_not_found_meta(client, auth_headers) -> None:
    response = client.get("/api/v1/knowledge/entities/Nonexistent", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["found"] is False
    assert body["data"] is None


def test_export_import_round_trip_over_rest(client, auth_headers) -> None:
    client.post(
        "/api/v1/knowledge/correct",
        json={"statement": "Project X is an important initiative."},
        headers=auth_headers,
    )

    export_response = client.get("/api/v1/knowledge/export", headers=auth_headers)
    assert export_response.status_code == 200
    exported = export_response.json()["data"]
    assert len(exported["entities"]) >= 1

    import_response = client.post(
        "/api/v1/knowledge/import",
        json={"data": json.dumps(exported)},
        headers=auth_headers,
    )
    assert import_response.status_code == 200
    assert import_response.json()["data"]["entities_created"] == 0  # ids already exist, skipped


def test_ask_endpoint(client, auth_headers) -> None:
    response = client.get(
        "/api/v1/knowledge/ask", params={"query": "Project X"}, headers=auth_headers
    )
    assert response.status_code == 200
    assert "answer" in response.json()["data"]
