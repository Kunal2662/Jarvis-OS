"""Productivity Core end-to-end -- Milestone 11 Task Group B.

Real DI container, real REST app, real EventBus, real
``RuntimeWebSocketHub``. The unit tests prove each piece; this proves
they are wired to each other -- REST writes reach WebSocket subscribers,
the three new search sources joined the *shared* registry, and the
Workspace substrate Task Group A shipped actually holds this task
group's data.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
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
    onto the productivity domain."""
    headers, token = auth
    now = datetime.now(UTC)
    workspace_id = client.post("/api/v1/workspaces", json={"name": "W"}, headers=headers).json()[
        "data"
    ]["id"]

    with client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
        client.post(
            "/api/v1/tasks", json={"workspace_id": workspace_id, "title": "T"}, headers=headers
        )
        calendar_id = client.post(
            "/api/v1/calendar/calendars",
            json={"workspace_id": workspace_id, "name": "C"},
            headers=headers,
        ).json()["data"]["id"]
        client.post(
            "/api/v1/calendar/events",
            json={"calendar_id": calendar_id, "title": "E", "starts_at": now.isoformat()},
            headers=headers,
        )
        client.post(
            "/api/v1/reminders",
            json={"workspace_id": workspace_id, "title": "R", "remind_at": now.isoformat()},
            headers=headers,
        )

        received = [ws.receive_json() for _ in range(4)]

    assert [frame["type"] for frame in received] == [
        "task.updated",
        "calendar.updated",
        "calendar.event_updated",
        "reminder.updated",
    ]
    assert received[0]["payload"]["workspace_id"] == workspace_id
    assert received[2]["payload"]["calendar_id"] == calendar_id


def test_the_three_sources_join_the_shared_search_service(client) -> None:
    """Registered through M10A's provider registry with no change to
    ``SearchService`` itself."""
    sources = {s.source_type for s in client.container.search_service().get_sources()}

    assert {"tasks", "calendar", "reminders"} <= sources
    # Task Group A's three are still there -- this is additive.
    assert {"workspaces", "projects", "notes"} <= sources


def test_productivity_content_is_findable_through_universal_search(client, auth) -> None:
    headers, _ = auth
    now = datetime.now(UTC)
    workspace_id = client.post("/api/v1/workspaces", json={"name": "W"}, headers=headers).json()[
        "data"
    ]["id"]
    client.post(
        "/api/v1/tasks",
        json={"workspace_id": workspace_id, "title": "Quantum task"},
        headers=headers,
    )
    calendar_id = client.post(
        "/api/v1/calendar/calendars",
        json={"workspace_id": workspace_id, "name": "Quantum calendar"},
        headers=headers,
    ).json()["data"]["id"]
    client.post(
        "/api/v1/calendar/events",
        json={"calendar_id": calendar_id, "title": "Quantum sync", "starts_at": now.isoformat()},
        headers=headers,
    )
    client.post(
        "/api/v1/reminders",
        json={
            "workspace_id": workspace_id,
            "title": "Quantum reminder",
            "remind_at": now.isoformat(),
        },
        headers=headers,
    )

    results = asyncio.run(client.container.search_service().search("quantum", top_k=30))

    assert {"tasks", "calendar", "reminders"} <= {r.source for r in results}


def test_productivity_data_hangs_off_the_workspace_substrate(client, auth) -> None:
    """Task Group A shipped the container precisely so B did not have to
    invent one: deleting the workspace takes the whole tree."""
    headers, _ = auth
    now = datetime.now(UTC)
    workspace_id = client.post("/api/v1/workspaces", json={"name": "W"}, headers=headers).json()[
        "data"
    ]["id"]
    task_id = client.post(
        "/api/v1/tasks", json={"workspace_id": workspace_id, "title": "T"}, headers=headers
    ).json()["data"]["id"]
    calendar_id = client.post(
        "/api/v1/calendar/calendars",
        json={"workspace_id": workspace_id, "name": "C"},
        headers=headers,
    ).json()["data"]["id"]
    event_id = client.post(
        "/api/v1/calendar/events",
        json={"calendar_id": calendar_id, "title": "E", "starts_at": now.isoformat()},
        headers=headers,
    ).json()["data"]["id"]
    reminder_id = client.post(
        "/api/v1/reminders",
        json={"workspace_id": workspace_id, "title": "R", "remind_at": now.isoformat()},
        headers=headers,
    ).json()["data"]["id"]

    assert client.delete(f"/api/v1/workspaces/{workspace_id}", headers=headers).status_code == 204

    assert client.get(f"/api/v1/tasks/{task_id}", headers=headers).status_code == 404
    assert client.get(f"/api/v1/calendar/events/{event_id}", headers=headers).status_code == 404
    assert client.get(f"/api/v1/reminders/{reminder_id}", headers=headers).status_code == 404


def test_a_task_can_be_filed_under_a_project(client, auth) -> None:
    """The Workspace -> Project -> Task chain, through the real API."""
    headers, _ = auth
    workspace_id = client.post("/api/v1/workspaces", json={"name": "W"}, headers=headers).json()[
        "data"
    ]["id"]
    project_id = client.post(
        "/api/v1/projects", json={"workspace_id": workspace_id, "name": "P"}, headers=headers
    ).json()["data"]["id"]

    task = client.post(
        "/api/v1/tasks",
        json={"workspace_id": workspace_id, "title": "T", "project_id": project_id},
        headers=headers,
    ).json()["data"]

    assert task["project_id"] == project_id
    filtered = client.get("/api/v1/tasks", params={"project_id": project_id}, headers=headers)
    assert filtered.json()["meta"]["count"] == 1


def test_di_exposes_one_singleton_per_service_and_manager(client) -> None:
    container = client.container

    for name in (
        "task_service",
        "calendar_service",
        "reminder_service",
        "task_manager",
        "calendar_manager",
        "reminder_manager",
    ):
        provider = getattr(container, name)
        assert provider() is provider(), name


def test_managers_read_the_containers_own_services(client, auth) -> None:
    """So the REST routes and the managers can never disagree about what
    exists."""
    headers, _ = auth
    container = client.container
    workspace_id = client.post("/api/v1/workspaces", json={"name": "W"}, headers=headers).json()[
        "data"
    ]["id"]
    client.post(
        "/api/v1/tasks",
        json={"workspace_id": workspace_id, "title": "Visible"},
        headers=headers,
    )

    agenda = asyncio.run(container.task_manager().agenda(workspace_id))

    assert agenda["status_counts"]["todo"] == 1


def test_nothing_in_this_task_group_fires_a_reminder(client, auth) -> None:
    """The scope boundary, asserted end to end: an overdue reminder
    stays ``pending`` no matter how many read paths observe it. Delivery
    is M7's Scheduler (Phase 6)."""
    headers, _ = auth
    workspace_id = client.post("/api/v1/workspaces", json={"name": "W"}, headers=headers).json()[
        "data"
    ]["id"]
    reminder_id = client.post(
        "/api/v1/reminders",
        json={
            "workspace_id": workspace_id,
            "title": "Overdue",
            "remind_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
        },
        headers=headers,
    ).json()["data"]["id"]

    for _ in range(3):
        client.get("/api/v1/reminders/due", headers=headers)
        client.get(f"/api/v1/reminders/{reminder_id}/context", headers=headers)
        asyncio.run(client.container.reminder_manager().due_digest())

    assert (
        client.get(f"/api/v1/reminders/{reminder_id}", headers=headers).json()["data"]["status"]
        == "pending"
    )
