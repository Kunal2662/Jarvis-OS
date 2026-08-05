"""WorkspaceKnowledgeService tests -- Milestone 11 Task Group D.

Real temp-file SQLite throughout, matching ``test_file_services.py`` --
these are the repository tests too, because a repository mocked away
from its own dialect proves nothing about the queries that run, and the
foreign keys this table leans on are only real against a real database.

The knowledge graph is faked at the *extraction* boundary only: a fake
``KnowledgeService`` that writes real entity rows and reports their ids,
so the link table is exercised against genuine foreign keys while no
test needs an LLM.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core.events.event_bus import EventBus
from jarvis.core.events.events import WorkspaceKnowledgeLinkedEvent
from jarvis.core.exceptions import ServiceError
from jarvis.services.file_service import FileService
from jarvis.services.knowledge_service import ExtractionResult
from jarvis.services.task_service import TaskService
from jarvis.services.workspace_ai_service import (
    WorkspaceKnowledgeService,
    describe_link_target,
)
from jarvis.services.workspace_service import WorkspaceService


def _settings(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JARVIS_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'jarvis.db'}")

    from jarvis.core.config import settings as settings_mod

    settings_mod.load_settings.cache_clear()  # type: ignore[attr-defined]
    return settings_mod.load_settings()


class _FakeKnowledge:
    """Writes real ``knowledge_entities`` rows and reports their ids.

    Real rows rather than fabricated ids because foreign keys are
    enforced now (see ``fix: enforce SQLite foreign keys``): a link to an
    invented entity id must be refused, and a fake that returned one
    would be testing the fake rather than the schema.
    """

    def __init__(self, db) -> None:
        self._db = db
        self.calls: list[str] = []
        self.names: list[str] = ["Ada", "Migration"]

    async def learn_from_text(self, text: str, *, source_memory_id: str | None = None):
        from jarvis.infrastructure.database.repositories import KnowledgeRepository

        self.calls.append(text)
        ids: list[str] = []
        async with self._db.session() as sess:
            repo = KnowledgeRepository(sess)
            for name in self.names:
                existing = await repo.find_entity_by_name(name)
                entity = existing or await repo.add_entity(
                    name, entity_type="person", description=f"about {name}", confidence=0.8
                )
                ids.append(entity.id)
        return ExtractionResult(
            entities_created=len(ids), relationships_created=0, entity_ids=tuple(ids)
        )

    async def add_entity(self, name: str) -> str:
        from jarvis.infrastructure.database.repositories import KnowledgeRepository

        async with self._db.session() as sess:
            entity = await KnowledgeRepository(sess).add_entity(
                name, entity_type="topic", description="", confidence=0.5
            )
            return entity.id


class _Env:
    def __init__(self, db, bus, root: Path) -> None:
        self.bus = bus
        self.events: list[WorkspaceKnowledgeLinkedEvent] = []
        bus.subscribe(WorkspaceKnowledgeLinkedEvent, lambda e: self.events.append(e) or None)
        self.workspaces = WorkspaceService(database=db, event_bus=bus)
        self.tasks = TaskService(database=db, workspace_service=self.workspaces, event_bus=bus)
        self.files = FileService(database=db, storage_root=root, event_bus=bus)
        self.knowledge = _FakeKnowledge(db)
        self.links = WorkspaceKnowledgeService(
            database=db,
            knowledge_service=self.knowledge,  # type: ignore[arg-type]
            workspace_service=self.workspaces,
            file_service=self.files,
            event_bus=bus,
        )


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


# --- linking --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_link_records_a_workspace_entity_pair(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")
    entity_id = await env.knowledge.add_entity("Ada")

    link = await env.links.link(workspace.id, entity_id)

    assert link.workspace_id == workspace.id
    assert link.entity_id == entity_id
    assert describe_link_target(link) == ("workspace", workspace.id)


@pytest.mark.asyncio
async def test_link_to_a_note_sets_the_narrow_column(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")
    note = await env.workspaces.create_note(workspace.id, "Standup")
    entity_id = await env.knowledge.add_entity("Ada")

    link = await env.links.link(workspace.id, entity_id, target="note", target_id=note.id)

    assert link.note_id == note.id
    assert describe_link_target(link) == ("note", note.id)


@pytest.mark.asyncio
async def test_linking_the_same_pair_twice_is_idempotent(env) -> None:
    """Ingestion re-runs constantly; a link table that grew a row per run
    would be an audit log nobody asked for."""
    workspace = await env.workspaces.create_workspace("Research")
    entity_id = await env.knowledge.add_entity("Ada")

    first = await env.links.link(workspace.id, entity_id)
    second = await env.links.link(workspace.id, entity_id)

    assert first.id == second.id
    assert len(await env.links.list_links(workspace_id=workspace.id)) == 1


@pytest.mark.asyncio
async def test_a_manual_assertion_promotes_an_extracted_link(env) -> None:
    """A person saying "yes, this is about that" outranks an extractor
    guessing it, and a later re-ingestion must not be free to delete it."""
    workspace = await env.workspaces.create_workspace("Research")
    entity_id = await env.knowledge.add_entity("Ada")
    await env.links.link(workspace.id, entity_id, source="extracted", confidence=0.4)

    promoted = await env.links.link(workspace.id, entity_id, source="manual", confidence=0.9)

    assert promoted.source == "manual"
    assert promoted.confidence == 0.9


@pytest.mark.asyncio
async def test_a_manual_link_is_not_demoted_by_extraction(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")
    entity_id = await env.knowledge.add_entity("Ada")
    await env.links.link(workspace.id, entity_id, source="manual", confidence=0.9)

    again = await env.links.link(workspace.id, entity_id, source="extracted", confidence=0.1)

    assert again.source == "manual"
    assert again.confidence == 0.9


@pytest.mark.asyncio
async def test_the_same_entity_can_be_linked_to_two_different_targets(env) -> None:
    """ "This note is about Ada" and "this workspace is about Ada" are
    different claims, and the lookup must not collapse them."""
    workspace = await env.workspaces.create_workspace("Research")
    note = await env.workspaces.create_note(workspace.id, "Standup")
    entity_id = await env.knowledge.add_entity("Ada")

    await env.links.link(workspace.id, entity_id)
    await env.links.link(workspace.id, entity_id, target="note", target_id=note.id)

    assert len(await env.links.list_links(workspace_id=workspace.id)) == 2


@pytest.mark.asyncio
async def test_linking_a_fabricated_entity_is_refused_as_a_bad_request(env) -> None:
    """A foreign key would refuse it too, but as an IntegrityError that
    reaches the caller as a 500 -- the gap Task Group C closed for
    attachments."""
    workspace = await env.workspaces.create_workspace("Research")

    with pytest.raises(ServiceError, match="does not exist"):
        await env.links.link(workspace.id, "no-such-entity")


@pytest.mark.asyncio
async def test_linking_in_a_fabricated_workspace_is_refused(env) -> None:
    entity_id = await env.knowledge.add_entity("Ada")

    with pytest.raises(ServiceError, match="Workspace"):
        await env.links.link("no-such-workspace", entity_id)


@pytest.mark.asyncio
async def test_linking_a_target_from_another_workspace_is_refused(env) -> None:
    """The check a foreign key genuinely cannot make: a valid note id
    says nothing about the note being in *this* workspace."""
    first = await env.workspaces.create_workspace("First")
    second = await env.workspaces.create_workspace("Second")
    foreign_note = await env.workspaces.create_note(second.id, "Theirs")
    entity_id = await env.knowledge.add_entity("Ada")

    with pytest.raises(ServiceError, match="different workspace"):
        await env.links.link(first.id, entity_id, target="note", target_id=foreign_note.id)


@pytest.mark.asyncio
async def test_linking_a_fabricated_note_is_refused(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")
    entity_id = await env.knowledge.add_entity("Ada")

    with pytest.raises(ServiceError, match="does not exist"):
        await env.links.link(workspace.id, entity_id, target="note", target_id="nope")


@pytest.mark.asyncio
async def test_an_unknown_target_kind_is_rejected(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")
    entity_id = await env.knowledge.add_entity("Ada")

    with pytest.raises(ServiceError, match="Unknown link target"):
        await env.links.link(workspace.id, entity_id, target="event", target_id="x")


@pytest.mark.asyncio
async def test_an_unknown_source_is_rejected(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")
    entity_id = await env.knowledge.add_entity("Ada")

    with pytest.raises(ServiceError, match="Unknown link source"):
        await env.links.link(workspace.id, entity_id, source="telepathy")


@pytest.mark.asyncio
async def test_a_workspace_link_refuses_a_target_id(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")
    entity_id = await env.knowledge.add_entity("Ada")

    with pytest.raises(ServiceError, match="takes no target id"):
        await env.links.link(workspace.id, entity_id, target="workspace", target_id="x")


@pytest.mark.asyncio
async def test_a_narrow_link_requires_a_target_id(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")
    entity_id = await env.knowledge.add_entity("Ada")

    with pytest.raises(ServiceError, match="requires a target id"):
        await env.links.link(workspace.id, entity_id, target="task")


@pytest.mark.asyncio
async def test_linking_a_task_works_like_any_other_narrow_target(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")
    task = await env.tasks.create_task(workspace.id, "Write it up")
    entity_id = await env.knowledge.add_entity("Ada")

    link = await env.links.link(workspace.id, entity_id, target="task", target_id=task.id)

    assert describe_link_target(link) == ("task", task.id)


# --- listing and reading --------------------------------------------------------


@pytest.mark.asyncio
async def test_list_links_filters_by_target(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")
    note = await env.workspaces.create_note(workspace.id, "Standup")
    entity_id = await env.knowledge.add_entity("Ada")
    await env.links.link(workspace.id, entity_id)
    await env.links.link(workspace.id, entity_id, target="note", target_id=note.id)

    scoped = await env.links.list_links(workspace_id=workspace.id, target="note", target_id=note.id)

    assert [link.note_id for link in scoped] == [note.id]


@pytest.mark.asyncio
async def test_list_links_filters_by_source(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")
    first = await env.knowledge.add_entity("Ada")
    second = await env.knowledge.add_entity("Grace")
    await env.links.link(workspace.id, first, source="manual")
    await env.links.link(workspace.id, second, source="extracted")

    assert len(await env.links.list_links(workspace_id=workspace.id, source="manual")) == 1


@pytest.mark.asyncio
async def test_list_links_rejects_an_unknown_filter(env) -> None:
    with pytest.raises(ServiceError, match="Unknown link source"):
        await env.links.list_links(source="hunch")


@pytest.mark.asyncio
async def test_entities_for_reports_link_counts_most_linked_first(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")
    note = await env.workspaces.create_note(workspace.id, "Standup")
    busy = await env.knowledge.add_entity("Ada")
    quiet = await env.knowledge.add_entity("Grace")
    await env.links.link(workspace.id, busy)
    await env.links.link(workspace.id, busy, target="note", target_id=note.id)
    await env.links.link(workspace.id, quiet)

    entities = await env.links.entities_for(workspace.id)

    assert [row["name"] for row in entities] == ["Ada", "Grace"]
    assert entities[0]["link_count"] == 2
    assert entities[0]["uri"].startswith("knowledge://entity/")


@pytest.mark.asyncio
async def test_entities_for_an_empty_workspace_is_empty(env) -> None:
    workspace = await env.workspaces.create_workspace("Empty")
    assert await env.links.entities_for(workspace.id) == []


@pytest.mark.asyncio
async def test_link_count_matches_the_listing(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")
    for name in ("Ada", "Grace", "Katherine"):
        await env.links.link(workspace.id, await env.knowledge.add_entity(name))

    assert await env.links.link_count(workspace.id) == 3


@pytest.mark.asyncio
async def test_require_link_raises_for_an_unknown_id(env) -> None:
    with pytest.raises(ServiceError, match="does not exist"):
        await env.links.require_link("nope")


# --- unlinking ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unlink_removes_the_row(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")
    link = await env.links.link(workspace.id, await env.knowledge.add_entity("Ada"))

    assert await env.links.unlink(link.id) is True
    assert await env.links.get_link(link.id) is None


@pytest.mark.asyncio
async def test_unlinking_something_absent_reports_false(env) -> None:
    assert await env.links.unlink("nope") is False


@pytest.mark.asyncio
async def test_deleting_a_workspace_takes_its_links(env) -> None:
    """The ORM cascade, which is what actually deletes children -- see
    ``Workspace``'s own note on ``ondelete`` versus ``cascade``."""
    workspace = await env.workspaces.create_workspace("Research")
    await env.links.link(workspace.id, await env.knowledge.add_entity("Ada"))

    await env.workspaces.delete_workspace(workspace.id)

    assert await env.links.list_links(workspace_id=workspace.id) == []


