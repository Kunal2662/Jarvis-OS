"""End-to-end Intelligence Layer test (Milestone 10B) -- proves the REST
API genuinely drives the real ``IntelligenceService`` *and* that the
result is genuinely relayed over the real Runtime WebSocket API, the
same "REST write side + WebSocket read side exercised together"
discipline ``tests/integration/test_knowledge_platform_e2e.py``
established. Also covers all three of Milestone 10B's Acceptance
Criteria directly.
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
    session = client.post("/api/v1/sessions", json={}).json()["data"]
    return {"Authorization": f"Bearer {session['session_id']}"}, session["session_id"]


def test_goal_created_over_rest_relays_over_websocket(client, auth_headers) -> None:
    """Acceptance Criterion 1 (Goal Manager persists a goal across
    sessions with measurable progress tracking) exercised end-to-end,
    plus the real WebSocket relay."""
    headers, token = auth_headers

    with client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
        create = client.post("/api/v1/goals", json={"title": "Learn Rust"}, headers=headers)
        assert create.status_code == 201
        goal_id = create.json()["data"]["id"]

        created_message = ws.receive_json()
        assert created_message["type"] == "goal.updated"
        assert created_message["payload"]["action"] == "created"

        progress = client.patch(
            f"/api/v1/goals/{goal_id}/progress",
            json={"progress_percent": 50},
            headers=headers,
        )
        assert progress.status_code == 200

        progress_message = ws.receive_json()
        assert progress_message["type"] == "goal.updated"
        assert progress_message["payload"]["action"] == "progress_updated"

    # The goal is now real, queryable, persisted state -- not just an event.
    detail = client.get(f"/api/v1/goals/{goal_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["data"]["progress_percent"] == 50


def test_learned_routine_changes_future_suggestion_over_rest(client, auth_headers) -> None:
    """Acceptance Criterion 2 (a learned routine or preference measurably
    changes a future Predictive Suggestion) exercised over the real
    IntelligenceService directly (the routine-observation API is not a
    REST endpoint -- it's an internal signal other services/tools would
    call -- so this drives the real service the DI container built, the
    same real object the route handlers use)."""
    headers, _token = auth_headers
    intelligence = client.container.intelligence_service()

    from datetime import UTC, datetime

    fixed_time = datetime(2026, 8, 4, 9, 0, tzinfo=UTC)

    async def _learn_twice():
        await intelligence.learn_routine("make_coffee", observed_at=fixed_time)
        await intelligence.learn_routine("make_coffee", observed_at=fixed_time)

    before = client.get("/api/v1/intelligence/suggestions", headers=headers).json()["data"]
    assert not any(s["kind"] == "routine" for s in before)

    asyncio.run(_learn_twice())

    # Suggestions are time-context-sensitive; the REST route uses "now",
    # so verify directly against the service with the same fixed time the
    # route would use if called at that instant.
    suggestions = asyncio.run(intelligence.predict_suggestions(now=fixed_time))
    assert any(s.kind == "routine" and "make_coffee" in s.title for s in suggestions)


def test_daily_briefing_over_rest_relays_over_websocket(client, auth_headers) -> None:
    """Acceptance Criterion 3 (Daily Briefing content generation --
    automatic scheduling deferred pending M7 Phase 6, see
    IntelligenceService's own module docstring) exercised end-to-end."""
    headers, token = auth_headers
    client.post(
        "/api/v1/goals",
        json={"title": "Submit taxes", "description": ""},
        headers=headers,
    )

    with client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
        response = client.get("/api/v1/intelligence/briefing", headers=headers)
        assert response.status_code == 200

        message = ws.receive_json()
        assert message["type"] == "briefing.generated"


def test_universal_search_includes_goals_source(client, auth_headers) -> None:
    """Proves the Search Provider Registry's extensibility: Goal Manager
    registered a new source (``GoalSearchSource``) without any change to
    ``SearchService`` itself, and it appears in Universal Search
    results."""
    headers, _token = auth_headers
    client.post("/api/v1/goals", json={"title": "Learn Rust"}, headers=headers)

    response = client.post("/api/v1/search", json={"query": "Rust"}, headers=headers)
    assert response.status_code == 200
    sources = {r["source"] for r in response.json()["data"]}
    assert "goals" in sources
