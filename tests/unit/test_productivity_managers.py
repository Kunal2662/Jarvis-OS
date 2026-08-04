"""Productivity manager tests -- Milestone 11 Task Group B.

Each manager's contract is the one ``WorkspaceManager`` established:
collect, never compute; persist nothing; degrade rather than fail when
a collaborator is missing or broken.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from jarvis.core.events.event_bus import EventBus
from jarvis.core.exceptions import ServiceError
from jarvis.core.interfaces.search import SearchResult
from jarvis.domain.productivity.models import RecurrenceRule
from jarvis.services.calendar_service import CalendarService
from jarvis.services.productivity_managers import (
    CalendarManager,
    ReminderManager,
    TaskManager,
)
from jarvis.services.reminder_service import ReminderService
from jarvis.services.task_service import TaskService
from jarvis.services.workspace_service import WorkspaceService

_NOW = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)


def _settings(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JARVIS_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'jarvis.db'}")

    from jarvis.core.config import settings as settings_mod

    settings_mod.load_settings.cache_clear()  # type: ignore[attr-defined]
    return settings_mod.load_settings()


class _Env:
    def __init__(self, db) -> None:
        bus = EventBus()
        self.workspaces = WorkspaceService(database=db, event_bus=bus)
        self.tasks = TaskService(database=db, workspace_service=self.workspaces, event_bus=bus)
        self.calendar = CalendarService(
            database=db, workspace_service=self.workspaces, event_bus=bus
        )
        self.reminders = ReminderService(
            database=db, workspace_service=self.workspaces, event_bus=bus
        )


@pytest.fixture
async def env(tmp_path: Path, monkeypatch):
    settings = _settings(tmp_path, monkeypatch)
    from jarvis.infrastructure.database.sqlite_client import SQLiteDatabase

    db = SQLiteDatabase(settings.db)
    await db.initialize()
    try:
        yield _Env(db)
    finally:
        await db.dispose()


class _Knowledge:
    async def search(self, query: str, *, top_k: int = 10) -> list[SearchResult]:
        return [SearchResult(id="k1", title="entity", content="", source="knowledge", score=1.0)]


class _Memory:
    async def recall(self, query: str, *, top_k: int = 10):
        from types import SimpleNamespace

        return [SimpleNamespace(id="m1", content="memory")]


class _Broken:
    async def search(self, query: str, *, top_k: int = 10):
        raise RuntimeError("index unavailable")

    async def recall(self, query: str, *, top_k: int = 10):
        raise RuntimeError("vector store down")


# --- TaskManager ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_agenda_separates_overdue_from_due_soon(env: _Env) -> None:
    """A task cannot be in both buckets -- otherwise a caller rendering
    both would show it twice."""
    workspace = await env.workspaces.create_workspace("W")
    overdue = await env.tasks.create_task(workspace.id, "Overdue", due_at=_NOW - timedelta(days=1))
    soon = await env.tasks.create_task(workspace.id, "Soon", due_at=_NOW + timedelta(days=2))
    await env.tasks.create_task(workspace.id, "Later", due_at=_NOW + timedelta(days=30))

    agenda = await TaskManager(env.tasks).agenda(workspace.id, now=_NOW)

    assert [t["id"] for t in agenda["overdue"]] == [overdue.id]
    assert [t["id"] for t in agenda["due_soon"]] == [soon.id]


@pytest.mark.asyncio
async def test_agenda_counts_match_the_owning_service(env: _Env) -> None:
    """Collected, not recomputed."""
    workspace = await env.workspaces.create_workspace("W")
    await env.tasks.create_task(workspace.id, "T")

    agenda = await TaskManager(env.tasks).agenda(workspace.id, now=_NOW)

    assert agenda["status_counts"] == await env.tasks.status_counts(workspace.id)


@pytest.mark.asyncio
async def test_agenda_takes_an_injected_clock(env: _Env) -> None:
    """So a caller (and a test) can ask what Tuesday looked like."""
    workspace = await env.workspaces.create_workspace("W")
    await env.tasks.create_task(workspace.id, "Future", due_at=_NOW + timedelta(days=3))

    past = await TaskManager(env.tasks).agenda(workspace.id, now=_NOW - timedelta(days=30))
    present = await TaskManager(env.tasks).agenda(workspace.id, now=_NOW)

    assert past["due_soon"] == []
    assert len(present["due_soon"]) == 1


@pytest.mark.asyncio
async def test_task_context_adds_the_neighbours(env: _Env) -> None:
    workspace = await env.workspaces.create_workspace("W")
    task = await env.tasks.create_task(workspace.id, "Quantum notes")
    manager = TaskManager(
        env.tasks,
        workspace_service=env.workspaces,
        knowledge_service=_Knowledge(),
        memory_service=_Memory(),
    )

    context = await manager.context(task.id)

    assert context["task"]["id"] == task.id
    assert context["workspace"]["name"] == "W"
    assert context["related_knowledge"][0]["id"] == "k1"
    assert context["related_memories"][0]["id"] == "m1"


@pytest.mark.asyncio
async def test_a_failing_collaborator_costs_context_not_the_call(env: _Env) -> None:
    workspace = await env.workspaces.create_workspace("W")
    task = await env.tasks.create_task(workspace.id, "T")
    broken = _Broken()

    context = await TaskManager(env.tasks, knowledge_service=broken, memory_service=broken).context(
        task.id
    )

    assert context["related_knowledge"] == []
    assert context["related_memories"] == []
    assert context["task"]["id"] == task.id


@pytest.mark.asyncio
async def test_task_manager_prefers_the_shared_search_service(env: _Env) -> None:
    class _Search:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def search(self, query: str, *, top_k: int = 10) -> list[SearchResult]:
            self.calls.append(query)
            return []

    shared = _Search()
    await TaskManager(env.tasks, search_service=shared).search("anything")

    assert shared.calls == ["anything"]


# --- CalendarManager ------------------------------------------------------------


@pytest.mark.asyncio
async def test_occurrences_expand_a_recurrence_into_the_window(env: _Env) -> None:
    """The capability no single service call provides, and the reason
    this manager exists: the repository can only filter on an event's
    *stored* start."""
    workspace = await env.workspaces.create_workspace("W")
    calendar = await env.calendar.create_calendar(workspace.id, "C")
    await env.calendar.create_event(
        calendar.id, "Standup", _NOW, recurrence=RecurrenceRule(frequency="daily", count=10)
    )

    rows = await CalendarManager(env.calendar).occurrences(
        window_start=_NOW, window_end=_NOW + timedelta(days=4), workspace_id=workspace.id
    )

    assert len(rows) == 5
    assert all(row["is_recurring"] for row in rows)
    assert rows == sorted(rows, key=lambda r: r["starts_at"])


@pytest.mark.asyncio
async def test_a_recurring_event_from_before_the_window_still_appears(env: _Env) -> None:
    """A weekly standup created in January is invisible to a March query
    until its rule is expanded -- which is exactly the bug this method
    exists to prevent."""
    workspace = await env.workspaces.create_workspace("W")
    calendar = await env.calendar.create_calendar(workspace.id, "C")
    await env.calendar.create_event(
        calendar.id,
        "Weekly",
        _NOW - timedelta(days=60),
        recurrence=RecurrenceRule(frequency="weekly", count=20),
    )

    rows = await CalendarManager(env.calendar).occurrences(
        window_start=_NOW, window_end=_NOW + timedelta(days=14), workspace_id=workspace.id
    )

    assert rows, "a recurrence starting before the window must still expand into it"


@pytest.mark.asyncio
async def test_a_one_off_outside_the_window_is_excluded(env: _Env) -> None:
    workspace = await env.workspaces.create_workspace("W")
    calendar = await env.calendar.create_calendar(workspace.id, "C")
    await env.calendar.create_event(calendar.id, "Long past", _NOW - timedelta(days=60))

    rows = await CalendarManager(env.calendar).occurrences(
        window_start=_NOW, window_end=_NOW + timedelta(days=7), workspace_id=workspace.id
    )

    assert rows == []


@pytest.mark.asyncio
async def test_calendar_agenda_includes_calendars_and_occurrences(env: _Env) -> None:
    workspace = await env.workspaces.create_workspace("W")
    calendar = await env.calendar.create_calendar(workspace.id, "C", is_default=True)
    await env.calendar.create_event(calendar.id, "Soon", _NOW + timedelta(days=1))

    agenda = await CalendarManager(env.calendar).agenda(workspace.id, now=_NOW)

    assert [c["name"] for c in agenda["calendars"]] == ["C"]
    assert len(agenda["occurrences"]) == 1


@pytest.mark.asyncio
async def test_event_context_reports_the_stored_rule(env: _Env) -> None:
    workspace = await env.workspaces.create_workspace("W")
    calendar = await env.calendar.create_calendar(workspace.id, "C")
    event = await env.calendar.create_event(
        calendar.id, "E", _NOW, recurrence=RecurrenceRule(frequency="weekly", count=3)
    )

    context = await CalendarManager(env.calendar).context(event.id)

    assert context["recurrence"]["frequency"] == "weekly"
    assert context["event"]["id"] == event.id


# --- ReminderManager ------------------------------------------------------------


@pytest.mark.asyncio
async def test_due_digest_reports_without_delivering(env: _Env) -> None:
    """The boundary this task group is scoped by, asserted at the
    manager level too: building the digest changes no status."""
    workspace = await env.workspaces.create_workspace("W")
    reminder = await env.reminders.create_reminder(workspace.id, "Ping", _NOW - timedelta(hours=1))

    digest = await ReminderManager(env.reminders).due_digest(now=_NOW)

    assert [row["id"] for row in digest["due"]] == [reminder.id]
    assert digest["delivered"] is False
    assert "Scheduler" in digest["detail"]
    assert (await env.reminders.require_reminder(reminder.id)).status == "pending"


@pytest.mark.asyncio
async def test_due_digest_resolves_a_task_target(env: _Env) -> None:
    workspace = await env.workspaces.create_workspace("W")
    task = await env.tasks.create_task(workspace.id, "Write report")
    await env.reminders.create_reminder(
        workspace.id, "Ping", _NOW - timedelta(hours=1), task_id=task.id
    )

    digest = await ReminderManager(env.reminders, task_service=env.tasks).due_digest(now=_NOW)

    assert digest["due"][0]["target"] == {
        "kind": "task",
        "id": task.id,
        "title": "Write report",
    }


@pytest.mark.asyncio
async def test_due_digest_resolves_an_event_target(env: _Env) -> None:
    workspace = await env.workspaces.create_workspace("W")
    calendar = await env.calendar.create_calendar(workspace.id, "C")
    event = await env.calendar.create_event(calendar.id, "Standup", _NOW)
    await env.reminders.create_reminder(
        workspace.id, "Ping", _NOW - timedelta(hours=1), event_id=event.id
    )

    digest = await ReminderManager(env.reminders, calendar_service=env.calendar).due_digest(
        now=_NOW
    )

    assert digest["due"][0]["target"]["kind"] == "event"


@pytest.mark.asyncio
async def test_an_unresolvable_target_yields_none_not_a_failure(env: _Env) -> None:
    """No task service wired: the digest still renders, with the target
    unresolved."""
    workspace = await env.workspaces.create_workspace("W")
    task = await env.tasks.create_task(workspace.id, "T")
    await env.reminders.create_reminder(
        workspace.id, "Ping", _NOW - timedelta(hours=1), task_id=task.id
    )

    digest = await ReminderManager(env.reminders).due_digest(now=_NOW)

    assert digest["due"][0]["target"] is None


@pytest.mark.asyncio
async def test_reminder_context_includes_the_next_occurrence(env: _Env) -> None:
    workspace = await env.workspaces.create_workspace("W")
    reminder = await env.reminders.create_reminder(
        workspace.id,
        "Weekly",
        _NOW + timedelta(days=1),
        recurrence=RecurrenceRule(frequency="weekly", count=5),
    )

    context = await ReminderManager(env.reminders).context(reminder.id)

    assert context["next_occurrence"] is not None


@pytest.mark.asyncio
async def test_context_of_an_unknown_reminder_raises(env: _Env) -> None:
    with pytest.raises(ServiceError, match="does not exist"):
        await ReminderManager(env.reminders).context("nope")


# --- Shared contract ------------------------------------------------------------


@pytest.mark.asyncio
async def test_managers_persist_nothing(env: _Env) -> None:
    """Every read, twice, with the domain captured either side."""
    workspace = await env.workspaces.create_workspace("W")
    task = await env.tasks.create_task(workspace.id, "T", due_at=_NOW)
    calendar = await env.calendar.create_calendar(workspace.id, "C")
    event = await env.calendar.create_event(calendar.id, "E", _NOW)
    reminder = await env.reminders.create_reminder(workspace.id, "R", _NOW)

    before = (
        [t.id for t in await env.tasks.list_tasks()],
        [e.id for e in await env.calendar.list_events()],
        [r.status for r in await env.reminders.list_reminders()],
    )

    for _ in range(2):
        await TaskManager(env.tasks).agenda(workspace.id, now=_NOW)
        await TaskManager(env.tasks).context(task.id)
        await CalendarManager(env.calendar).occurrences(
            window_start=_NOW, window_end=_NOW + timedelta(days=7)
        )
        await CalendarManager(env.calendar).context(event.id)
        await ReminderManager(env.reminders).due_digest(now=_NOW)
        await ReminderManager(env.reminders).context(reminder.id)

    assert (
        [t.id for t in await env.tasks.list_tasks()],
        [e.id for e in await env.calendar.list_events()],
        [r.status for r in await env.reminders.list_reminders()],
    ) == before