# --- ingestion ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_text_extracts_once_and_links_what_it_found(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")

    result = await env.links.ingest_text(workspace.id, "Ada worked on the migration")

    assert env.knowledge.calls == ["Ada worked on the migration"]
    assert result.entities_linked == 2
    assert result.links_created == 2
    assert len(await env.links.list_links(workspace_id=workspace.id)) == 2


@pytest.mark.asyncio
async def test_ingest_text_uses_the_entity_confidence(env) -> None:
    """The link's confidence is the graph's own, not a number this
    service invented."""
    workspace = await env.workspaces.create_workspace("Research")
    await env.links.ingest_text(workspace.id, "Ada")

    links = await env.links.list_links(workspace_id=workspace.id)

    assert {link.confidence for link in links} == {0.8}
    assert {link.source for link in links} == {"extracted"}


@pytest.mark.asyncio
async def test_ingesting_empty_text_is_a_skip_not_an_extraction(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")

    result = await env.links.ingest_text(workspace.id, "   ")

    assert result.targets_skipped == 1
    assert result.targets_processed == 0
    assert env.knowledge.calls == []


@pytest.mark.asyncio
async def test_reingestion_replaces_extracted_links_for_that_target(env) -> None:
    """An edited note must stop claiming entities its text no longer
    mentions."""
    workspace = await env.workspaces.create_workspace("Research")
    note = await env.workspaces.create_note(workspace.id, "Standup")
    await env.links.ingest_text(workspace.id, "Ada", target="note", target_id=note.id)

    env.knowledge.names = ["Grace"]
    result = await env.links.ingest_text(workspace.id, "Grace", target="note", target_id=note.id)

    linked = await env.links.list_links(target="note", target_id=note.id)
    assert result.links_replaced == 2
    assert len(linked) == 1


@pytest.mark.asyncio
async def test_reingestion_leaves_manual_links_alone(env) -> None:
    """A person's assertion outlives a re-read of the file."""
    workspace = await env.workspaces.create_workspace("Research")
    note = await env.workspaces.create_note(workspace.id, "Standup")
    asserted = await env.links.link(
        workspace.id,
        await env.knowledge.add_entity("Katherine"),
        target="note",
        target_id=note.id,
        source="manual",
    )

    await env.links.ingest_text(workspace.id, "Ada", target="note", target_id=note.id)

    assert await env.links.get_link(asserted.id) is not None


@pytest.mark.asyncio
async def test_reingestion_can_be_asked_to_add_rather_than_replace(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")
    await env.links.ingest_text(workspace.id, "Ada")

    env.knowledge.names = ["Katherine"]
    await env.links.ingest_text(workspace.id, "Katherine", replace=False)

    assert len(await env.links.list_links(workspace_id=workspace.id)) == 3


@pytest.mark.asyncio
async def test_ingest_note_reads_its_title_and_body(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")
    note = await env.workspaces.create_note(workspace.id, "Standup", content="Ada spoke")

    result = await env.links.ingest_note(note.id)

    assert "Standup" in env.knowledge.calls[0]
    assert "Ada spoke" in env.knowledge.calls[0]
    assert result.links_created == 2


@pytest.mark.asyncio
async def test_ingest_file_reads_the_index_record_not_the_disk(env) -> None:
    """Task Group C already decided which files are readable as text and
    how much of each it keeps; re-reading here would be a second answer
    to both questions."""
    workspace = await env.workspaces.create_workspace("Research")
    file = await env.files.create_file(workspace.id, "notes.md", b"Ada wrote this")

    result = await env.links.ingest_file(file.id)

    assert "Ada wrote this" in env.knowledge.calls[0]
    assert result.links_created == 2


@pytest.mark.asyncio
async def test_an_unindexed_file_is_skipped(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")
    file = await env.files.create_file(workspace.id, "photo.png", b"\x89PNG\r\n")

    result = await env.links.ingest_file(file.id)

    assert result.targets_skipped == 1
    assert env.knowledge.calls == []


@pytest.mark.asyncio
async def test_ingest_workspace_covers_its_own_text_notes_and_files(env) -> None:
    workspace = await env.workspaces.create_workspace("Research", description="the migration")
    await env.workspaces.create_note(workspace.id, "Standup", content="Ada spoke")
    await env.files.create_file(workspace.id, "notes.md", b"Ada wrote this")

    result = await env.links.ingest_workspace(workspace.id)

    assert result.targets_processed == 3
    assert len(env.knowledge.calls) == 3


@pytest.mark.asyncio
async def test_ingest_workspace_can_skip_corpora(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")
    await env.workspaces.create_note(workspace.id, "Standup", content="Ada")

    result = await env.links.ingest_workspace(
        workspace.id, include_notes=False, include_files=False
    )

    assert result.targets_processed == 1


@pytest.mark.asyncio
async def test_ingest_workspace_bounds_how_many_targets_it_reads(env) -> None:
    """Extraction is an LLM call per target, so this is the difference
    between a slow request and an unbounded one."""
    workspace = await env.workspaces.create_workspace("Research")
    for index in range(5):
        await env.workspaces.create_note(workspace.id, f"Note {index}", content="Ada")

    result = await env.links.ingest_workspace(workspace.id, include_files=False, limit=2)

    assert result.targets_processed == 3  # the workspace itself plus two notes


@pytest.mark.asyncio
async def test_ingest_bounds_how_much_text_it_hands_the_extractor(env) -> None:
    from jarvis.services.workspace_ai_service import MAX_INGEST_CHARS

    workspace = await env.workspaces.create_workspace("Research")
    await env.links.ingest_text(workspace.id, "x" * (MAX_INGEST_CHARS * 2))

    assert len(env.knowledge.calls[0]) == MAX_INGEST_CHARS


@pytest.mark.asyncio
async def test_ingesting_an_unknown_workspace_is_refused(env) -> None:
    with pytest.raises(ServiceError, match="does not exist"):
        await env.links.ingest_workspace("nope")


@pytest.mark.asyncio
async def test_ingest_text_refuses_a_bad_target_before_paying_for_extraction(env) -> None:
    """An unstorable link must fail as a bad request rather than as an
    IntegrityError -- and extraction is an LLM call, so refusing early
    also avoids paying for a result that cannot be recorded."""
    workspace = await env.workspaces.create_workspace("Research")

    with pytest.raises(ServiceError, match="does not exist"):
        await env.links.ingest_text(workspace.id, "Ada", target="note", target_id="fabricated")
    with pytest.raises(ServiceError, match="Workspace"):
        await env.links.ingest_text("no-such-workspace", "Ada")

    assert env.knowledge.calls == []


@pytest.mark.asyncio
async def test_ingest_text_refuses_a_target_from_another_workspace(env) -> None:
    first = await env.workspaces.create_workspace("First")
    second = await env.workspaces.create_workspace("Second")
    foreign_note = await env.workspaces.create_note(second.id, "Theirs")

    with pytest.raises(ServiceError, match="different workspace"):
        await env.links.ingest_text(first.id, "Ada", target="note", target_id=foreign_note.id)


@pytest.mark.asyncio
async def test_ingestion_needs_the_collaborator_that_owns_the_corpus(tmp_path, monkeypatch) -> None:
    """Optional collaborators widen what can be ingested; asking for one
    that is not wired is an error, not a silent no-op."""
    settings = _settings(tmp_path, monkeypatch)
    from jarvis.infrastructure.database.sqlite_client import SQLiteDatabase

    db = SQLiteDatabase(settings.db)
    await db.initialize()
    try:
        service = WorkspaceKnowledgeService(
            database=db, knowledge_service=_FakeKnowledge(db)  # type: ignore[arg-type]
        )
        with pytest.raises(ServiceError, match="workspace service"):
            await service.ingest_note("any")
        with pytest.raises(ServiceError, match="file service"):
            await service.ingest_file("any")
    finally:
        await db.dispose()


# --- events ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_linking_and_unlinking_publish_one_event_each(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")
    link = await env.links.link(workspace.id, await env.knowledge.add_entity("Ada"))
    await env.links.unlink(link.id)

    assert [event.action for event in env.events] == ["linked", "unlinked"]
    assert env.events[0].workspace_id == workspace.id
    assert env.events[0].source == "manual"


@pytest.mark.asyncio
async def test_ingestion_publishes_once_per_target_not_once_per_link(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")

    await env.links.ingest_text(workspace.id, "Ada and the migration")

    assert len(env.events) == 1
    assert env.events[0].source == "extracted"
    # A distinct action, so the empty `link_id` reads as the documented
    # shape of a batch rather than a missing field.
    assert env.events[0].action == "reingested"
    assert env.events[0].link_id == ""


@pytest.mark.asyncio
async def test_a_promotion_is_published_because_it_changes_what_survives(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")
    entity_id = await env.knowledge.add_entity("Ada")
    await env.links.link(workspace.id, entity_id, source="extracted")
    env.events.clear()

    await env.links.link(workspace.id, entity_id, source="manual")

    assert [event.action for event in env.events] == ["promoted"]


@pytest.mark.asyncio
async def test_an_unchanged_relink_publishes_nothing(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")
    entity_id = await env.knowledge.add_entity("Ada")
    await env.links.link(workspace.id, entity_id, source="manual")
    env.events.clear()

    await env.links.link(workspace.id, entity_id, source="manual")

    assert env.events == []


@pytest.mark.asyncio
async def test_an_ingestion_that_changed_nothing_publishes_nothing(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")
    await env.links.ingest_text(workspace.id, "Ada")
    env.events.clear()

    await env.links.ingest_text(workspace.id, "Ada", replace=False)

    assert env.events == []


@pytest.mark.asyncio
async def test_the_service_works_without_an_event_bus(tmp_path, monkeypatch) -> None:
    settings = _settings(tmp_path, monkeypatch)
    from jarvis.infrastructure.database.sqlite_client import SQLiteDatabase

    db = SQLiteDatabase(settings.db)
    await db.initialize()
    try:
        workspaces = WorkspaceService(database=db)
        knowledge = _FakeKnowledge(db)
        service = WorkspaceKnowledgeService(
            database=db,
            knowledge_service=knowledge,  # type: ignore[arg-type]
            workspace_service=workspaces,
        )
        workspace = await workspaces.create_workspace("Quiet")
        link = await service.link(workspace.id, await knowledge.add_entity("Ada"))
        assert link.id
    finally:
        await db.dispose()
