"""WorkspaceService tests -- Milestone 11 Task Group A.

Real (temp-file) SQLite throughout, matching
``test_intelligence_service.py``'s established pattern -- these are the
repository tests as well as the service tests, because a repository
mocked away from its own dialect proves nothing about the queries that
actually run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core.events.event_bus import EventBus
from jarvis.core.events.events import (
    NoteUpdatedEvent,
    ProjectUpdatedEvent,
    WorkspaceUpdatedEvent,
)
from jarvis.core.exceptions import ServiceError
from jarvis.domain.workspace.models import WorkspaceSettings
from jarvis.services.workspace_service import WorkspaceService


def _settings(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JARVIS_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'jarvis.db'}")

    from jarvis.core.config import settings as settings_mod

    settings_mod.load_settings.cache_clear()  # type: ignore[attr-defined]
    return settings_mod.load_settings()


@pytest.fixture
async def service(tmp_path: Path, monkeypatch):
    settings = _settings(tmp_path, monkeypatch)
    from jarvis.infrastructure.database.sqlite_client import SQLiteDatabase

    db = SQLiteDatabase(settings.db)
    await db.initialize()
    try:
        yield WorkspaceService(database=db, event_bus=EventBus())
    finally:
        await db.dispose()


@pytest.fixture
async def recorder(tmp_path: Path, monkeypatch):
    """A service whose bus records every relayed workspace event."""
    settings = _settings(tmp_path, monkeypatch)
    from jarvis.infrastructure.database.sqlite_client import SQLiteDatabase

    db = SQLiteDatabase(settings.db)
    await db.initialize()
    bus = EventBus()
    seen: list[object] = []
    for event_type in (WorkspaceUpdatedEvent, ProjectUpdatedEvent, NoteUpdatedEvent):
        bus.subscribe(event_type, lambda e: seen.append(e) or None)
    try:
        yield WorkspaceService(database=db, event_bus=bus), seen
    finally:
        await db.dispose()


# --- Workspace lifecycle --------------------------------------------------------


@pytest.mark.asyncio
async def test_create_and_read_a_workspace(service: WorkspaceService) -> None:
    workspace = await service.create_workspace("Research", description="papers")

    assert workspace.name == "Research"
    assert workspace.status == "active"
    fetched = await service.get_workspace(workspace.id)
    assert fetched is not None
    assert fetched.description == "papers"


@pytest.mark.asyncio
async def test_empty_workspace_name_is_rejected(service: WorkspaceService) -> None:
    """Whitespace-only counts as empty -- a workspace named ' ' is
    indistinguishable from a mistake."""
    with pytest.raises(ServiceError, match="empty name"):
        await service.create_workspace("   ")


@pytest.mark.asyncio
async def test_list_filters_by_status(service: WorkspaceService) -> None:
    active = await service.create_workspace("Active")
    archived = await service.create_workspace("Archived")
    await service.update_workspace(archived.id, status="archived")

    assert [w.id for w in await service.list_workspaces(status="active")] == [active.id]
    assert [w.id for w in await service.list_workspaces(status="archived")] == [archived.id]
    assert len(await service.list_workspaces()) == 2


@pytest.mark.asyncio
async def test_unknown_status_is_rejected_rather_than_silently_matching_nothing(
    service: WorkspaceService,
) -> None:
    """A typo'd status would otherwise return an empty list, which reads
    as "no workspaces" rather than "you asked a nonsense question"."""
    with pytest.raises(ServiceError, match="Unknown workspace"):
        await service.list_workspaces(status="activ")


@pytest.mark.asyncio
async def test_partial_update_leaves_other_fields_alone(service: WorkspaceService) -> None:
    workspace = await service.create_workspace("Before", description="keep me")

    updated = await service.update_workspace(workspace.id, name="After")

    assert updated is not None
    assert updated.name == "After"
    assert updated.description == "keep me"


@pytest.mark.asyncio
async def test_update_and_delete_report_missing_rows(service: WorkspaceService) -> None:
    assert await service.update_workspace("nope", name="x") is None
    assert await service.delete_workspace("nope") is False


# --- Settings + metadata --------------------------------------------------------


@pytest.mark.asyncio
async def test_settings_round_trip(service: WorkspaceService) -> None:
    workspace = await service.create_workspace(
        "Themed", settings=WorkspaceSettings(color="#101820", icon="flask")
    )

    settings = await service.get_settings(workspace.id)

    assert settings.color == "#101820"
    assert settings.icon == "flask"


@pytest.mark.asyncio
async def test_malformed_settings_json_degrades_to_defaults(service: WorkspaceService) -> None:
    """Settings are read on every workspace load; one bad write must not
    make a workspace unopenable."""
    from jarvis.infrastructure.database.repositories import WorkspaceRepository

    workspace = await service.create_workspace("Broken")
    async with service._db.session() as sess:
        await WorkspaceRepository(sess).update(workspace.id, settings_json="{not json")

    assert (await service.get_settings(workspace.id)).color == ""


@pytest.mark.asyncio
async def test_metadata_is_derived_from_the_rows(service: WorkspaceService) -> None:
    workspace = await service.create_workspace("Counted")
    project = await service.create_project(workspace.id, "P1")
    await service.create_project(workspace.id, "P2")
    await service.update_project(project.id, status="completed")
    await service.create_note(workspace.id, "N1")

    metadata = await service.metadata(workspace.id)

    assert metadata.project_count == 2
    assert metadata.active_project_count == 1
    assert metadata.note_count == 1
    assert metadata.last_activity_at is not None


@pytest.mark.asyncio
async def test_metadata_for_an_unknown_workspace_raises(service: WorkspaceService) -> None:
    with pytest.raises(ServiceError, match="does not exist"):
        await service.metadata("nope")


# --- Projects -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_project_requires_an_existing_workspace(service: WorkspaceService) -> None:
    """Checked in the service so the caller gets a clear message rather
    than an IntegrityError from the foreign key."""
    with pytest.raises(ServiceError, match="does not exist"):
        await service.create_project("nope", "Orphan")


@pytest.mark.asyncio
async def test_projects_filter_by_workspace_and_status(service: WorkspaceService) -> None:
    one = await service.create_workspace("One")
    two = await service.create_workspace("Two")
    await service.create_project(one.id, "A")
    await service.create_project(two.id, "B")

    assert [p.name for p in await service.list_projects(workspace_id=one.id)] == ["A"]
    assert len(await service.list_projects()) == 2


@pytest.mark.asyncio
async def test_deleting_a_project_keeps_its_notes(service: WorkspaceService) -> None:
    """The ORM cascade would take them. A note is something the user
    wrote; losing a batch as a side effect of tidying a project is not a
    trade anyone would choose."""
    workspace = await service.create_workspace("W")
    project = await service.create_project(workspace.id, "P")
    note = await service.create_note(workspace.id, "Survivor", project_id=project.id)

    assert await service.delete_project(project.id) is True

    survivor = await service.get_note(note.id)
    assert survivor is not None
    assert survivor.project_id is None
    assert survivor.workspace_id == workspace.id


@pytest.mark.asyncio
async def test_deleting_a_workspace_does_cascade(service: WorkspaceService) -> None:
    """Unlike a project, deleting the container is an explicit "remove
    all of this" -- the cascade is the intent here."""
    workspace = await service.create_workspace("Doomed")
    await service.create_project(workspace.id, "P")
    note = await service.create_note(workspace.id, "N")

    assert await service.delete_workspace(workspace.id) is True

    assert await service.get_note(note.id) is None
    assert await service.list_projects(workspace_id=workspace.id) == []


