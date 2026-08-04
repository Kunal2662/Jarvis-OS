"""Task / Calendar / Reminder service tests -- Milestone 11 Task Group B.

Real temp-file SQLite throughout, matching ``test_workspace_service.py``
-- these are the repository tests too, because a repository mocked away
from its own dialect proves nothing about the queries that run.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from jarvis.core.events.event_bus import EventBus
from jarvis.core.events.events import (
    CalendarEventUpdatedEvent,
    CalendarUpdatedEvent,
    ReminderUpdatedEvent,
    TaskUpdatedEvent,
)
from jarvis.core.exceptions import ServiceError
from jarvis.domain.productivity.models import RecurrenceRule
from jarvis.services.calendar_service import CalendarService
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
    def __init__(self, db, bus) -> None:
        self.bus = bus
        self.events: list[object] = []
        for event_type in (
            TaskUpdatedEvent,
            CalendarUpdatedEvent,
            CalendarEventUpdatedEvent,
            ReminderUpdatedEvent,
        ):
            bus.subscribe(event_type, lambda e: self.events.append(e) or None)
        self.workspaces = WorkspaceService(database=db, event_bus=bus)
        self.tasks = TaskService(database=db, workspace_service=self.workspaces, event_bus=bus)
        self.calendar = CalendarService(
            database=db, workspace_service=self.workspaces, event_bus=bus
        )
        self.reminders = ReminderService(
            database=db, workspace_service=self.workspaces, event_bus=bus
        )

    def actions(self) -> list[tuple[str, str]]:
        return [(type(e).__name__, e.action) for e in self.events]


@pytest.fixture
async def env(tmp_path: Path, monkeypatch):
    settings = _settings(tmp_path, monkeypatch)
    from jarvis.infrastructure.database.sqlite_client import SQLiteDatabase

    db = SQLiteDatabase(settings.db)
    await db.initialize()
    try:
        yield _Env(db, EventBus())
    finally:
        await db.dispose()


async def _workspace(env: _Env, name: str = "W") -> str:
    return (await env.workspaces.create_workspace(name)).id


# ================================================================= Tasks


@pytest.mark.asyncio
async def test_task_crud_round_trip(env: _Env) -> None:
    workspace_id = await _workspace(env)

    task = await env.tasks.create_task(
        workspace_id, "Write report", priority="high", tags=["Work", "work "]
    )

    assert task.status == "todo"
    assert task.priority == "high"
    # Tags normalized on write, so a filter is a plain equality check.
    assert await env.tasks.tags_for(task.id) == ["work"]

    updated = await env.tasks.update_task(task.id, title="Write final report")
    assert updated is not None
    assert updated.title == "Write final report"

    assert await env.tasks.delete_task(task.id) is True
    assert await env.tasks.get_task(task.id) is None


@pytest.mark.asyncio
async def test_a_task_needs_a_real_workspace(env: _Env) -> None:
    """Checked in the service so the caller gets a clear message rather
    than an IntegrityError from three layers down."""
    with pytest.raises(ServiceError, match="does not exist"):
        await env.tasks.create_task("nope", "Orphan")


@pytest.mark.asyncio
async def test_empty_title_and_unknown_vocabulary_are_rejected(env: _Env) -> None:
    workspace_id = await _workspace(env)

    with pytest.raises(ServiceError, match="empty title"):
        await env.tasks.create_task(workspace_id, "   ")
    with pytest.raises(ServiceError, match="Unknown task priority"):
        await env.tasks.create_task(workspace_id, "T", priority="critical")
    with pytest.raises(ServiceError, match="Unknown task status"):
        await env.tasks.list_tasks(status="doing")


@pytest.mark.asyncio
async def test_completing_a_task_stamps_completed_at(env: _Env) -> None:
    """``completed_at`` is derived from the transition, never set by the
    caller -- it is the one field that must agree with ``status``."""
    workspace_id = await _workspace(env)
    task = await env.tasks.create_task(workspace_id, "T")

    done = await env.tasks.complete_task(task.id)
    assert done is not None
    assert done.status == "done"
    assert done.completed_at is not None

    reopened = await env.tasks.update_task(task.id, status="todo")
    assert reopened is not None
    assert reopened.completed_at is None


@pytest.mark.asyncio
async def test_clear_due_is_distinct_from_leave_alone(env: _Env) -> None:
    workspace_id = await _workspace(env)
    task = await env.tasks.create_task(workspace_id, "T", due_at=_NOW)

    untouched = await env.tasks.update_task(task.id, title="T2")
    assert untouched is not None
    assert untouched.due_at is not None

    cleared = await env.tasks.update_task(task.id, clear_due=True)
    assert cleared is not None
    assert cleared.due_at is None


@pytest.mark.asyncio
async def test_tasks_list_dated_before_undated(env: _Env) -> None:
    """SQLite would sort NULLs first, burying every dated task under
    every undated one."""
    workspace_id = await _workspace(env)
    await env.tasks.create_task(workspace_id, "No date")
    dated = await env.tasks.create_task(workspace_id, "Dated", due_at=_NOW)

    assert (await env.tasks.list_tasks(workspace_id=workspace_id))[0].id == dated.id


@pytest.mark.asyncio
async def test_tag_filter_matches_whole_tags(env: _Env) -> None:
    """A LIKE against the serialized JSON would match "work" inside
    "homework"."""
    workspace_id = await _workspace(env)
    await env.tasks.create_task(workspace_id, "A", tags=["work"])
    await env.tasks.create_task(workspace_id, "B", tags=["homework"])

    assert [t.title for t in await env.tasks.list_tasks(tag="work")] == ["A"]


@pytest.mark.asyncio
async def test_due_before_excludes_closed_tasks(env: _Env) -> None:
    """A completed task is not "due"."""
    workspace_id = await _workspace(env)
    open_task = await env.tasks.create_task(workspace_id, "Open", due_at=_NOW - timedelta(days=1))
    closed = await env.tasks.create_task(workspace_id, "Closed", due_at=_NOW - timedelta(days=1))
    await env.tasks.complete_task(closed.id)

    due = await env.tasks.due_before(_NOW, workspace_id=workspace_id)

    assert [t.id for t in due] == [open_task.id]


@pytest.mark.asyncio
async def test_status_counts_include_the_zeroes(env: _Env) -> None:
    """So a caller rendering a summary does not have to know the
    vocabulary to fill them in."""
    workspace_id = await _workspace(env)
    await env.tasks.create_task(workspace_id, "T")

    counts = await env.tasks.status_counts(workspace_id)

    assert counts == {"cancelled": 0, "done": 0, "in_progress": 0, "todo": 1}


@pytest.mark.asyncio
async def test_task_search_ranks_open_and_urgent_higher(env: _Env) -> None:
    workspace_id = await _workspace(env)
    urgent = await env.tasks.create_task(workspace_id, "keyword urgent", priority="urgent")
    low = await env.tasks.create_task(workspace_id, "keyword low", priority="low")
    cancelled = await env.tasks.create_task(workspace_id, "keyword cancelled")
    await env.tasks.update_task(cancelled.id, status="cancelled")

    results = await env.tasks.search("keyword")
    scores = {r.id: r.score for r in results}

    assert scores[urgent.id] > scores[low.id] > scores[cancelled.id]
    assert [r.source for r in results] == ["tasks"] * 3


@pytest.mark.asyncio
async def test_empty_query_returns_nothing(env: _Env) -> None:
    workspace_id = await _workspace(env)
    await env.tasks.create_task(workspace_id, "Anything")

    assert await env.tasks.search("  ") == []


# ============================================================== Calendar


@pytest.mark.asyncio
async def test_calendar_and_event_crud(env: _Env) -> None:
    workspace_id = await _workspace(env)
    calendar = await env.calendar.create_calendar(workspace_id, "Work", color="#123456")

    event = await env.calendar.create_event(calendar.id, "Standup", _NOW)

    assert event.category == "general"
    assert await env.calendar.delete_event(event.id) is True
    assert await env.calendar.delete_calendar(calendar.id) is True


@pytest.mark.asyncio
async def test_only_one_default_calendar_per_workspace(env: _Env) -> None:
    workspace_id = await _workspace(env)
    first = await env.calendar.create_calendar(workspace_id, "One", is_default=True)
    second = await env.calendar.create_calendar(workspace_id, "Two", is_default=True)

    calendars = {
        c.id: c.is_default for c in await env.calendar.list_calendars(workspace_id=workspace_id)
    }

    assert calendars[second.id] is True
    assert calendars[first.id] is False


@pytest.mark.asyncio
async def test_default_calendar_is_created_lazily(env: _Env) -> None:
    """Task Group A's WorkspaceService should not have to know this task
    group exists, and a workspace nobody schedules in needs no calendar
    row."""
    workspace_id = await _workspace(env)
    assert await env.calendar.list_calendars(workspace_id=workspace_id) == []

    created = await env.calendar.ensure_default_calendar(workspace_id)
    again = await env.calendar.ensure_default_calendar(workspace_id)

    assert created.id == again.id
    assert created.is_default is True


@pytest.mark.asyncio
async def test_an_event_cannot_end_before_it_starts(env: _Env) -> None:
    workspace_id = await _workspace(env)
    calendar = await env.calendar.create_calendar(workspace_id, "C")

    with pytest.raises(ServiceError, match="end before it starts"):
        await env.calendar.create_event(
            calendar.id, "Backwards", _NOW, ends_at=_NOW - timedelta(hours=1)
        )


@pytest.mark.asyncio
async def test_unknown_category_and_bad_recurrence_are_rejected(env: _Env) -> None:
    workspace_id = await _workspace(env)
    calendar = await env.calendar.create_calendar(workspace_id, "C")

    with pytest.raises(ServiceError, match="Unknown event category"):
        await env.calendar.create_event(calendar.id, "E", _NOW, category="wedding")
    with pytest.raises(ServiceError, match="Unknown recurrence frequency"):
        await env.calendar.create_event(
            calendar.id, "E", _NOW, recurrence=RecurrenceRule(frequency="hourly")
        )


@pytest.mark.asyncio
async def test_recurrence_is_stored_as_a_rule_not_expanded_rows(env: _Env) -> None:
    """A yearly event must not write 100 rows: editing the series would
    then have to find and rewrite all of them."""
    workspace_id = await _workspace(env)
    calendar = await env.calendar.create_calendar(workspace_id, "C")

    await env.calendar.create_event(
        calendar.id, "Daily", _NOW, recurrence=RecurrenceRule(frequency="daily", count=30)
    )

    stored = await env.calendar.list_events(calendar_id=calendar.id)
    assert len(stored) == 1
    assert (await env.calendar.recurrence_of(stored[0].id)).count == 30


@pytest.mark.asyncio
async def test_events_filter_by_workspace_through_the_calendar(env: _Env) -> None:
    """No denormalized ``workspace_id`` on the event -- the join is what
    keeps one source of truth."""
    one = await _workspace(env, "One")
    two = await _workspace(env, "Two")
    cal_one = await env.calendar.create_calendar(one, "A")
    cal_two = await env.calendar.create_calendar(two, "B")
    await env.calendar.create_event(cal_one.id, "In one", _NOW)
    await env.calendar.create_event(cal_two.id, "In two", _NOW)

    assert [e.title for e in await env.calendar.list_events(workspace_id=one)] == ["In one"]


@pytest.mark.asyncio
async def test_deleting_a_calendar_takes_its_events(env: _Env) -> None:
    """Unlike deleting a project, which keeps its notes: an event with
    no calendar is not "unfiled", it is meaningless."""
    workspace_id = await _workspace(env)
    calendar = await env.calendar.create_calendar(workspace_id, "C")
    event = await env.calendar.create_event(calendar.id, "Doomed", _NOW)

    await env.calendar.delete_calendar(calendar.id)

    assert await env.calendar.get_event(event.id) is None


@pytest.mark.asyncio
async def test_calendar_search_returns_events_and_calendars(env: _Env) -> None:
    workspace_id = await _workspace(env)
    calendar = await env.calendar.create_calendar(workspace_id, "Standup calendar")
    await env.calendar.create_event(calendar.id, "Standup meeting", _NOW)

    kinds = {r.metadata["kind"] for r in await env.calendar.search("standup")}

    assert kinds == {"event", "calendar"}


# ============================================================= Reminders


@pytest.mark.asyncio
async def test_reminder_crud_and_status_transitions(env: _Env) -> None:
    workspace_id = await _workspace(env)
    reminder = await env.reminders.create_reminder(workspace_id, "Ping", _NOW)

    assert reminder.status == "pending"
    dismissed = await env.reminders.dismiss(reminder.id)
    assert dismissed is not None
    assert dismissed.status == "dismissed"

    cancelled = await env.reminders.cancel(reminder.id)
    assert cancelled is not None
    assert cancelled.status == "cancelled"

    assert await env.reminders.delete_reminder(reminder.id) is True


@pytest.mark.asyncio
async def test_a_reminder_targets_a_task_or_an_event_not_both(env: _Env) -> None:
    """Both would make "what is this about" depend on which one a
    renderer checked first."""
    workspace_id = await _workspace(env)
    task = await env.tasks.create_task(workspace_id, "T")
    calendar = await env.calendar.create_calendar(workspace_id, "C")
    event = await env.calendar.create_event(calendar.id, "E", _NOW)

    with pytest.raises(ServiceError, match="not both"):
        await env.reminders.create_reminder(
            workspace_id, "R", _NOW, task_id=task.id, event_id=event.id
        )


@pytest.mark.asyncio
async def test_due_before_reports_and_changes_nothing(env: _Env) -> None:
    """The boundary this whole task group is scoped by: asking which
    reminders are due must not deliver, mark, or mutate any of them."""
    workspace_id = await _workspace(env)
    reminder = await env.reminders.create_reminder(
        workspace_id, "Overdue", _NOW - timedelta(hours=1)
    )

    due = await env.reminders.due_before(_NOW, workspace_id=workspace_id)

    assert [r.id for r in due] == [reminder.id]
    # Still pending afterwards -- nothing fired.
    assert (await env.reminders.require_reminder(reminder.id)).status == "pending"


@pytest.mark.asyncio
async def test_due_before_ignores_non_pending_reminders(env: _Env) -> None:
    workspace_id = await _workspace(env)
    reminder = await env.reminders.create_reminder(
        workspace_id, "Handled", _NOW - timedelta(hours=1)
    )
    await env.reminders.dismiss(reminder.id)

    assert await env.reminders.due_before(_NOW, workspace_id=workspace_id) == []


@pytest.mark.asyncio
async def test_next_occurrence_is_computed_from_the_stored_rule(env: _Env) -> None:
    """Answering "when next" without a scheduler is exactly the metadata
    this task group is scoped to provide."""
    workspace_id = await _workspace(env)
    reminder = await env.reminders.create_reminder(
        workspace_id, "Weekly", _NOW, recurrence=RecurrenceRule(frequency="weekly", count=4)
    )

    following = await env.reminders.next_occurrence_after(reminder.id, _NOW)

    assert following == _NOW + timedelta(weeks=1)


@pytest.mark.asyncio
async def test_a_passed_one_shot_has_no_next_occurrence(env: _Env) -> None:
    workspace_id = await _workspace(env)
    reminder = await env.reminders.create_reminder(workspace_id, "Once", _NOW)

    assert await env.reminders.next_occurrence_after(reminder.id, _NOW) is None


@pytest.mark.asyncio
async def test_reminder_search_ranks_pending_above_history(env: _Env) -> None:
    workspace_id = await _workspace(env)
    pending = await env.reminders.create_reminder(workspace_id, "keyword live", _NOW)
    done = await env.reminders.create_reminder(workspace_id, "keyword old", _NOW)
    await env.reminders.dismiss(done.id)

    scores = {r.id: r.score for r in await env.reminders.search("keyword")}

    assert scores[pending.id] > scores[done.id]


# ================================================================ Events


@pytest.mark.asyncio
async def test_every_mutation_publishes_its_event(env: _Env) -> None:
    workspace_id = await _workspace(env)
    env.events.clear()

    task = await env.tasks.create_task(workspace_id, "T")
    await env.tasks.complete_task(task.id)
    calendar = await env.calendar.create_calendar(workspace_id, "C")
    event = await env.calendar.create_event(calendar.id, "E", _NOW)
    await env.calendar.delete_event(event.id)
    reminder = await env.reminders.create_reminder(workspace_id, "R", _NOW)
    await env.reminders.dismiss(reminder.id)
    await env.tasks.delete_task(task.id)

    assert env.actions() == [
        ("TaskUpdatedEvent", "created"),
        ("TaskUpdatedEvent", "completed"),
        ("CalendarUpdatedEvent", "created"),
        ("CalendarEventUpdatedEvent", "created"),
        ("CalendarEventUpdatedEvent", "deleted"),
        ("ReminderUpdatedEvent", "created"),
        ("ReminderUpdatedEvent", "dismissed"),
        ("TaskUpdatedEvent", "deleted"),
    ]


@pytest.mark.asyncio
async def test_events_carry_their_parent_ids(env: _Env) -> None:
    """So a subscriber scoped to one workspace can filter without a
    lookup."""
    workspace_id = await _workspace(env)
    calendar = await env.calendar.create_calendar(workspace_id, "C")
    env.events.clear()

    await env.calendar.create_event(calendar.id, "E", _NOW)

    published = env.events[0]
    assert published.calendar_id == calendar.id  # type: ignore[attr-defined]
    assert published.workspace_id == workspace_id  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_a_failed_mutation_publishes_nothing(env: _Env) -> None:
    env.events.clear()

    assert await env.tasks.delete_task("nope") is False
    assert await env.reminders.update_reminder("nope", title="x") is None
    assert await env.calendar.delete_event("nope") is False

    assert env.events == []


@pytest.mark.asyncio
async def test_services_work_without_an_event_bus(tmp_path: Path, monkeypatch) -> None:
    """Events are optional wiring, the same contract every other service
    in this repository has."""
    settings = _settings(tmp_path, monkeypatch)
    from jarvis.infrastructure.database.sqlite_client import SQLiteDatabase

    db = SQLiteDatabase(settings.db)
    await db.initialize()
    try:
        workspaces = WorkspaceService(database=db)
        workspace = await workspaces.create_workspace("Quiet")
        tasks = TaskService(database=db, workspace_service=workspaces)
        assert (await tasks.create_task(workspace.id, "T")).title == "T"
    finally:
        await db.dispose()


@pytest.mark.asyncio
async def test_deleting_a_task_takes_its_reminders(env: _Env) -> None:
    """A reminder about a task that no longer exists is noise, not
    content -- unlike a note, which outlives its project.

    This cascade runs through the ORM relationship, not the foreign
    key: SQLite ignores ``ON DELETE`` unless ``PRAGMA foreign_keys=ON``
    is set and this application never sets it. See ``Workspace``'s
    relationship block in ``models.py``.
    """
    workspace_id = await _workspace(env)
    task = await env.tasks.create_task(workspace_id, "T")
    reminder = await env.reminders.create_reminder(
        workspace_id, "About the task", _NOW, task_id=task.id
    )

    await env.tasks.delete_task(task.id)

    assert await env.reminders.get_reminder(reminder.id) is None


@pytest.mark.asyncio
async def test_deleting_a_workspace_takes_the_whole_productivity_tree(env: _Env) -> None:
    workspace_id = await _workspace(env)
    task = await env.tasks.create_task(workspace_id, "T")
    calendar = await env.calendar.create_calendar(workspace_id, "C")
    event = await env.calendar.create_event(calendar.id, "E", _NOW)
    reminder = await env.reminders.create_reminder(workspace_id, "R", _NOW)

    assert await env.workspaces.delete_workspace(workspace_id) is True

    assert await env.tasks.get_task(task.id) is None
    assert await env.calendar.get_event(event.id) is None
    assert await env.calendar.get_calendar(calendar.id) is None
    assert await env.reminders.get_reminder(reminder.id) is None
