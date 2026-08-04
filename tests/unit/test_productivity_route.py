"""Productivity REST tests -- Milestone 11 Task Group B.

Against the real FastAPI app and the real DI container, matching
``test_workspaces_route.py``.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

_NOW = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)


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


@pytest.fixture
def workspace_id(client, auth) -> str:
    return client.post("/api/v1/workspaces", json={"name": "W"}, headers=auth).json()["data"]["id"]


def _calendar(client, auth, workspace_id: str, name: str = "C") -> str:
    return client.post(
        "/api/v1/calendar/calendars",
        json={"workspace_id": workspace_id, "name": name},
        headers=auth,
    ).json()["data"]["id"]


# --- Auth + envelope ------------------------------------------------------------


def test_every_collection_requires_a_session(client) -> None:
    for path in ("/api/v1/tasks", "/api/v1/calendar/events", "/api/v1/reminders"):
        assert client.get(path).status_code in (401, 403)


def test_responses_use_the_documented_envelope(client, auth, workspace_id) -> None:
    created = client.post(
        "/api/v1/tasks", json={"workspace_id": workspace_id, "title": "T"}, headers=auth
    )
    listed = client.get("/api/v1/tasks", headers=auth)

    for response in (created, listed):
        assert set(response.json()) == {"data", "meta"}
    assert created.json()["meta"]["created"] is True
    assert listed.json()["meta"]["count"] == 1


# --- Tasks ----------------------------------------------------------------------


def test_task_crud_round_trip(client, auth, workspace_id) -> None:
    task_id = client.post(
        "/api/v1/tasks",
        json={"workspace_id": workspace_id, "title": "Draft", "tags": ["Work", "work"]},
        headers=auth,
    ).json()["data"]["id"]

    fetched = client.get(f"/api/v1/tasks/{task_id}", headers=auth).json()["data"]
    assert fetched["tags"] == ["work"]  # normalized on write

    patched = client.patch(
        f"/api/v1/tasks/{task_id}", json={"status": "done"}, headers=auth
    ).json()["data"]
    assert patched["status"] == "done"
    assert patched["completed_at"] is not None

    assert client.delete(f"/api/v1/tasks/{task_id}", headers=auth).status_code == 204
    assert client.get(f"/api/v1/tasks/{task_id}", headers=auth).status_code == 404


def test_invalid_task_input_is_400(client, auth, workspace_id) -> None:
    assert (
        client.post(
            "/api/v1/tasks", json={"workspace_id": workspace_id, "title": "  "}, headers=auth
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/v1/tasks",
            json={"workspace_id": "nope", "title": "Orphan"},
            headers=auth,
        ).status_code
        == 400
    )
    assert client.get("/api/v1/tasks", params={"status": "doing"}, headers=auth).status_code == 400


def test_task_agenda_route_beats_the_id_route(client, auth, workspace_id) -> None:
    """``/tasks/agenda`` is declared before ``/tasks/{task_id}``; if the
    order ever flips, this asks for a task literally named "agenda"."""
    client.post(
        "/api/v1/tasks",
        json={
            "workspace_id": workspace_id,
            "title": "Overdue",
            "due_at": (_NOW - timedelta(days=400)).isoformat(),
        },
        headers=auth,
    )

    response = client.get(
        "/api/v1/tasks/agenda", params={"workspace_id": workspace_id}, headers=auth
    )

    assert response.status_code == 200
    assert len(response.json()["data"]["overdue"]) == 1


def test_task_context_route(client, auth, workspace_id) -> None:
    task_id = client.post(
        "/api/v1/tasks", json={"workspace_id": workspace_id, "title": "T"}, headers=auth
    ).json()["data"]["id"]

    data = client.get(f"/api/v1/tasks/{task_id}/context", headers=auth).json()["data"]

    assert set(data) >= {"task", "workspace", "related_knowledge", "related_memories"}


# --- Calendar -------------------------------------------------------------------


def test_calendar_and_event_crud(client, auth, workspace_id) -> None:
    calendar_id = _calendar(client, auth, workspace_id)
    event_id = client.post(
        "/api/v1/calendar/events",
        json={"calendar_id": calendar_id, "title": "Standup", "starts_at": _NOW.isoformat()},
        headers=auth,
    ).json()["data"]["id"]

    patched = client.patch(
        f"/api/v1/calendar/events/{event_id}",
        json={"category": "meeting", "location": "Room 1"},
        headers=auth,
    ).json()["data"]
    assert patched["category"] == "meeting"

    assert client.delete(f"/api/v1/calendar/events/{event_id}", headers=auth).status_code == 204
    assert (
        client.delete(f"/api/v1/calendar/calendars/{calendar_id}", headers=auth).status_code == 204
    )


def test_invalid_event_input_is_400(client, auth, workspace_id) -> None:
    calendar_id = _calendar(client, auth, workspace_id)

    backwards = client.post(
        "/api/v1/calendar/events",
        json={
            "calendar_id": calendar_id,
            "title": "Backwards",
            "starts_at": _NOW.isoformat(),
            "ends_at": (_NOW - timedelta(hours=1)).isoformat(),
        },
        headers=auth,
    )
    bad_rule = client.post(
        "/api/v1/calendar/events",
        json={
            "calendar_id": calendar_id,
            "title": "E",
            "starts_at": _NOW.isoformat(),
            "recurrence": {"frequency": "hourly"},
        },
        headers=auth,
    )

    assert backwards.status_code == 400
    assert bad_rule.status_code == 400


def test_occurrences_expand_the_stored_rule(client, auth, workspace_id) -> None:
    calendar_id = _calendar(client, auth, workspace_id)
    client.post(
        "/api/v1/calendar/events",
        json={
            "calendar_id": calendar_id,
            "title": "Daily",
            "starts_at": _NOW.isoformat(),
            "recurrence": {"frequency": "daily", "count": 10},
        },
        headers=auth,
    )

    response = client.get(
        "/api/v1/calendar/occurrences",
        params={
            "window_start": _NOW.isoformat(),
            "window_end": (_NOW + timedelta(days=4)).isoformat(),
            "workspace_id": workspace_id,
        },
        headers=auth,
    )

    # One stored row, five occurrences in the window.
    assert len(client.get("/api/v1/calendar/events", headers=auth).json()["data"]) == 1
    assert response.json()["meta"]["count"] == 5


def test_setting_a_new_default_calendar_clears_the_old_one(client, auth, workspace_id) -> None:
    first = client.post(
        "/api/v1/calendar/calendars",
        json={"workspace_id": workspace_id, "name": "One", "is_default": True},
        headers=auth,
    ).json()["data"]["id"]
    second = _calendar(client, auth, workspace_id, "Two")

    client.patch(f"/api/v1/calendar/calendars/{second}", json={"is_default": True}, headers=auth)

    defaults = {
        c["id"]: c["is_default"]
        for c in client.get(
            "/api/v1/calendar/calendars", params={"workspace_id": workspace_id}, headers=auth
        ).json()["data"]
    }
    assert defaults[second] is True
    assert defaults[first] is False


# --- Reminders ------------------------------------------------------------------


def test_reminder_crud_round_trip(client, auth, workspace_id) -> None:
    reminder_id = client.post(
        "/api/v1/reminders",
        json={"workspace_id": workspace_id, "title": "Ping", "remind_at": _NOW.isoformat()},
        headers=auth,
    ).json()["data"]["id"]

    patched = client.patch(
        f"/api/v1/reminders/{reminder_id}", json={"status": "dismissed"}, headers=auth
    ).json()["data"]
    assert patched["status"] == "dismissed"

    assert client.delete(f"/api/v1/reminders/{reminder_id}", headers=auth).status_code == 204


def test_a_reminder_cannot_target_both_a_task_and_an_event(client, auth, workspace_id) -> None:
    task_id = client.post(
        "/api/v1/tasks", json={"workspace_id": workspace_id, "title": "T"}, headers=auth
    ).json()["data"]["id"]
    calendar_id = _calendar(client, auth, workspace_id)
    event_id = client.post(
        "/api/v1/calendar/events",
        json={"calendar_id": calendar_id, "title": "E", "starts_at": _NOW.isoformat()},
        headers=auth,
    ).json()["data"]["id"]

    response = client.post(
        "/api/v1/reminders",
        json={
            "workspace_id": workspace_id,
            "title": "R",
            "remind_at": _NOW.isoformat(),
            "task_id": task_id,
            "event_id": event_id,
        },
        headers=auth,
    )

    assert response.status_code == 400


def test_due_endpoint_reports_and_delivers_nothing(client, auth, workspace_id) -> None:
    """The scope boundary, asserted at the HTTP surface: calling this
    must not mark anything sent."""
    reminder_id = client.post(
        "/api/v1/reminders",
        json={
            "workspace_id": workspace_id,
            "title": "Overdue",
            "remind_at": (_NOW - timedelta(days=400)).isoformat(),
        },
        headers=auth,
    ).json()["data"]["id"]

    data = client.get("/api/v1/reminders/due", headers=auth).json()["data"]

    assert [row["id"] for row in data["due"]] == [reminder_id]
    assert data["delivered"] is False
    assert "Scheduler" in data["detail"]
    # Untouched by the read.
    after = client.get(f"/api/v1/reminders/{reminder_id}", headers=auth).json()["data"]
    assert after["status"] == "pending"


def test_due_route_beats_the_id_route(client, auth) -> None:
    assert client.get("/api/v1/reminders/due", headers=auth).status_code == 200


def test_missing_rows_are_404(client, auth) -> None:
    assert client.get("/api/v1/tasks/nope", headers=auth).status_code == 404
    assert client.get("/api/v1/calendar/events/nope", headers=auth).status_code == 404
    assert client.get("/api/v1/reminders/nope", headers=auth).status_code == 404
    assert client.delete("/api/v1/tasks/nope", headers=auth).status_code == 404