# --- Notes ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_note_can_be_filed_against_the_workspace_alone(
    service: WorkspaceService,
) -> None:
    """The normal case, not an error -- a thought worth capturing rarely
    arrives already filed."""
    workspace = await service.create_workspace("W")

    note = await service.create_note(workspace.id, "Unfiled")

    assert note.project_id is None


@pytest.mark.asyncio
async def test_a_note_cannot_span_two_workspaces(service: WorkspaceService) -> None:
    one = await service.create_workspace("One")
    two = await service.create_workspace("Two")
    project = await service.create_project(two.id, "Elsewhere")

    with pytest.raises(ServiceError, match="different workspace"):
        await service.create_note(one.id, "Confused", project_id=project.id)


@pytest.mark.asyncio
async def test_clear_project_is_distinct_from_leave_alone(service: WorkspaceService) -> None:
    """``project_id=None`` already means "don't touch it" in this
    partial-update convention, so unfiling needs its own flag."""
    workspace = await service.create_workspace("W")
    project = await service.create_project(workspace.id, "P")
    note = await service.create_note(workspace.id, "N", project_id=project.id)

    untouched = await service.update_note(note.id, title="Renamed")
    assert untouched is not None
    assert untouched.project_id == project.id

    unfiled = await service.update_note(note.id, clear_project=True)
    assert unfiled is not None
    assert unfiled.project_id is None


