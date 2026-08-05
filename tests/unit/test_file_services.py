"""Folder / File / Attachment service tests -- Milestone 11 Task Group C.

Real temp-file SQLite and a real temporary storage root throughout,
matching ``test_productivity_services.py`` -- these are the repository
tests too, because a repository mocked away from its own dialect proves
nothing about the queries that run, and a storage layer mocked away from
a real filesystem proves nothing about path containment.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core.events.event_bus import EventBus
from jarvis.core.events.events import (
    AttachmentUpdatedEvent,
    FileUpdatedEvent,
    FolderUpdatedEvent,
)
from jarvis.core.exceptions import ServiceError
from jarvis.services.file_service import (
    AttachmentService,
    FileService,
    FolderService,
    describe_target,
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
        self.bus = bus
        self.root = root
        self.events: list[object] = []
        for event_type in (FileUpdatedEvent, FolderUpdatedEvent, AttachmentUpdatedEvent):
            bus.subscribe(event_type, lambda e: self.events.append(e) or None)
        self.workspaces = WorkspaceService(database=db, event_bus=bus)
        self.folders = FolderService(database=db, storage_root=root, event_bus=bus)
        self.files = FileService(database=db, storage_root=root, event_bus=bus)
        self.attachments = AttachmentService(database=db, event_bus=bus)

    def actions(self) -> list[tuple[str, str]]:
        return [(type(e).__name__, e.action) for e in self.events]


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


async def _workspace(env: _Env, name: str = "W") -> str:
    return (await env.workspaces.create_workspace(name)).id


# =============================================================== Folders


@pytest.mark.asyncio
async def test_folder_crud_round_trip(env: _Env) -> None:
    workspace_id = await _workspace(env)

    folder = await env.folders.create_folder(workspace_id, "Docs")
    assert folder.relative_path == "Docs"
    assert folder.parent_folder_id is None
    # The directory exists on disk, not only in the catalogue.
    assert (env.root / workspace_id / "Docs").is_dir()

    child = await env.folders.create_folder(workspace_id, "Invoices", parent_folder_id=folder.id)
    assert child.relative_path == "Docs/Invoices"
    assert (env.root / workspace_id / "Docs" / "Invoices").is_dir()

    assert await env.folders.delete_folder(child.id) is True
    assert await env.folders.get_folder(child.id) is None
    assert not (env.root / workspace_id / "Docs" / "Invoices").exists()


@pytest.mark.asyncio
async def test_duplicate_sibling_folder_is_refused(env: _Env) -> None:
    workspace_id = await _workspace(env)
    await env.folders.create_folder(workspace_id, "Docs")

    with pytest.raises(ServiceError, match="already exists"):
        await env.folders.create_folder(workspace_id, "Docs")

    # A same-named folder under a different parent is fine -- uniqueness
    # is per-parent, the way a filesystem works.
    other = await env.folders.create_folder(workspace_id, "Archive")
    nested = await env.folders.create_folder(workspace_id, "Docs", parent_folder_id=other.id)
    assert nested.relative_path == "Archive/Docs"


@pytest.mark.asyncio
async def test_a_folder_cannot_be_moved_into_its_own_subtree(env: _Env) -> None:
    """The check a foreign key cannot express: moving a folder inside
    itself detaches the whole subtree from every root while leaving each
    row individually valid."""
    workspace_id = await _workspace(env)
    parent = await env.folders.create_folder(workspace_id, "A")
    child = await env.folders.create_folder(workspace_id, "B", parent_folder_id=parent.id)
    grandchild = await env.folders.create_folder(workspace_id, "C", parent_folder_id=child.id)

    with pytest.raises(ServiceError, match="inside itself"):
        await env.folders.move_folder(parent.id, parent_folder_id=parent.id)
    with pytest.raises(ServiceError, match="own subtree"):
        await env.folders.move_folder(parent.id, parent_folder_id=grandchild.id)


@pytest.mark.asyncio
async def test_moving_a_folder_rewrites_the_whole_subtree(env: _Env) -> None:
    workspace_id = await _workspace(env)
    source = await env.folders.create_folder(workspace_id, "Src")
    deep = await env.folders.create_folder(workspace_id, "Deep", parent_folder_id=source.id)
    destination = await env.folders.create_folder(workspace_id, "Dst")
    file = await env.files.create_file(workspace_id, "note.md", b"# hi", folder_id=deep.id)
    assert file.relative_path == f"{workspace_id}/Src/Deep/note.md"

    moved = await env.folders.move_folder(source.id, parent_folder_id=destination.id)
    assert moved.relative_path == "Dst/Src"

    refreshed_deep = await env.folders.require_folder(deep.id)
    assert refreshed_deep.relative_path == "Dst/Src/Deep"
    refreshed_file = await env.files.require_file(file.id)
    assert refreshed_file.relative_path == f"{workspace_id}/Dst/Src/Deep/note.md"
    # And the bytes actually moved, not just the strings.
    assert (env.root / workspace_id / "Dst" / "Src" / "Deep" / "note.md").read_bytes() == b"# hi"
    assert not (env.root / workspace_id / "Src").exists()

    assert ("FolderUpdatedEvent", "moved") in env.actions()


@pytest.mark.asyncio
async def test_renaming_a_folder_rewrites_paths_and_disk(env: _Env) -> None:
    workspace_id = await _workspace(env)
    folder = await env.folders.create_folder(workspace_id, "Old")
    file = await env.files.create_file(workspace_id, "a.txt", b"x", folder_id=folder.id)

    renamed = await env.folders.rename_folder(folder.id, "New")
    assert renamed.relative_path == "New"
    assert (await env.files.require_file(file.id)).relative_path == f"{workspace_id}/New/a.txt"
    assert (env.root / workspace_id / "New" / "a.txt").read_bytes() == b"x"


@pytest.mark.asyncio
async def test_a_non_empty_folder_needs_an_explicit_recursive_delete(env: _Env) -> None:
    """The DB cascade would take the subtree happily; that is the wrong
    default for a destructive operation on real bytes."""
    workspace_id = await _workspace(env)
    folder = await env.folders.create_folder(workspace_id, "Docs")
    await env.files.create_file(workspace_id, "a.txt", b"x", folder_id=folder.id)

    with pytest.raises(ServiceError, match="not empty"):
        await env.folders.delete_folder(folder.id)

    assert await env.folders.delete_folder(folder.id, recursive=True) is True
    assert not (env.root / workspace_id / "Docs").exists()


@pytest.mark.asyncio
async def test_a_folder_cannot_be_reparented_across_workspaces(env: _Env) -> None:
    first = await _workspace(env, "One")
    second = await _workspace(env, "Two")
    folder = await env.folders.create_folder(first, "Docs")
    foreign = await env.folders.create_folder(second, "Docs")

    with pytest.raises(ServiceError, match="another workspace"):
        await env.folders.move_folder(folder.id, parent_folder_id=foreign.id)


# ================================================================= Files


@pytest.mark.asyncio
async def test_file_crud_round_trip(env: _Env) -> None:
    workspace_id = await _workspace(env)

    file = await env.files.create_file(
        workspace_id, "notes.md", b"# Title\nbody", description="A note", tags=["Work", "work "]
    )
    assert file.extension == ".md"
    assert file.mime_type in {"text/markdown", "text/x-markdown"}
    assert file.size_bytes == len(b"# Title\nbody")
    assert file.relative_path == f"{workspace_id}/notes.md"
    assert await env.files.tags_for(file.id) == ["work"]
    assert await env.files.read_file(file.id) == b"# Title\nbody"

    assert await env.files.delete_file(file.id) is True
    assert await env.files.get_file(file.id) is None
    assert not (env.root / workspace_id / "notes.md").exists()


@pytest.mark.asyncio
async def test_duplicate_filename_in_one_folder_is_refused(env: _Env) -> None:
    workspace_id = await _workspace(env)
    await env.files.create_file(workspace_id, "a.txt", b"1")

    with pytest.raises(ServiceError, match="already exists"):
        await env.files.create_file(workspace_id, "a.txt", b"2")

    # The original is untouched -- a refused create must not corrupt it.
    assert (env.root / workspace_id / "a.txt").read_bytes() == b"1"


@pytest.mark.asyncio
async def test_two_workspaces_may_hold_the_same_path(env: _Env) -> None:
    """The workspace id leads every stored path precisely so this does
    not collide on disk."""
    first = await _workspace(env, "One")
    second = await _workspace(env, "Two")

    a = await env.files.create_file(first, "todo.md", b"first")
    b = await env.files.create_file(second, "todo.md", b"second")

    assert a.relative_path != b.relative_path
    assert await env.files.read_file(a.id) == b"first"
    assert await env.files.read_file(b.id) == b"second"


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["../escape.txt", "..", "a/b.txt", "a\\b.txt", "", "con.txt"])
async def test_a_file_name_that_could_escape_is_refused(env: _Env, name: str) -> None:
    """The single most important property in this task group: no name a
    caller supplies can put bytes outside the storage root."""
    workspace_id = await _workspace(env)

    with pytest.raises(ServiceError):
        await env.files.create_file(workspace_id, name, b"payload")

    # Nothing was written anywhere -- not under the root, not above it.
    assert not (env.root.parent / "escape.txt").exists()
    assert list((env.root / workspace_id).glob("*")) == [] or not (env.root / workspace_id).exists()


@pytest.mark.asyncio
async def test_a_rename_is_validated_as_strictly_as_a_create(env: _Env) -> None:
    """A rename can introduce ``..`` just as easily as a create, and the
    two are easy to protect unevenly."""
    workspace_id = await _workspace(env)
    file = await env.files.create_file(workspace_id, "a.txt", b"x")

    with pytest.raises(ServiceError):
        await env.files.rename_file(file.id, "../escaped.txt")
    assert not (env.root.parent / "escaped.txt").exists()
    assert (await env.files.require_file(file.id)).filename == "a.txt"


@pytest.mark.asyncio
async def test_renaming_changes_extension_mime_and_index_status(env: _Env) -> None:
    workspace_id = await _workspace(env)
    file = await env.files.create_file(workspace_id, "data.bin", b"hello world")
    assert (await env.files.index_record(file.id)).status == "skipped"

    renamed = await env.files.rename_file(file.id, "data.txt")
    assert renamed.extension == ".txt"
    assert renamed.mime_type == "text/plain"
    record = await env.files.index_record(file.id)
    assert record.status == "indexed"
    assert record.content_text == "hello world"


@pytest.mark.asyncio
async def test_moving_a_file_between_folders_moves_the_bytes(env: _Env) -> None:
    workspace_id = await _workspace(env)
    source = await env.folders.create_folder(workspace_id, "In")
    destination = await env.folders.create_folder(workspace_id, "Out")
    file = await env.files.create_file(workspace_id, "a.txt", b"x", folder_id=source.id)

    moved = await env.files.move_file(file.id, folder_id=destination.id)
    assert moved.relative_path == f"{workspace_id}/Out/a.txt"
    assert (env.root / workspace_id / "Out" / "a.txt").read_bytes() == b"x"
    assert not (env.root / workspace_id / "In" / "a.txt").exists()

    # And back to the workspace root, which is a real destination.
    unfiled = await env.files.move_file(file.id, folder_id=None)
    assert unfiled.folder_id is None
    assert unfiled.relative_path == f"{workspace_id}/a.txt"


@pytest.mark.asyncio
async def test_a_file_cannot_be_filed_into_another_workspaces_folder(env: _Env) -> None:
    first = await _workspace(env, "One")
    second = await _workspace(env, "Two")
    foreign = await env.folders.create_folder(second, "Docs")

    with pytest.raises(ServiceError, match="different workspace"):
        await env.files.create_file(first, "a.txt", b"x", folder_id=foreign.id)


@pytest.mark.asyncio
async def test_tags_and_metadata(env: _Env) -> None:
    workspace_id = await _workspace(env)
    file = await env.files.create_file(workspace_id, "a.txt", b"x")

    assert await env.files.add_tag(file.id, "Invoice") == ["invoice"]
    # Idempotent -- re-tagging is a no-op, not a primary-key violation.
    assert await env.files.add_tag(file.id, "invoice") == ["invoice"]
    assert await env.files.remove_tag(file.id, "invoice") == []

    await env.files.set_metadata(file.id, "checksum", "abc")
    await env.files.set_metadata(file.id, "checksum", "def")  # upsert, not duplicate
    rows = await env.files.list_metadata(file.id)
    assert [(r.key, r.value) for r in rows] == [("checksum", "def")]
    assert await env.files.delete_metadata(file.id, "checksum") is True


@pytest.mark.asyncio
async def test_listing_by_tag_uses_the_join_not_substring_matching(env: _Env) -> None:
    """The reason file tags are a real table: ``work`` must not match
    ``homework``."""
    workspace_id = await _workspace(env)
    a = await env.files.create_file(workspace_id, "a.txt", b"x", tags=["work"])
    await env.files.create_file(workspace_id, "b.txt", b"y", tags=["homework"])

    found = await env.files.list_files(workspace_id=workspace_id, tag="work")
    assert [f.id for f in found] == [a.id]


# ============================================================== Indexing


@pytest.mark.asyncio
async def test_indexing_records_four_distinct_outcomes(env: _Env) -> None:
    workspace_id = await _workspace(env)

    indexed = await env.files.create_file(workspace_id, "a.md", b"# hello")
    skipped = await env.files.create_file(workspace_id, "b.png", b"\x89PNG\r\n")

    assert (await env.files.index_record(indexed.id)).status == "indexed"
    assert (await env.files.index_record(indexed.id)).content_text == "# hello"
    # A skipped file is a *successful* catalogue entry, not a failure.
    record = await env.files.index_record(skipped.id)
    assert record.status == "skipped"
    assert record.content_text == ""
    assert record.detail


@pytest.mark.asyncio
async def test_a_large_file_is_truncated_and_says_so(tmp_path: Path, monkeypatch) -> None:
    settings = _settings(tmp_path, monkeypatch)
    from jarvis.infrastructure.database.sqlite_client import SQLiteDatabase

    db = SQLiteDatabase(settings.db)
    await db.initialize()
    root = tmp_path / "storage"
    root.mkdir()
    try:
        workspaces = WorkspaceService(database=db)
        files = FileService(database=db, storage_root=root, index_max_bytes=8)
        workspace_id = (await workspaces.create_workspace("W")).id

        file = await files.create_file(workspace_id, "big.txt", b"0123456789abcdef")
        record = await files.index_record(file.id)
        assert record.status == "truncated"
        assert record.content_text == "01234567"
        # The whole file is still on disk -- only the *index* is bounded.
        assert await files.read_file(file.id) == b"0123456789abcdef"
    finally:
        await db.dispose()


@pytest.mark.asyncio
async def test_indexing_can_be_disabled_without_breaking_cataloguing(
    tmp_path: Path, monkeypatch
) -> None:
    settings = _settings(tmp_path, monkeypatch)
    from jarvis.infrastructure.database.sqlite_client import SQLiteDatabase

    db = SQLiteDatabase(settings.db)
    await db.initialize()
    root = tmp_path / "storage"
    root.mkdir()
    try:
        workspaces = WorkspaceService(database=db)
        files = FileService(database=db, storage_root=root, index_enabled=False)
        workspace_id = (await workspaces.create_workspace("W")).id

        file = await files.create_file(workspace_id, "a.md", b"# hello")
        record = await files.index_record(file.id)
        assert record.status == "skipped"
        assert "disabled" in record.detail.lower()
        # The file itself is fully catalogued and readable.
        assert await files.read_file(file.id) == b"# hello"
    finally:
        await db.dispose()


@pytest.mark.asyncio
async def test_reindex_workspace_reports_per_status_counts(env: _Env) -> None:
    workspace_id = await _workspace(env)
    await env.files.create_file(workspace_id, "a.md", b"# a")
    await env.files.create_file(workspace_id, "b.txt", b"b")
    await env.files.create_file(workspace_id, "c.png", b"\x89PNG")

    counts = await env.files.reindex_workspace(workspace_id)
    assert counts == {"indexed": 2, "skipped": 1}


@pytest.mark.asyncio
async def test_workspace_stats(env: _Env) -> None:
    workspace_id = await _workspace(env)
    await env.folders.create_folder(workspace_id, "Docs")
    await env.files.create_file(workspace_id, "a.md", b"12345")
    await env.files.create_file(workspace_id, "b.md", b"123")

    stats = await env.files.workspace_stats(workspace_id)
    assert stats["file_count"] == 2
    assert stats["folder_count"] == 1
    assert stats["total_bytes"] == 8
    assert stats["by_extension"] == {".md": 2}
    assert stats["index_status"] == {"indexed": 2}


# ================================================================ Search


@pytest.mark.asyncio
async def test_search_matches_filename_tag_and_extracted_body(env: _Env) -> None:
    workspace_id = await _workspace(env)
    by_name = await env.files.create_file(workspace_id, "quarterly.md", b"nothing useful")
    by_body = await env.files.create_file(workspace_id, "misc.md", b"the quarterly numbers")
    by_tag = await env.files.create_file(workspace_id, "other.png", b"\x89", tags=["quarterly"])

    hits = await env.files.search_files("quarterly")
    found = {hit.id for hit in hits}
    assert {by_name.id, by_body.id, by_tag.id} <= found
    # A name match outranks a body-only match.
    scores = {hit.id: hit.score for hit in hits}
    assert scores[by_name.id] > scores[by_body.id]


@pytest.mark.asyncio
async def test_folder_search_finds_by_name_and_path(env: _Env) -> None:
    workspace_id = await _workspace(env)
    parent = await env.folders.create_folder(workspace_id, "Finance")
    await env.folders.create_folder(workspace_id, "2026", parent_folder_id=parent.id)

    hits = await env.folders.search_folders("finance")
    assert {hit.title for hit in hits} == {"Finance", "2026"}
    assert all(hit.source == "folders" for hit in hits)


# =========================================================== Attachments


@pytest.mark.asyncio
async def test_attaching_to_the_workspace_itself_is_the_default(env: _Env) -> None:
    workspace_id = await _workspace(env)
    file = await env.files.create_file(workspace_id, "a.txt", b"x")

    attachment = await env.attachments.attach(file.id, caption="Filed here")
    target, target_id = describe_target(attachment)
    assert (target, target_id) == ("workspace", workspace_id)
    assert ("AttachmentUpdatedEvent", "attached") in env.actions()


@pytest.mark.asyncio
async def test_attaching_to_a_note_sets_exactly_one_narrow_key(env: _Env) -> None:
    workspace_id = await _workspace(env)
    note = await env.workspaces.create_note(workspace_id, "Meeting")
    file = await env.files.create_file(workspace_id, "a.txt", b"x")

    attachment = await env.attachments.attach(file.id, target="note", target_id=note.id)
    assert attachment.note_id == note.id
    assert attachment.task_id is None
    assert attachment.project_id is None
    assert describe_target(attachment) == ("note", note.id)


@pytest.mark.asyncio
async def test_attachment_target_arguments_are_validated(env: _Env) -> None:
    workspace_id = await _workspace(env)
    file = await env.files.create_file(workspace_id, "a.txt", b"x")

    with pytest.raises(ServiceError, match="Unknown attachment target"):
        await env.attachments.attach(file.id, target="spaceship", target_id="x")
    with pytest.raises(ServiceError, match="requires a target id"):
        await env.attachments.attach(file.id, target="note")
    with pytest.raises(ServiceError, match="takes no target id"):
        await env.attachments.attach(file.id, target="workspace", target_id="x")


@pytest.mark.asyncio
async def test_detaching_never_deletes_the_file(env: _Env) -> None:
    workspace_id = await _workspace(env)
    file = await env.files.create_file(workspace_id, "a.txt", b"x")
    attachment = await env.attachments.attach(file.id)

    assert await env.attachments.detach(attachment.id) is True
    assert await env.files.get_file(file.id) is not None
    assert await env.files.read_file(file.id) == b"x"


@pytest.mark.asyncio
async def test_deleting_a_file_removes_its_attachments(env: _Env) -> None:
    """The cascade that *should* run: an attachment to a file that no
    longer exists is a dangling row by definition."""
    workspace_id = await _workspace(env)
    file = await env.files.create_file(workspace_id, "a.txt", b"x")
    await env.attachments.attach(file.id)

    await env.files.delete_file(file.id)
    assert await env.attachments.list_attachments(workspace_id=workspace_id) == []


@pytest.mark.asyncio
async def test_attaching_a_nonexistent_file_is_refused_before_the_database(env: _Env) -> None:
    with pytest.raises(ServiceError, match="does not exist"):
        await env.attachments.attach("nope", target="workspace")


@pytest.mark.asyncio
async def test_a_fabricated_target_id_is_refused_before_the_database(env: _Env) -> None:
    """Foreign keys already refuse this, but as an ``IntegrityError``
    five layers down that reaches the caller as a 500. The check here
    turns the same rejection into a message they can act on -- it does
    not replace the constraint."""
    workspace_id = await _workspace(env)
    file = await env.files.create_file(workspace_id, "a.txt", b"x")

    with pytest.raises(ServiceError, match="does not exist"):
        await env.attachments.attach(file.id, target="task", target_id="not-a-real-task")


@pytest.mark.asyncio
async def test_an_attachment_cannot_span_two_workspaces(env: _Env) -> None:
    """The part a foreign key genuinely cannot express: a valid
    ``note_id`` says nothing about the note being in *this* file's
    workspace."""
    first = await _workspace(env, "One")
    second = await _workspace(env, "Two")
    file = await env.files.create_file(first, "a.txt", b"x")
    foreign_note = await env.workspaces.create_note(second, "Elsewhere")

    with pytest.raises(ServiceError, match="different workspace"):
        await env.attachments.attach(file.id, target="note", target_id=foreign_note.id)


# ================================================================ Events


@pytest.mark.asyncio
async def test_every_documented_action_is_published(env: _Env) -> None:
    workspace_id = await _workspace(env)
    folder = await env.folders.create_folder(workspace_id, "Docs")
    file = await env.files.create_file(workspace_id, "a.txt", b"x", folder_id=folder.id)
    await env.files.update_file(file.id, description="d")
    await env.files.rename_file(file.id, "b.txt")
    await env.files.move_file(file.id, folder_id=None)
    await env.files.reindex_file(file.id)
    await env.folders.rename_folder(folder.id, "Papers")
    attachment = await env.attachments.attach(file.id)
    await env.attachments.detach(attachment.id)
    await env.files.delete_file(file.id)
    await env.folders.delete_folder(folder.id)

    actions = set(env.actions())
    assert {
        ("FileUpdatedEvent", "created"),
        ("FileUpdatedEvent", "updated"),
        ("FileUpdatedEvent", "renamed"),
        ("FileUpdatedEvent", "moved"),
        ("FileUpdatedEvent", "indexed"),
        ("FileUpdatedEvent", "deleted"),
        ("FolderUpdatedEvent", "created"),
        ("FolderUpdatedEvent", "renamed"),
        ("FolderUpdatedEvent", "deleted"),
        ("AttachmentUpdatedEvent", "attached"),
        ("AttachmentUpdatedEvent", "detached"),
    } <= actions


@pytest.mark.asyncio
async def test_a_folder_event_reports_how_many_files_it_touched(env: _Env) -> None:
    workspace_id = await _workspace(env)
    folder = await env.folders.create_folder(workspace_id, "Docs")
    await env.files.create_file(workspace_id, "a.txt", b"x", folder_id=folder.id)
    await env.files.create_file(workspace_id, "b.txt", b"y", folder_id=folder.id)
    env.events.clear()

    await env.folders.rename_folder(folder.id, "Papers")
    renamed = [e for e in env.events if isinstance(e, FolderUpdatedEvent)]
    assert renamed[0].affected_files == 2
