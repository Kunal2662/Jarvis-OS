"""WorkspaceContextManager / WorkspaceRetriever tests -- Milestone 11
Task Group D.

The managers' contract is that they *coordinate* and never compute or
store. These assert both halves: every figure that reaches a context
section matches what the owning manager reports, and a missing or
failing collaborator costs a section rather than the whole call.

Real temp-file SQLite and the real Task Group A-C services throughout,
so "the context manager reads through the managers that own these
answers" is proved against the actual managers rather than a mock that
agrees with the assertion by construction.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from jarvis.core.events.event_bus import EventBus
from jarvis.core.exceptions import ServiceError
from jarvis.core.interfaces.search import SearchResult
from jarvis.services.calendar_service import CalendarService
from jarvis.services.file_managers import FileManager
from jarvis.services.file_service import FileService
from jarvis.services.productivity_managers import (
    CalendarManager,
    ReminderManager,
    TaskManager,
)
from jarvis.services.reminder_service import ReminderService
from jarvis.services.task_service import TaskService
from jarvis.services.workspace_ai_managers import (
    GLOBAL_SOURCES,
    WorkspaceContextManager,
    WorkspaceRetriever,
)
from jarvis.services.workspace_service import WorkspaceService


def _settings(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JARVIS_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'jarvis.db'}")

    from jarvis.core.config import settings as settings_mod

    settings_mod.load_settings.cache_clear()  # type: ignore[attr-defined]
    return settings_mod.load_settings()


class _Env:
    def __init__(self, db, bus, root: Path) -> None:
        self.workspaces = WorkspaceService(database=db, event_bus=bus)
        self.tasks = TaskService(database=db, workspace_service=self.workspaces, event_bus=bus)
        self.calendar = CalendarService(
            database=db, workspace_service=self.workspaces, event_bus=bus
        )
        self.reminders = ReminderService(
            database=db, workspace_service=self.workspaces, event_bus=bus
        )
        self.files = FileService(database=db, storage_root=root, event_bus=bus)
        self.task_manager = TaskManager(self.tasks)
        self.calendar_manager = CalendarManager(self.calendar)
        self.reminder_manager = ReminderManager(self.reminders)
        self.file_manager = FileManager(self.files)

    def context_manager(self, **overrides) -> WorkspaceContextManager:
        options = {
            "task_manager": self.task_manager,
            "task_service": self.tasks,
            "calendar_manager": self.calendar_manager,
            "reminder_manager": self.reminder_manager,
            "file_manager": self.file_manager,
        }
        options.update(overrides)
        return WorkspaceContextManager(self.workspaces, **options)

    def retriever(self, **overrides) -> WorkspaceRetriever:
        options = {
            "calendar_service": self.calendar,
            "task_service": self.tasks,
            "file_service": self.files,
        }
        options.update(overrides)
        return WorkspaceRetriever(self.workspaces, **options)


@pytest.fixture
async def env(tmp_path: Path, monkeypatch):
    settings = _settings(tmp_path, monkeypatch)
    from jarvis.infrastructure.database.sqlite_client import SQLiteDatabase

    db = SQLiteDatabase(settings.db)
    await db.initialize()
    root = tmp_path / "storage"
    root.mkdir()
    try:
        yield _Env(db, EventBus(), root)
    finally:
        await db.dispose()


class _Links:
    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self.rows = (
            rows
            if rows is not None
            else [
                {
                    "id": "e1",
                    "name": "Ada",
                    "entity_type": "person",
                    "description": "a colleague",
                    "link_count": 3,
                    "confidence": 0.9,
                    "uri": "knowledge://entity/e1",
                }
            ]
        )

    async def entities_for(self, workspace_id: str, *, limit: int = 50):
        return self.rows[:limit]


class _Knowledge:
    async def search(self, query: str, *, top_k: int = 10) -> list[SearchResult]:
        return [
            SearchResult(
                id="k1",
                title=f"entity for {query}",
                content="",
                source="knowledge",
                score=1.0,
                uri="knowledge://entity/k1",
            )
        ]


class _Memory:
    async def recall(self, query: str, *, top_k: int = 10):
        from types import SimpleNamespace

        return [SimpleNamespace(id="m1", content=f"memory of {query}")]


class _Broken:
    async def agenda(self, *args, **kwargs):
        raise RuntimeError("subsystem down")

    async def due_digest(self, **kwargs):
        raise RuntimeError("subsystem down")

    async def overview(self, *args, **kwargs):
        raise RuntimeError("subsystem down")

    async def entities_for(self, *args, **kwargs):
        raise RuntimeError("subsystem down")

    async def search(self, *args, **kwargs):
        raise RuntimeError("subsystem down")

    async def recall(self, *args, **kwargs):
        raise RuntimeError("subsystem down")


# --- context assembly -----------------------------------------------------------


@pytest.mark.asyncio
async def test_context_covers_every_wired_subsystem(env) -> None:
    workspace = await env.workspaces.create_workspace("Research", description="the migration")
    await env.workspaces.create_project(workspace.id, "Phase 1")
    await env.workspaces.create_note(workspace.id, "Standup", content="we discussed it")
    await env.tasks.create_task(workspace.id, "Write it up")
    calendar = await env.calendar.create_calendar(workspace.id, "Work")
    await env.calendar.create_event(calendar.id, "Kickoff", datetime.now(UTC) + timedelta(days=1))
    await env.reminders.create_reminder(
        workspace.id, "Nudge", datetime.now(UTC) - timedelta(hours=1)
    )
    await env.files.create_file(workspace.id, "notes.md", b"hello")

    context = await env.context_manager(knowledge_links=_Links(), memory_service=_Memory()).context(
        workspace.id
    )

    named = {section.name for section in context.sections if section.items}
    assert named == {
        "workspace",
        "projects",
        "tasks",
        "calendar",
        "reminders",
        "notes",
        "files",
        "knowledge",
        "memories",
    }


@pytest.mark.asyncio
async def test_context_carries_the_workspace_identity(env) -> None:
    workspace = await env.workspaces.create_workspace("Research", description="papers")

    context = await env.context_manager().context(workspace.id)

    assert context.workspace_id == workspace.id
    assert context.workspace_name == "Research"
    assert "Research" in context.render()


@pytest.mark.asyncio
async def test_context_of_an_unknown_workspace_raises(env) -> None:
    """A caller error, unlike a missing collaborator."""
    with pytest.raises(ServiceError, match="does not exist"):
        await env.context_manager().context("nope")


@pytest.mark.asyncio
async def test_task_numbers_match_the_manager_that_owns_them(env) -> None:
    """Collected, not recomputed. If these disagree, the context manager
    has grown its own idea of what is overdue."""
    workspace = await env.workspaces.create_workspace("Research")
    await env.tasks.create_task(
        workspace.id, "Late one", due_at=datetime.now(UTC) - timedelta(days=2)
    )
    await env.tasks.create_task(
        workspace.id, "Soon one", due_at=datetime.now(UTC) + timedelta(days=1)
    )

    context = await env.context_manager().context(workspace.id)
    agenda = await env.task_manager.agenda(workspace.id)

    rendered = context.section("tasks").render()  # type: ignore[union-attr]
    assert len(agenda["overdue"]) == 1
    assert "[OVERDUE] Late one" in rendered
    assert "[due soon] Soon one" in rendered


@pytest.mark.asyncio
async def test_a_task_with_no_due_date_still_reaches_the_context(env) -> None:
    """Most tasks have no due date, and the agenda's overdue/due-soon
    split puts them in neither bucket. Without the plain listing the
    assistant would be told a workspace has one task and shown none of
    them."""
    workspace = await env.workspaces.create_workspace("Research")
    await env.tasks.create_task(workspace.id, "Book the room")

    context = await env.context_manager().context(workspace.id)

    assert "[open] Book the room" in context.section("tasks").render()  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_a_dated_task_is_not_listed_twice(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")
    await env.tasks.create_task(
        workspace.id, "Late one", due_at=datetime.now(UTC) - timedelta(days=2)
    )

    rendered = (await env.context_manager().context(workspace.id)).section("tasks").render()  # type: ignore[union-attr]

    assert rendered.count("Late one") == 1
    assert "[OVERDUE] Late one" in rendered


@pytest.mark.asyncio
async def test_finished_tasks_do_not_spend_the_budget(env) -> None:
    """``done`` and ``cancelled`` are history; telling a model what is
    already finished is the wrong use of a bounded context."""
    workspace = await env.workspaces.create_workspace("Research")
    task = await env.tasks.create_task(workspace.id, "Already shipped")
    await env.tasks.update_task(task.id, status="done")

    rendered = (await env.context_manager().context(workspace.id)).section("tasks").render()  # type: ignore[union-attr]

    assert "Already shipped" not in rendered


@pytest.mark.asyncio
async def test_open_tasks_are_skipped_without_the_task_service(env) -> None:
    """The manager still degrades: the agenda half survives, the plain
    listing does not."""
    workspace = await env.workspaces.create_workspace("Research")
    await env.tasks.create_task(workspace.id, "Book the room")

    context = await env.context_manager(task_service=None).context(workspace.id)

    assert "Book the room" not in context.section("tasks").render()  # type: ignore[union-attr]
    assert "Task counts" in context.section("tasks").render()  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_calendar_occurrences_come_from_the_calendar_manager(env) -> None:
    """Recurrence expansion has one implementation, and it is not here."""
    from jarvis.domain.productivity.models import RecurrenceRule

    workspace = await env.workspaces.create_workspace("Research")
    calendar = await env.calendar.create_calendar(workspace.id, "Work")
    await env.calendar.create_event(
        calendar.id,
        "Standup",
        datetime.now(UTC) + timedelta(hours=1),
        recurrence=RecurrenceRule(frequency="daily", interval=1),
    )

    context = await env.context_manager().context(workspace.id)

    section = context.section("calendar")
    assert section is not None
    assert section.total > 1  # the rule expanded, rather than one stored row
    assert "Standup" in section.render()


@pytest.mark.asyncio
async def test_file_totals_come_from_the_file_manager(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")
    await env.files.create_file(workspace.id, "notes.md", b"hello world")

    context = await env.context_manager().context(workspace.id)
    overview = await env.file_manager.overview(workspace.id)

    rendered = context.section("files").render()  # type: ignore[union-attr]
    assert f"{overview['file_count']} file(s)" in rendered
    assert "notes.md" in rendered


@pytest.mark.asyncio
async def test_active_projects_outrank_archived_ones(env) -> None:
    """Under budget pressure the archived project is what should go."""
    workspace = await env.workspaces.create_workspace("Research")
    archived = await env.workspaces.create_project(workspace.id, "Old")
    await env.workspaces.update_project(archived.id, status="archived")
    await env.workspaces.create_project(workspace.id, "New")

    context = await env.context_manager().context(workspace.id)

    titles = [item.title for item in context.section("projects").items]  # type: ignore[union-attr]
    assert titles == ["New", "Old"]


@pytest.mark.asyncio
async def test_linked_knowledge_wins_over_a_text_match(env) -> None:
    """A link was produced by this workspace's own text; a text match
    merely shares a word with its name."""
    workspace = await env.workspaces.create_workspace("Research")

    context = await env.context_manager(
        knowledge_links=_Links(), knowledge_service=_Knowledge()
    ).context(workspace.id)

    rendered = context.section("knowledge").render()  # type: ignore[union-attr]
    assert "Ada" in rendered
    assert "entity for" not in rendered


@pytest.mark.asyncio
async def test_text_matching_still_answers_when_nothing_is_linked_yet(env) -> None:
    """A brand-new workspace has produced nothing, and reporting nothing
    would make it look unrelated to everything."""
    workspace = await env.workspaces.create_workspace("Research")

    context = await env.context_manager(
        knowledge_links=_Links(rows=[]), knowledge_service=_Knowledge()
    ).context(workspace.id)

    assert "entity for" in context.section("knowledge").render()  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_context_respects_a_caller_supplied_budget(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")
    for index in range(20):
        await env.workspaces.create_note(workspace.id, f"Note {index}", content="x" * 400)

    context = await env.context_manager().context(workspace.id, budget_chars=400)

    assert context.used_chars <= 400
    assert "notes" in context.truncated_sections


@pytest.mark.asyncio
async def test_section_item_caps_bound_the_work_before_packing(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")
    for index in range(30):
        await env.workspaces.create_note(workspace.id, f"Note {index}")

    context = await env.context_manager(section_items=3).context(workspace.id)

    notes = context.section("notes")
    assert notes is not None
    assert notes.total == 30
    assert len(notes.items) <= 3


# --- degradation ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_unwired_subsystem_costs_its_section_only(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")
    await env.workspaces.create_note(workspace.id, "Standup")

    context = await WorkspaceContextManager(env.workspaces).context(workspace.id)

    assert context.section("tasks").items == ()  # type: ignore[union-attr]
    assert context.section("notes").items  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_a_failing_subsystem_costs_its_section_not_the_call(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")
    broken = _Broken()

    context = await env.context_manager(
        task_manager=broken,
        calendar_manager=broken,
        reminder_manager=broken,
        file_manager=broken,
        knowledge_links=broken,
        knowledge_service=broken,
        memory_service=broken,
    ).context(workspace.id)

    assert context.workspace_name == "Research"
    for name in ("tasks", "calendar", "reminders", "files", "knowledge", "memories"):
        assert context.section(name).items == ()  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_the_context_manager_persists_nothing(env) -> None:
    """It is a read-side coordinator. Calling it twice must leave the
    domain exactly as it was."""
    workspace = await env.workspaces.create_workspace("Stable")
    await env.workspaces.create_note(workspace.id, "N")
    before = (await env.workspaces.metadata(workspace.id)).as_dict()

    manager = env.context_manager()
    for _ in range(2):
        await manager.context(workspace.id)

    assert (await env.workspaces.metadata(workspace.id)).as_dict() == before


# --- retrieval ------------------------------------------------------------------


class _Search:
    def __init__(self, results: list[SearchResult]) -> None:
        self.results = results
        self.calls: list[tuple[str, int]] = []

    async def search(self, query: str, *, top_k: int = 20) -> list[SearchResult]:
        self.calls.append((query, top_k))
        return self.results


def _result(source: str, identifier: str, **metadata) -> SearchResult:
    return SearchResult(
        id=identifier,
        title=identifier,
        content="",
        source=source,
        score=1.0,
        metadata=metadata,
    )


@pytest.mark.asyncio
async def test_retrieval_prefers_the_shared_search_service(env) -> None:
    """So a hit is ranked against every other source before being
    narrowed, rather than through a second ranking only this domain
    sees."""
    workspace = await env.workspaces.create_workspace("Research")
    shared = _Search([_result("notes", "n1", workspace_id=workspace.id)])

    results = await env.retriever(search_service=shared).retrieve(workspace.id, "anything")

    assert shared.calls[0][0] == "anything"
    assert [r.id for r in results] == ["n1"]


@pytest.mark.asyncio
async def test_retrieval_over_fetches_because_it_filters_after_ranking(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")
    shared = _Search([])

    await env.retriever(search_service=shared, overfetch=4).retrieve(workspace.id, "q", top_k=5)

    assert shared.calls[0][1] == 20


@pytest.mark.asyncio
async def test_another_workspaces_results_are_excluded(env) -> None:
    """A scoped search leaking another workspace's note is a
    privacy-shaped bug."""
    mine = await env.workspaces.create_workspace("Mine")
    theirs = await env.workspaces.create_workspace("Theirs")
    shared = _Search(
        [
            _result("notes", "mine", workspace_id=mine.id),
            _result("notes", "theirs", workspace_id=theirs.id),
        ]
    )

    results = await env.retriever(search_service=shared).retrieve(mine.id, "q")

    assert [r.id for r in results] == ["mine"]


@pytest.mark.asyncio
async def test_the_workspace_row_itself_is_in_scope(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")
    shared = _Search([_result("workspaces", workspace.id)])

    results = await env.retriever(search_service=shared).retrieve(workspace.id, "research")

    assert [r.id for r in results] == [workspace.id]


@pytest.mark.asyncio
async def test_a_calendar_event_is_scoped_through_its_calendar(env) -> None:
    """An event carries no workspace id -- Task Group B put it on the
    calendar deliberately -- so the join happens once per retrieval."""
    workspace = await env.workspaces.create_workspace("Research")
    calendar = await env.calendar.create_calendar(workspace.id, "Work")
    shared = _Search(
        [
            _result("calendar", "mine", kind="event", calendar_id=calendar.id),
            _result("calendar", "theirs", kind="event", calendar_id="other-calendar"),
        ]
    )

    results = await env.retriever(search_service=shared).retrieve(workspace.id, "q")

    assert [r.id for r in results] == ["mine"]


@pytest.mark.asyncio
async def test_events_are_excluded_when_no_calendar_service_is_wired(env) -> None:
    """ "I could not tell" resolves to "not this workspace", never to a
    guess."""
    workspace = await env.workspaces.create_workspace("Research")
    shared = _Search([_result("calendar", "e1", kind="event", calendar_id="c1")])

    retriever = WorkspaceRetriever(env.workspaces, search_service=shared)

    assert await retriever.retrieve(workspace.id, "q") == []


@pytest.mark.asyncio
async def test_global_sources_are_out_by_default_and_in_on_request(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")
    shared = _Search([_result(source, source) for source in sorted(GLOBAL_SOURCES)])
    retriever = env.retriever(search_service=shared)

    assert await retriever.retrieve(workspace.id, "q") == []
    included = await retriever.retrieve(workspace.id, "q", include_global=True)
    assert {r.source for r in included} == set(GLOBAL_SOURCES)


@pytest.mark.asyncio
async def test_an_unplaceable_result_is_excluded(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")
    shared = _Search([_result("mystery", "x")])

    assert await env.retriever(search_service=shared).retrieve(workspace.id, "q") == []


@pytest.mark.asyncio
async def test_results_are_returned_highest_score_first(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")
    low = _result("notes", "low", workspace_id=workspace.id)
    high = SearchResult(
        id="high",
        title="high",
        content="",
        source="notes",
        score=9.0,
        metadata={"workspace_id": workspace.id},
    )
    shared = _Search([low, high])

    results = await env.retriever(search_service=shared).retrieve(workspace.id, "q")

    assert [r.id for r in results] == ["high", "low"]


@pytest.mark.asyncio
async def test_retrieval_respects_top_k(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")
    shared = _Search([_result("notes", f"n{i}", workspace_id=workspace.id) for i in range(10)])

    results = await env.retriever(search_service=shared).retrieve(workspace.id, "q", top_k=3)

    assert len(results) == 3


@pytest.mark.asyncio
async def test_retrieval_falls_back_to_the_domain_services(env) -> None:
    """Narrower without a SearchService, never wrong -- the same contract
    every manager since Task Group A has used."""
    workspace = await env.workspaces.create_workspace("Quantum research")
    await env.workspaces.create_note(workspace.id, "Quantum note")
    await env.tasks.create_task(workspace.id, "Quantum task")

    results = await env.retriever().retrieve(workspace.id, "quantum")

    assert {r.source for r in results} >= {"notes", "tasks"}
    assert all(r.metadata.get("workspace_id") in (workspace.id, None) for r in results)


@pytest.mark.asyncio
async def test_the_fallback_still_excludes_other_workspaces(env) -> None:
    mine = await env.workspaces.create_workspace("Quantum mine")
    theirs = await env.workspaces.create_workspace("Quantum theirs")
    await env.workspaces.create_note(mine.id, "Quantum note")
    await env.workspaces.create_note(theirs.id, "Quantum note")

    results = await env.retriever().retrieve(mine.id, "quantum")

    assert all(r.metadata.get("workspace_id") == mine.id or r.id == mine.id for r in results)


@pytest.mark.asyncio
async def test_retrieving_in_an_unknown_workspace_raises(env) -> None:
    with pytest.raises(ServiceError, match="does not exist"):
        await env.retriever().retrieve("nope", "q")


@pytest.mark.asyncio
async def test_an_empty_query_retrieves_nothing(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")
    shared = _Search([_result("notes", "n1", workspace_id=workspace.id)])

    assert await env.retriever(search_service=shared).retrieve(workspace.id, "  ") == []
    assert shared.calls == []