@pytest.mark.asyncio
async def test_unknown_note_format_is_rejected(service: WorkspaceService) -> None:
    workspace = await service.create_workspace("W")

    with pytest.raises(ServiceError, match="Unknown note format"):
        await service.create_note(workspace.id, "N", content_format="rtf")


@pytest.mark.asyncio
async def test_notes_list_pinned_first(service: WorkspaceService) -> None:
    workspace = await service.create_workspace("W")
    await service.create_note(workspace.id, "Ordinary")
    pinned = await service.create_note(workspace.id, "Important")
    await service.update_note(pinned.id, pinned=True)

    assert (await service.list_notes(workspace_id=workspace.id))[0].id == pinned.id


# --- Search hooks ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_matches_across_the_three_entities(service: WorkspaceService) -> None:
    workspace = await service.create_workspace("Quantum research")
    await service.create_project(workspace.id, "Quantum error correction")
    await service.create_note(workspace.id, "Quantum notes", content="surface codes")

    assert [r.source for r in await service.search_workspaces("quantum")] == ["workspaces"]
    assert [r.source for r in await service.search_projects("quantum")] == ["projects"]
    assert [r.source for r in await service.search_notes("quantum")] == ["notes"]


@pytest.mark.asyncio
async def test_empty_query_returns_nothing_rather_than_everything(
    service: WorkspaceService,
) -> None:
    workspace = await service.create_workspace("Anything")
    await service.create_note(workspace.id, "Anything")

    assert await service.search_workspaces("  ") == []
    assert await service.search_notes("") == []


@pytest.mark.asyncio
async def test_a_title_match_outranks_a_body_match(service: WorkspaceService) -> None:
    workspace = await service.create_workspace("W")
    await service.create_note(workspace.id, "Buried", content="the keyword is in here")
    await service.create_note(workspace.id, "keyword in the title")

    results = await service.search_notes("keyword")

    assert results[0].title == "keyword in the title"


@pytest.mark.asyncio
async def test_pinning_boosts_a_note(service: WorkspaceService) -> None:
    workspace = await service.create_workspace("W")
    plain = await service.create_note(workspace.id, "keyword one")
    pinned = await service.create_note(workspace.id, "keyword two")
    await service.update_note(pinned.id, pinned=True)

    scores = {r.id: r.score for r in await service.search_notes("keyword")}

    assert scores[pinned.id] > scores[plain.id]


# --- Events ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_every_mutation_publishes_its_event(recorder) -> None:
    service, seen = recorder

    workspace = await service.create_workspace("W")
    project = await service.create_project(workspace.id, "P")
    note = await service.create_note(workspace.id, "N")
    await service.update_workspace(workspace.id, status="archived")
    await service.update_project(project.id, status="completed")
    await service.update_note(note.id, title="N2")
    await service.delete_note(note.id)

    assert [(type(e).__name__, e.action) for e in seen] == [
        ("WorkspaceUpdatedEvent", "created"),
        ("ProjectUpdatedEvent", "created"),
        ("NoteUpdatedEvent", "created"),
        ("WorkspaceUpdatedEvent", "archived"),
        ("ProjectUpdatedEvent", "completed"),
        ("NoteUpdatedEvent", "updated"),
        ("NoteUpdatedEvent", "deleted"),
    ]


@pytest.mark.asyncio
async def test_events_carry_their_parent_ids(recorder) -> None:
    """A subscriber scoped to one workspace can filter without a
    lookup."""
    service, seen = recorder

    workspace = await service.create_workspace("W")
    project = await service.create_project(workspace.id, "P")
    await service.create_note(workspace.id, "N", project_id=project.id)

    assert seen[1].workspace_id == workspace.id
    assert seen[2].workspace_id == workspace.id
    assert seen[2].project_id == project.id


@pytest.mark.asyncio
async def test_a_failed_mutation_publishes_nothing(recorder) -> None:
    service, seen = recorder

    assert await service.delete_workspace("nope") is False
    assert await service.update_note("nope", title="x") is None

    assert seen == []


@pytest.mark.asyncio
async def test_the_service_works_without_an_event_bus(tmp_path: Path, monkeypatch) -> None:
    """Events are optional wiring, not a requirement -- the same
    contract every other service in this repository has."""
    settings = _settings(tmp_path, monkeypatch)
    from jarvis.infrastructure.database.sqlite_client import SQLiteDatabase

    db = SQLiteDatabase(settings.db)
    await db.initialize()
    try:
        service = WorkspaceService(database=db)
        workspace = await service.create_workspace("Quiet")
        assert workspace.name == "Quiet"
    finally:
        await db.dispose()
