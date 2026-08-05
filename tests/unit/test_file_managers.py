"""File Platform manager tests -- Milestone 11 Task Group C.

The managers' contract is that they **collect and never compute**, and
that every collaborator except their own service is optional so a
partially-wired container degrades to less context rather than failing.
Both halves are asserted here; the second is the one that silently rots
otherwise, because a fully-wired test never exercises it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core.events.event_bus import EventBus
from jarvis.services.file_managers import AttachmentManager, FileManager, FolderManager
from jarvis.services.file_service import AttachmentService, FileService, FolderService
from jarvis.services.workspace_service import WorkspaceService


def _settings(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JARVIS_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'jarvis.db'}")

    from jarvis.core.config import settings as settings_mod

    settings_mod.load_settings.cache_clear()  # type: ignore[attr-defined]
    return settings_mod.load_settings()


class _Env:
    def __init__(self, db, root: Path) -> None:
        bus = EventBus()
        self.workspaces = WorkspaceService(database=db, event_bus=bus)
        self.folders = FolderService(database=db, storage_root=root, event_bus=bus)
        self.files = FileService(database=db, storage_root=root, event_bus=bus)
        self.attachments = AttachmentService(database=db, event_bus=bus)

        self.folder_manager = FolderManager(
            self.folders, file_service=self.files, workspace_service=self.workspaces
        )
        self.file_manager = FileManager(
            self.files,
            folder_service=self.folders,
            attachment_service=self.attachments,
            workspace_service=self.workspaces,
        )
        self.attachment_manager = AttachmentManager(
            self.attachments, file_service=self.files, workspace_service=self.workspaces
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
        yield _Env(db, root)
    finally:
        await db.dispose()


@pytest.mark.asyncio
async def test_tree_includes_depth_file_counts_and_unfiled_files(env: _Env) -> None:
    workspace_id = (await env.workspaces.create_workspace("W")).id
    parent = await env.folders.create_folder(workspace_id, "A")
    child = await env.folders.create_folder(workspace_id, "B", parent_folder_id=parent.id)
    await env.files.create_file(workspace_id, "deep.txt", b"x", folder_id=child.id)
    await env.files.create_file(workspace_id, "loose.txt", b"y")

    tree = await env.folder_manager.tree(workspace_id)

    assert tree["workspace"] == {"id": workspace_id, "name": "W"}
    by_path = {row["relative_path"]: row for row in tree["folders"]}
    assert by_path["A"]["depth"] == 0
    assert by_path["A/B"]["depth"] == 1
    assert by_path["A/B"]["file_count"] == 1
    assert by_path["A"]["file_count"] == 0
    # Unfiled files are the normal case, and a tree that hid them would
    # make an uploaded file look like it vanished.
    assert [f["filename"] for f in tree["unfiled_files"]] == ["loose.txt"]


@pytest.mark.asyncio
async def test_folder_contents_is_one_level_not_a_subtree(env: _Env) -> None:
    workspace_id = (await env.workspaces.create_workspace("W")).id
    parent = await env.folders.create_folder(workspace_id, "A")
    child = await env.folders.create_folder(workspace_id, "B", parent_folder_id=parent.id)
    await env.files.create_file(workspace_id, "deep.txt", b"x", folder_id=child.id)

    contents = await env.folder_manager.contents(parent.id)
    assert [row["name"] for row in contents["subfolders"]] == ["B"]
    # The grandchild's file is not here -- that is the point.
    assert contents["files"] == []


@pytest.mark.asyncio
async def test_file_context_collects_folder_workspace_tags_index_and_attachments(
    env: _Env,
) -> None:
    workspace_id = (await env.workspaces.create_workspace("W")).id
    folder = await env.folders.create_folder(workspace_id, "Docs")
    file = await env.files.create_file(
        workspace_id, "a.md", b"# hello", folder_id=folder.id, tags=["work"]
    )
    await env.attachments.attach(file.id, caption="Filed")

    context = await env.file_manager.context(file.id)

    assert context["file"]["filename"] == "a.md"
    assert context["folder"]["relative_path"] == "Docs"
    assert context["workspace"] == {"id": workspace_id, "name": "W"}
    assert context["tags"] == ["work"]
    assert context["index"]["status"] == "indexed"
    assert context["index"]["characters"] == len("# hello")
    assert context["attached_to"][0]["target"] == "workspace"
    # No Knowledge or Memory wired: empty lists, not an exception.
    assert context["related_knowledge"] == []
    assert context["related_memories"] == []


@pytest.mark.asyncio
async def test_overview_reports_the_services_own_numbers(env: _Env) -> None:
    """The manager assembles; it does not recompute. A second
    implementation of "how many bytes" is a second answer waiting to
    disagree with the first."""
    workspace_id = (await env.workspaces.create_workspace("W")).id
    await env.files.create_file(workspace_id, "a.md", b"12345")

    overview = await env.file_manager.overview(workspace_id)
    stats = await env.files.workspace_stats(workspace_id)

    assert overview["total_bytes"] == stats["total_bytes"] == 5
    assert overview["file_count"] == stats["file_count"] == 1
    assert [f["filename"] for f in overview["recent_files"]] == ["a.md"]


@pytest.mark.asyncio
async def test_attachment_manager_resolves_files_in_both_directions(env: _Env) -> None:
    workspace_id = (await env.workspaces.create_workspace("W")).id
    note = await env.workspaces.create_note(workspace_id, "Meeting")
    file = await env.files.create_file(workspace_id, "a.txt", b"x")
    await env.attachments.attach(file.id, target="note", target_id=note.id)

    for_target = await env.attachment_manager.for_target("note", note.id)
    assert for_target["count"] == 1
    assert for_target["attachments"][0]["file"]["filename"] == "a.txt"

    for_file = await env.attachment_manager.for_file(file.id)
    assert for_file["count"] == 1
    assert for_file["attached_to"][0]["target"] == "note"
    assert for_file["file"]["filename"] == "a.txt"


@pytest.mark.asyncio
async def test_managers_degrade_when_collaborators_are_missing(env: _Env) -> None:
    """A partially-wired container must yield less context, never an
    AttributeError."""
    workspace_id = (await env.workspaces.create_workspace("W")).id
    file = await env.files.create_file(workspace_id, "a.txt", b"x")

    bare_folders = FolderManager(env.folders)
    bare_files = FileManager(env.files)
    bare_attachments = AttachmentManager(env.attachments)

    tree = await bare_folders.tree(workspace_id)
    assert tree["workspace"] is None
    assert tree["unfiled_files"] == []

    context = await bare_files.context(file.id)
    assert context["file"]["filename"] == "a.txt"
    assert context["folder"] is None
    assert context["workspace"] is None
    assert context["attached_to"] == []

    for_file = await bare_attachments.for_file(file.id)
    assert for_file["file"] is None
    assert for_file["count"] == 0


@pytest.mark.asyncio
async def test_search_falls_back_to_its_own_domain_without_a_search_service(env: _Env) -> None:
    workspace_id = (await env.workspaces.create_workspace("W")).id
    await env.folders.create_folder(workspace_id, "Quarterly")
    await env.files.create_file(workspace_id, "quarterly.md", b"x")

    assert [hit.source for hit in await env.file_manager.search("quarterly")] == ["files"]
    assert [hit.source for hit in await env.folder_manager.search("quarterly")] == ["folders"]


@pytest.mark.asyncio
async def test_search_goes_through_the_shared_service_when_wired(env: _Env) -> None:
    """Wired, the manager must not run its own ranking -- otherwise file
    hits would be scored on a different scale from every other source."""
    from jarvis.services.search_service import SearchService
    from jarvis.services.search_sources import FileSearchSource, FolderSearchSource

    search = SearchService()
    search.register_source(FileSearchSource(env.files))
    search.register_source(FolderSearchSource(env.folders))

    workspace_id = (await env.workspaces.create_workspace("W")).id
    await env.folders.create_folder(workspace_id, "Quarterly")
    await env.files.create_file(workspace_id, "quarterly.md", b"x")

    manager = FileManager(env.files, search_service=search)
    sources = {hit.source for hit in await manager.search("quarterly")}
    assert sources == {"files", "folders"}
