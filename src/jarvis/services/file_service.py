"""File Platform services -- Milestone 11 Task Group C.

``FolderService``, ``FileService`` and ``AttachmentService``, structured
exactly like ``WorkspaceService``: an ``IDatabase`` opened per call via
``db.session()``, a repository constructed inside that session, an
optional ``EventBus``, and a ``search()`` a ``SearchSource`` wraps.

**Why three services in one module.** Task Group B gave each service its
own file because tasks, calendars and reminders share nothing but a
workspace id. These three share the storage root and the path-derivation
rules -- a folder move rewrites its files' paths, and a file's location
is computed from its folder's. Splitting them would either duplicate
those rules or add a fourth module existing only to hold two functions.
The classes stay separate; the file does not.

**Why there is no separate indexer class.** Indexing here is
``extract_text`` -- one pure function in ``domain/files`` -- plus one
upsert. A class wrapping that would own no state and make no decision,
so ``FileService`` calls it directly and exposes ``reindex_file`` /
``reindex_workspace``. When indexing grows a queue, a scheduler or
embeddings it will deserve its own home; it does not have one yet.

**Disk and database are kept in step deliberately.** A write happens
*inside* the session, so a failed write rolls the row back; and the
whole block is wrapped so a failure after the write still unlinks the
bytes. Deletion runs the other way -- row first, then unlink -- because
if the second step fails, unreferenced bytes on disk are recoverable
garbage whereas a row pointing at nothing is a broken entry the user
sees.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from jarvis.core.exceptions import ServiceError
from jarvis.core.interfaces.search import SearchResult
from jarvis.core.logging.logger import get_logger
from jarvis.domain.files.models import (
    ATTACHMENT_TARGETS,
    MAX_EXTRACT_BYTES,
    FilePathError,
    extension_of,
    extract_text,
    guess_mime_type,
    safe_join,
    validate_name,
)
from jarvis.infrastructure.database.repositories import (
    AttachmentRepository,
    FileRepository,
    FolderRepository,
    MetadataRepository,
)

if TYPE_CHECKING:
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.interfaces.database import IDatabase
    from jarvis.infrastructure.database.models import (
        File,
        FileMetadata,
        Folder,
        IndexRecord,
        WorkspaceAttachment,
    )

_logger = get_logger("jarvis.services.files")

#: A file matched on its name is a better hit than one matched only in
#: its extracted body. Deterministic weights, the same posture M10A set
#: for search scoring and Task Groups A and B repeated.
_NAME_SCORE = 1.0
_BODY_SCORE = 0.6

#: Which ``WorkspaceAttachment`` column each target name writes to.
#: ``workspace`` maps to ``None`` because the workspace id is already a
#: required column -- "attached to the workspace itself" is the absence
#: of a narrower target, not a sixth foreign key.
_TARGET_COLUMNS: dict[str, str | None] = {
    "workspace": None,
    "project": "project_id",
    "note": "note_id",
    "task": "task_id",
    "event": "event_id",
    "reminder": "reminder_id",
}

#: The five real columns, in the order the repository takes them.
_NARROW_COLUMNS: tuple[str, ...] = ("project_id", "note_id", "task_id", "event_id", "reminder_id")


#: The ORM class behind each narrow target, resolved lazily so this
#: module keeps importing nothing from ``infrastructure.database.models``
#: at import time.
_TARGET_MODELS: dict[str, str] = {
    "project": "Project",
    "note": "Note",
    "task": "Task",
    "event": "CalendarEvent",
    "reminder": "Reminder",
}


async def _require_target(
    sess: object, target: str, target_id: str | None, workspace_id: str
) -> None:
    """Proves the attachment target exists and lives in the same
    workspace, before the insert.

    Foreign keys already refuse a fabricated parent -- that is the whole
    point of the integrity pass -- but they refuse it as an
    ``IntegrityError`` five layers down, which reaches the caller as a
    500. Checking here turns the same rejection into "that task does not
    exist", the posture ``WorkspaceService.create_project`` already
    takes. This is not a substitute for the constraint; the constraint
    is still what makes the guarantee true.

    The workspace check is the part a foreign key genuinely cannot make:
    ``task_id`` being valid says nothing about the task being in *this*
    file's workspace, and an attachment spanning two would be a link the
    UI could never coherently show.
    """
    from jarvis.infrastructure.database import models as db_models

    if target == "workspace":
        return
    if not target_id:
        return
    model = getattr(db_models, _TARGET_MODELS[target])
    row = await sess.get(model, target_id)  # type: ignore[attr-defined]
    if row is None:
        raise ServiceError(f"{target.capitalize()} {target_id!r} does not exist.")

    owner = getattr(row, "workspace_id", None)
    if owner is None and target == "event":
        # An event's workspace comes through its calendar -- the one
        # target that does not carry the id itself.
        calendar = await sess.get(db_models.Calendar, row.calendar_id)  # type: ignore[attr-defined]
        owner = calendar.workspace_id if calendar is not None else None
    if owner is not None and owner != workspace_id:
        raise ServiceError(
            f"{target.capitalize()} {target_id!r} belongs to a different workspace; "
            "an attachment cannot span two."
        )


def _target_columns(target: str | None, target_id: str | None) -> dict[str, str | None]:
    """Expands ``(target, id)`` into the five column values.

    All ``None`` for ``workspace``, which is the point: a file filed
    against the workspace itself sets no narrow foreign key.
    """
    columns: dict[str, str | None] = dict.fromkeys(_NARROW_COLUMNS)
    column = _TARGET_COLUMNS.get(target or "workspace")
    if column is not None:
        columns[column] = target_id
    return columns


# ---------------------------------------------------------------------------
# Pure path derivation
# ---------------------------------------------------------------------------
def folder_relative_path(parent_path: str, name: str) -> str:
    """A folder's path *within its workspace*.

    Forward slashes regardless of platform: this string is stored,
    compared with ``LIKE`` and returned over REST, so it must not change
    shape between Windows and Linux. Conversion to a real path happens
    once, in ``safe_join``.
    """
    return f"{parent_path}/{name}" if parent_path else name


def file_relative_path(workspace_id: str, folder_path: str, filename: str) -> str:
    """A file's path *within the storage root*, always workspace-first.

    The workspace id leads because two workspaces may legitimately both
    contain ``notes/todo.md``, and a flat root would make one silently
    overwrite the other.
    """
    parts = [workspace_id]
    if folder_path:
        parts.append(folder_path)
    parts.append(filename)
    return "/".join(parts)


def _segments(relative_path: str) -> list[str]:
    return [part for part in relative_path.split("/") if part]


class _StorageMixin:
    """Resolution of a stored relative path to a real one.

    Every service that touches disk goes through here, so containment is
    checked in one place. ``safe_join`` re-validates each segment on
    every call -- the same check that ran at creation. That is redundant
    by design: it makes the guarantee hold for any row regardless of how
    it got written.
    """

    _root: Path

    def _resolve(self, relative_path: str) -> Path:
        try:
            return safe_join(self._root, *_segments(relative_path))
        except FilePathError as exc:
            raise ServiceError(str(exc)) from exc


# ---------------------------------------------------------------------------
# Folders
# ---------------------------------------------------------------------------
class FolderService(_StorageMixin):
    def __init__(
        self,
        *,
        database: IDatabase,
        storage_root: Path,
        event_bus: EventBus | None = None,
    ) -> None:
        self._db = database
        self._root = Path(storage_root)
        self._event_bus = event_bus

    @property
    def storage_root(self) -> Path:
        return self._root

    async def create_folder(
        self, workspace_id: str, name: str, *, parent_folder_id: str | None = None
    ) -> Folder:
        name = _validated(name, "folder name")
        async with self._db.session() as sess:
            folders = FolderRepository(sess)  # type: ignore[arg-type]
            parent_path = ""
            if parent_folder_id is not None:
                parent = await folders.get(parent_folder_id)
                if parent is None:
                    raise ServiceError(f"Folder {parent_folder_id!r} does not exist.")
                if parent.workspace_id != workspace_id:
                    raise ServiceError(
                        f"Folder {parent_folder_id!r} belongs to a different workspace."
                    )
                parent_path = parent.relative_path
            if await folders.find_child(parent_folder_id, workspace_id, name) is not None:
                raise ServiceError(f"A folder named {name!r} already exists here.")

            relative_path = folder_relative_path(parent_path, name)
            folder = await folders.add(
                workspace_id,
                name,
                parent_folder_id=parent_folder_id,
                relative_path=relative_path,
            )
            folder_id = folder.id
            target = self._resolve(file_relative_path(workspace_id, parent_path, name))
            await asyncio.to_thread(target.mkdir, parents=True, exist_ok=True)

        await self._publish(
            folder_id, workspace_id, parent_folder_id or "", relative_path, action="created"
        )
        return await self.require_folder(folder_id)

    async def get_folder(self, folder_id: str) -> Folder | None:
        async with self._db.session() as sess:
            return await FolderRepository(sess).get(folder_id)  # type: ignore[arg-type]

    async def require_folder(self, folder_id: str) -> Folder:
        folder = await self.get_folder(folder_id)
        if folder is None:
            raise ServiceError(f"Folder {folder_id!r} does not exist.")
        return folder

    async def list_folders(
        self,
        *,
        workspace_id: str | None = None,
        parent_folder_id: str | None = None,
        root_only: bool = False,
    ) -> list[Folder]:
        async with self._db.session() as sess:
            return await FolderRepository(sess).list_folders(  # type: ignore[arg-type]
                workspace_id=workspace_id,
                parent_folder_id=parent_folder_id,
                root_only=root_only,
            )

    async def tree(self, workspace_id: str) -> list[dict[str, object]]:
        """A flat, path-ordered listing rather than a nested structure.

        Sorting by ``relative_path`` already yields parents before
        children, so the caller can build whatever nesting its view
        needs, and a deep tree does not become a deeply recursive JSON
        document that some clients cannot stream.
        """
        async with self._db.session() as sess:
            folders = await FolderRepository(sess).list_folders(  # type: ignore[arg-type]
                workspace_id=workspace_id
            )
            counts: dict[str, int] = {}
            files = await FileRepository(sess).list_files(workspace_id=workspace_id)  # type: ignore[arg-type]
            for file in files:
                key = file.folder_id or ""
                counts[key] = counts.get(key, 0) + 1
        rows: list[dict[str, object]] = [
            {
                "id": folder.id,
                "name": folder.name,
                "parent_folder_id": folder.parent_folder_id,
                "relative_path": folder.relative_path,
                "depth": folder.relative_path.count("/"),
                "file_count": counts.get(folder.id, 0),
            }
            for folder in folders
        ]
        return rows

    async def rename_folder(self, folder_id: str, name: str) -> Folder:
        """Renames on disk and rewrites the subtree's cached paths.

        A rename is exactly as capable of introducing ``..`` as a create,
        so the new name goes through the same validation -- historically
        the easy half of this pair to protect unevenly.
        """
        name = _validated(name, "folder name")
        async with self._db.session() as sess:
            folders = FolderRepository(sess)  # type: ignore[arg-type]
            folder = await folders.get(folder_id)
            if folder is None:
                raise ServiceError(f"Folder {folder_id!r} does not exist.")
            if folder.name == name:
                return folder
            if (
                await folders.find_child(folder.parent_folder_id, folder.workspace_id, name)
                is not None
            ):
                raise ServiceError(f"A folder named {name!r} already exists here.")

            old_path = folder.relative_path
            parent_path = old_path.rsplit("/", 1)[0] if "/" in old_path else ""
            new_path = folder_relative_path(parent_path, name)
            workspace_id = folder.workspace_id

            await self._move_on_disk(workspace_id, old_path, new_path)
            folder.name = name
            folder.relative_path = new_path
            affected = await self._rewrite_subtree(sess, folder, old_path, new_path)
            parent_id = folder.parent_folder_id or ""

        await self._publish(
            folder_id,
            workspace_id,
            parent_id,
            new_path,
            action="renamed",
            affected_files=affected,
        )
        return await self.require_folder(folder_id)

    async def move_folder(self, folder_id: str, *, parent_folder_id: str | None) -> Folder:
        """Re-parents a folder, refusing cycles.

        A foreign key cannot say "not one of my own descendants", so the
        check lives here: moving a folder into its own subtree would
        detach that subtree from every root while leaving every row
        individually valid -- invisible to the database and to any
        listing that starts from a root.
        """
        async with self._db.session() as sess:
            folders = FolderRepository(sess)  # type: ignore[arg-type]
            folder = await folders.get(folder_id)
            if folder is None:
                raise ServiceError(f"Folder {folder_id!r} does not exist.")
            workspace_id = folder.workspace_id
            old_path = folder.relative_path

            parent_path = ""
            if parent_folder_id is not None:
                if parent_folder_id == folder_id:
                    raise ServiceError("A folder cannot be moved inside itself.")
                parent = await folders.get(parent_folder_id)
                if parent is None:
                    raise ServiceError(f"Folder {parent_folder_id!r} does not exist.")
                if parent.workspace_id != workspace_id:
                    raise ServiceError("A folder cannot be moved into another workspace.")
                if parent.relative_path == old_path or parent.relative_path.startswith(
                    f"{old_path}/"
                ):
                    raise ServiceError("A folder cannot be moved inside its own subtree.")
                parent_path = parent.relative_path

            new_path = folder_relative_path(parent_path, folder.name)
            if new_path == old_path:
                return folder
            if await folders.find_child(parent_folder_id, workspace_id, folder.name) is not None:
                raise ServiceError(f"A folder named {folder.name!r} already exists there.")

            await self._move_on_disk(workspace_id, old_path, new_path)
            folder.parent_folder_id = parent_folder_id
            folder.relative_path = new_path
            affected = await self._rewrite_subtree(sess, folder, old_path, new_path)

        await self._publish(
            folder_id,
            workspace_id,
            parent_folder_id or "",
            new_path,
            action="moved",
            affected_files=affected,
        )
        return await self.require_folder(folder_id)

    async def delete_folder(self, folder_id: str, *, recursive: bool = False) -> bool:
        """Refuses a non-empty folder unless ``recursive`` is explicit.

        The database cascade would happily take the whole subtree, which
        is the wrong default for a destructive operation on real bytes:
        a user tidying up one empty folder should never lose a hundred
        files because the delete silently meant "and everything under
        it".
        """
        async with self._db.session() as sess:
            folders = FolderRepository(sess)  # type: ignore[arg-type]
            folder = await folders.get(folder_id)
            if folder is None:
                return False
            workspace_id, relative_path = folder.workspace_id, folder.relative_path
            parent_id = folder.parent_folder_id or ""

            descendants = await folders.list_subtree(folder)
            files = FileRepository(sess)  # type: ignore[arg-type]
            contained = await files.list_files(workspace_id=workspace_id, folder_id=folder_id)
            for child in descendants:
                contained.extend(
                    await files.list_files(workspace_id=workspace_id, folder_id=child.id)
                )
            if (descendants or contained) and not recursive:
                raise ServiceError(
                    f"Folder {folder.name!r} is not empty "
                    f"({len(descendants)} subfolder(s), {len(contained)} file(s)); "
                    "pass recursive=true to delete it and everything in it."
                )
            affected = len(contained)
            # The row goes first: an unreferenced directory left on disk
            # is recoverable garbage, a row pointing at nothing is a
            # broken entry the user sees.
            await folders.delete(folder_id)

        target = self._resolve(file_relative_path(workspace_id, relative_path, ""))
        await _remove_tree(target)
        await self._publish(
            folder_id,
            workspace_id,
            parent_id,
            relative_path,
            action="deleted",
            affected_files=affected,
        )
        return True

    async def search_folders(self, query: str, *, top_k: int = 10) -> list[SearchResult]:
        query = (query or "").strip()
        if not query:
            return []
        async with self._db.session() as sess:
            hits = await FolderRepository(sess).search(query, limit=top_k)  # type: ignore[arg-type]
        return [
            SearchResult(
                id=folder.id,
                title=folder.name,
                content=folder.relative_path,
                source="folders",
                score=_NAME_SCORE if query.lower() in folder.name.lower() else _BODY_SCORE,
                uri=f"folder://{folder.id}",
                metadata={
                    "workspace_id": folder.workspace_id,
                    "parent_folder_id": folder.parent_folder_id,
                    "relative_path": folder.relative_path,
                },
            )
            for folder in hits
        ]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    async def _move_on_disk(self, workspace_id: str, old_path: str, new_path: str) -> None:
        source = self._resolve(file_relative_path(workspace_id, old_path, ""))
        destination = self._resolve(file_relative_path(workspace_id, new_path, ""))
        if not await asyncio.to_thread(source.exists):
            # The catalogue is authoritative; a missing directory means
            # the root was edited underneath us. Recreate rather than
            # abort, so one external deletion cannot wedge every later
            # operation on the subtree.
            await asyncio.to_thread(destination.mkdir, parents=True, exist_ok=True)
            return
        if await asyncio.to_thread(destination.exists):
            raise ServiceError(f"{destination.name!r} already exists at the destination.")
        await asyncio.to_thread(destination.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(shutil.move, str(source), str(destination))

    @staticmethod
    async def _rewrite_subtree(sess: object, folder: Folder, old: str, new: str) -> int:
        """Repoints every cached path under *folder* and returns the file
        count.

        The cache is derived, so it is rewritten wholesale rather than
        patched: ``parent_folder_id`` is the truth and this is the one
        place the two are reconciled.

        The descendants are read once, by their *former* prefix, before
        anything is rewritten. Re-querying afterwards would work only
        because autoflush happens to run first, which is not a property
        worth depending on.
        """
        folders = FolderRepository(sess)  # type: ignore[arg-type]
        files = FileRepository(sess)  # type: ignore[arg-type]
        descendants = await folders.list_subtree(
            _PathStub(folder.workspace_id, old)  # type: ignore[arg-type]
        )
        for descendant in descendants:
            descendant.relative_path = new + descendant.relative_path[len(old) :]

        moved = 0
        for target in [folder, *descendants]:
            for file in await files.list_files(
                workspace_id=folder.workspace_id, folder_id=target.id
            ):
                file.relative_path = file_relative_path(
                    folder.workspace_id, target.relative_path, file.filename
                )
                moved += 1
        return moved

    async def _publish(
        self,
        folder_id: str,
        workspace_id: str,
        parent_folder_id: str,
        relative_path: str,
        *,
        action: str,
        affected_files: int = 0,
    ) -> None:
        if self._event_bus is None:
            return
        from jarvis.core.events.events import FolderUpdatedEvent

        await self._event_bus.publish(
            FolderUpdatedEvent(
                folder_id=folder_id,
                workspace_id=workspace_id,
                parent_folder_id=parent_folder_id,
                relative_path=relative_path,
                affected_files=affected_files,
                action=action,
            )
        )


class _PathStub:
    """The two attributes ``FolderRepository.list_subtree`` reads, so a
    subtree can be queried by its *former* path after the folder row has
    already been updated in the session."""

    __slots__ = ("relative_path", "workspace_id")

    def __init__(self, workspace_id: str, relative_path: str) -> None:
        self.workspace_id = workspace_id
        self.relative_path = relative_path


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------
class FileService(_StorageMixin):
    def __init__(
        self,
        *,
        database: IDatabase,
        storage_root: Path,
        event_bus: EventBus | None = None,
        index_enabled: bool = True,
        index_max_bytes: int = MAX_EXTRACT_BYTES,
    ) -> None:
        self._db = database
        self._root = Path(storage_root)
        self._event_bus = event_bus
        self._index_enabled = index_enabled
        self._index_max_bytes = index_max_bytes

    @property
    def storage_root(self) -> Path:
        return self._root

    async def create_file(
        self,
        workspace_id: str,
        filename: str,
        content: bytes,
        *,
        folder_id: str | None = None,
        project_id: str | None = None,
        description: str = "",
        tags: list[str] | None = None,
    ) -> File:
        filename = _validated(filename, "file name")
        written: Path | None = None
        try:
            async with self._db.session() as sess:
                folder_path = await self._folder_path(sess, workspace_id, folder_id)
                files = FileRepository(sess)  # type: ignore[arg-type]
                relative_path = file_relative_path(workspace_id, folder_path, filename)
                if await files.find_by_relative_path(workspace_id, relative_path) is not None:
                    raise ServiceError(f"A file named {filename!r} already exists here.")

                file = await files.add(
                    workspace_id,
                    filename,
                    relative_path,
                    folder_id=folder_id,
                    project_id=project_id,
                    extension=extension_of(filename),
                    mime_type=guess_mime_type(filename),
                    size_bytes=len(content),
                    description=description,
                )
                file_id = file.id
                for tag in _clean_tags(tags):
                    await files.add_tag(file_id, tag)

                # Inside the session on purpose: a failed write rolls the
                # row back instead of leaving a catalogue entry for bytes
                # that were never stored.
                target = self._resolve(relative_path)
                await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)
                await asyncio.to_thread(target.write_bytes, content)
                written = target
                await self._index(sess, file_id, target)
        except Exception:
            # Covers the window the session cannot: a commit failure
            # after the bytes have landed.
            if written is not None:
                await asyncio.to_thread(_unlink_quietly, written)
            raise

        await self._publish(file_id, workspace_id, folder_id or "", relative_path, action="created")
        _logger.info("File created: {} ({} bytes)", relative_path, len(content))
        return await self.require_file(file_id)

    async def get_file(self, file_id: str) -> File | None:
        async with self._db.session() as sess:
            return await FileRepository(sess).get(file_id)  # type: ignore[arg-type]

    async def require_file(self, file_id: str) -> File:
        file = await self.get_file(file_id)
        if file is None:
            raise ServiceError(f"File {file_id!r} does not exist.")
        return file

    async def read_file(self, file_id: str) -> bytes:
        """Re-resolves through ``safe_join`` rather than trusting the
        stored path -- the containment guarantee holds for any row
        however it was written."""
        file = await self.require_file(file_id)
        target = self._resolve(file.relative_path)
        try:
            return await asyncio.to_thread(target.read_bytes)
        except OSError as exc:
            raise ServiceError(f"File {file.filename!r} could not be read: {exc}") from exc

    async def list_files(
        self,
        *,
        workspace_id: str | None = None,
        folder_id: str | None = None,
        project_id: str | None = None,
        extension: str | None = None,
        tag: str | None = None,
        unfiled_only: bool = False,
    ) -> list[File]:
        async with self._db.session() as sess:
            files = FileRepository(sess)  # type: ignore[arg-type]
            if tag is not None:
                return await files.list_by_tag(tag, workspace_id=workspace_id)
            return await files.list_files(
                workspace_id=workspace_id,
                folder_id=folder_id,
                project_id=project_id,
                extension=extension,
                unfiled_only=unfiled_only,
            )

    async def update_file(
        self,
        file_id: str,
        *,
        description: str | None = None,
        project_id: str | None = None,
        clear_project: bool = False,
    ) -> File | None:
        """Metadata only. Renaming and re-filing touch disk and have
        their own methods, so a caller cannot move a file by accident
        while editing its description."""
        async with self._db.session() as sess:
            file = await FileRepository(sess).update(  # type: ignore[arg-type]
                file_id,
                description=description,
                project_id=project_id,
                clear_project=clear_project,
            )
            if file is None:
                return None
            workspace_id, folder_id = file.workspace_id, file.folder_id or ""
            relative_path = file.relative_path
        await self._publish(file_id, workspace_id, folder_id, relative_path, action="updated")
        return await self.get_file(file_id)

    async def rename_file(self, file_id: str, filename: str) -> File:
        filename = _validated(filename, "file name")
        async with self._db.session() as sess:
            files = FileRepository(sess)  # type: ignore[arg-type]
            file = await files.get(file_id)
            if file is None:
                raise ServiceError(f"File {file_id!r} does not exist.")
            if file.filename == filename:
                return file
            workspace_id, folder_id = file.workspace_id, file.folder_id
            folder_path = await self._folder_path(sess, workspace_id, folder_id)
            new_path = file_relative_path(workspace_id, folder_path, filename)
            if await files.find_by_relative_path(workspace_id, new_path) is not None:
                raise ServiceError(f"A file named {filename!r} already exists here.")

            await self._move_on_disk(file.relative_path, new_path)
            file.filename = filename
            file.relative_path = new_path
            # The extension is part of the name, so a rename can change
            # both the MIME type and whether the file is indexable.
            file.extension = extension_of(filename)
            file.mime_type = guess_mime_type(filename)
            await self._index(sess, file_id, self._resolve(new_path))

        await self._publish(file_id, workspace_id, folder_id or "", new_path, action="renamed")
        return await self.require_file(file_id)

    async def move_file(self, file_id: str, *, folder_id: str | None) -> File:
        async with self._db.session() as sess:
            files = FileRepository(sess)  # type: ignore[arg-type]
            file = await files.get(file_id)
            if file is None:
                raise ServiceError(f"File {file_id!r} does not exist.")
            workspace_id = file.workspace_id
            folder_path = await self._folder_path(sess, workspace_id, folder_id)
            new_path = file_relative_path(workspace_id, folder_path, file.filename)
            if new_path == file.relative_path:
                return file
            if await files.find_by_relative_path(workspace_id, new_path) is not None:
                raise ServiceError(f"A file named {file.filename!r} already exists there.")

            await self._move_on_disk(file.relative_path, new_path)
            file.folder_id = folder_id
            file.relative_path = new_path

        await self._publish(file_id, workspace_id, folder_id or "", new_path, action="moved")
        return await self.require_file(file_id)

    async def delete_file(self, file_id: str) -> bool:
        async with self._db.session() as sess:
            files = FileRepository(sess)  # type: ignore[arg-type]
            file = await files.get(file_id)
            if file is None:
                return False
            workspace_id = file.workspace_id
            folder_id = file.folder_id or ""
            relative_path = file.relative_path
            await files.delete(file_id)

        # Row first, unlink second -- see the module docstring.
        await asyncio.to_thread(_unlink_quietly, self._resolve(relative_path))
        await self._publish(file_id, workspace_id, folder_id, relative_path, action="deleted")
        return True

    # ------------------------------------------------------------------
    # Tags and metadata
    # ------------------------------------------------------------------
    async def add_tag(self, file_id: str, tag: str) -> list[str]:
        tag = (tag or "").strip().lower()
        if not tag:
            raise ServiceError("Cannot add an empty tag.")
        async with self._db.session() as sess:
            files = FileRepository(sess)  # type: ignore[arg-type]
            if await files.get(file_id) is None:
                raise ServiceError(f"File {file_id!r} does not exist.")
            await files.add_tag(file_id, tag)
            return await files.tags_for(file_id)

    async def remove_tag(self, file_id: str, tag: str) -> list[str]:
        async with self._db.session() as sess:
            files = FileRepository(sess)  # type: ignore[arg-type]
            await files.remove_tag(file_id, (tag or "").strip().lower())
            return await files.tags_for(file_id)

    async def tags_for(self, file_id: str) -> list[str]:
        async with self._db.session() as sess:
            return await FileRepository(sess).tags_for(file_id)  # type: ignore[arg-type]

    async def set_metadata(self, file_id: str, key: str, value: str) -> FileMetadata:
        key = (key or "").strip()
        if not key:
            raise ServiceError("Cannot set metadata with an empty key.")
        async with self._db.session() as sess:
            if await FileRepository(sess).get(file_id) is None:  # type: ignore[arg-type]
                raise ServiceError(f"File {file_id!r} does not exist.")
            return await MetadataRepository(sess).set_metadata(file_id, key, value)  # type: ignore[arg-type]

    async def list_metadata(self, file_id: str) -> list[FileMetadata]:
        async with self._db.session() as sess:
            return await MetadataRepository(sess).list_metadata(file_id)  # type: ignore[arg-type]

    async def delete_metadata(self, file_id: str, key: str) -> bool:
        async with self._db.session() as sess:
            return await MetadataRepository(sess).delete_metadata(file_id, key)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------
    async def reindex_file(self, file_id: str) -> IndexRecord:
        file = await self.require_file(file_id)
        async with self._db.session() as sess:
            record = await self._index(sess, file_id, self._resolve(file.relative_path))
            status = record.status
        await self._publish(
            file_id,
            file.workspace_id,
            file.folder_id or "",
            file.relative_path,
            action="indexed",
        )
        _logger.debug("Indexed {}: {}", file.relative_path, status)
        return record

    async def reindex_workspace(self, workspace_id: str) -> dict[str, int]:
        """Re-reads every file in a workspace and returns per-status
        counts. Synchronous and unbounded on purpose -- a queue would be
        a second scheduler, and M7 Phase 6 owns that."""
        async with self._db.session() as sess:
            files = await FileRepository(sess).list_files(workspace_id=workspace_id)  # type: ignore[arg-type]
            for file in files:
                await self._index(sess, file.id, self._resolve(file.relative_path))
            return await MetadataRepository(sess).counts_by_status(workspace_id)  # type: ignore[arg-type]

    async def index_record(self, file_id: str) -> IndexRecord | None:
        async with self._db.session() as sess:
            return await MetadataRepository(sess).get_index(file_id)  # type: ignore[arg-type]

    async def workspace_stats(self, workspace_id: str) -> dict[str, object]:
        async with self._db.session() as sess:
            files = FileRepository(sess)  # type: ignore[arg-type]
            by_extension = await files.counts_by_extension(workspace_id)
            total_bytes = await files.total_size(workspace_id)
            index_counts = await MetadataRepository(sess).counts_by_status(workspace_id)  # type: ignore[arg-type]
            folder_count = len(
                await FolderRepository(sess).list_folders(workspace_id=workspace_id)  # type: ignore[arg-type]
            )
        return {
            "workspace_id": workspace_id,
            "file_count": sum(by_extension.values()),
            "folder_count": folder_count,
            "total_bytes": total_bytes,
            "by_extension": by_extension,
            "index_status": index_counts,
        }

    # ------------------------------------------------------------------
    # Search hook
    # ------------------------------------------------------------------
    async def search_files(self, query: str, *, top_k: int = 10) -> list[SearchResult]:
        query = (query or "").strip()
        if not query:
            return []
        async with self._db.session() as sess:
            files = FileRepository(sess)  # type: ignore[arg-type]
            metadata = MetadataRepository(sess)  # type: ignore[arg-type]
            hits = await files.search(query, limit=top_k)
            tags = {file.id: await files.tags_for(file.id) for file in hits}
            records = {file.id: await metadata.get_index(file.id) for file in hits}

        needle = query.lower()
        results: list[SearchResult] = []
        for file in hits:
            matched_name = needle in file.filename.lower()
            record = records.get(file.id)
            body = record.content_text if record is not None else ""
            results.append(
                SearchResult(
                    id=file.id,
                    title=file.filename,
                    # The description if there is one, otherwise the
                    # indexed body -- a snippet the user can recognise,
                    # not a path they already knew.
                    content=file.description or body[:500],
                    source="files",
                    score=_NAME_SCORE if matched_name else _BODY_SCORE,
                    uri=f"file://{file.id}",
                    metadata={
                        "workspace_id": file.workspace_id,
                        "folder_id": file.folder_id,
                        "project_id": file.project_id,
                        "relative_path": file.relative_path,
                        "mime_type": file.mime_type,
                        "size_bytes": file.size_bytes,
                        "tags": tags.get(file.id, []),
                        "index_status": record.status if record is not None else "unindexed",
                    },
                )
            )
        return results

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    async def _folder_path(self, sess: object, workspace_id: str, folder_id: str | None) -> str:
        """The containing folder's workspace-relative path, validating
        that the folder exists and belongs to the same workspace."""
        if folder_id is None:
            return ""
        folder = await FolderRepository(sess).get(folder_id)  # type: ignore[arg-type]
        if folder is None:
            raise ServiceError(f"Folder {folder_id!r} does not exist.")
        if folder.workspace_id != workspace_id:
            raise ServiceError(f"Folder {folder_id!r} belongs to a different workspace.")
        return folder.relative_path

    async def _move_on_disk(self, old_path: str, new_path: str) -> None:
        source = self._resolve(old_path)
        destination = self._resolve(new_path)
        if not await asyncio.to_thread(source.exists):
            raise ServiceError(f"The stored file for {old_path!r} is missing from disk.")
        if await asyncio.to_thread(destination.exists):
            raise ServiceError(f"{destination.name!r} already exists at the destination.")
        await asyncio.to_thread(destination.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(shutil.move, str(source), str(destination))

    async def _index(self, sess: object, file_id: str, path: Path) -> IndexRecord:
        """Extract and record. Never raises for an unreadable file --
        ``extract_text`` reports ``failed`` and the record says so, which
        is the whole reason ``status`` has four values."""
        metadata = MetadataRepository(sess)  # type: ignore[arg-type]
        if not self._index_enabled:
            return await metadata.upsert_index(
                file_id, content_text="", status="skipped", detail="Indexing is disabled."
            )
        text, status = await asyncio.to_thread(extract_text, path, max_bytes=self._index_max_bytes)
        detail = {
            "skipped": "No text extractor for this file type.",
            "truncated": f"Indexed the first {self._index_max_bytes} bytes.",
            "failed": "The file could not be read.",
        }.get(status, "")
        return await metadata.upsert_index(file_id, content_text=text, status=status, detail=detail)

    async def _publish(
        self,
        file_id: str,
        workspace_id: str,
        folder_id: str,
        relative_path: str,
        *,
        action: str,
    ) -> None:
        if self._event_bus is None:
            return
        from jarvis.core.events.events import FileUpdatedEvent

        await self._event_bus.publish(
            FileUpdatedEvent(
                file_id=file_id,
                workspace_id=workspace_id,
                folder_id=folder_id,
                relative_path=relative_path,
                action=action,
            )
        )


# ---------------------------------------------------------------------------
# Attachments
# ---------------------------------------------------------------------------
class AttachmentService:
    """Attaches catalogued files to workspace entities.

    No storage root: an attachment is a link between two rows that
    already exist, so this service never touches disk. It is the one
    place ``WorkspaceAttachment``'s "at most one narrow target" rule is
    enforced -- five nullable columns can each be checked by the
    database, but "no more than one of them is set" is a statement about
    the row as a whole.
    """

    def __init__(
        self,
        *,
        database: IDatabase,
        event_bus: EventBus | None = None,
    ) -> None:
        self._db = database
        self._event_bus = event_bus

    async def attach(
        self,
        file_id: str,
        *,
        target: str = "workspace",
        target_id: str | None = None,
        caption: str = "",
    ) -> WorkspaceAttachment:
        if target not in ATTACHMENT_TARGETS:
            raise ServiceError(
                f"Unknown attachment target {target!r}; allowed: {list(ATTACHMENT_TARGETS)}."
            )
        column = _TARGET_COLUMNS[target]
        if column is None and target_id:
            raise ServiceError(
                "A workspace attachment takes no target id -- the file's own "
                "workspace is the target."
            )
        if column is not None and not target_id:
            raise ServiceError(f"Attaching to a {target} requires a target id.")

        async with self._db.session() as sess:
            file = await FileRepository(sess).get(file_id)  # type: ignore[arg-type]
            if file is None:
                raise ServiceError(f"File {file_id!r} does not exist.")
            workspace_id = file.workspace_id
            await _require_target(sess, target, target_id, workspace_id)
            columns = _target_columns(target, target_id)
            attachment = await AttachmentRepository(sess).add(  # type: ignore[arg-type]
                workspace_id,
                file_id,
                caption=caption,
                project_id=columns["project_id"],
                note_id=columns["note_id"],
                task_id=columns["task_id"],
                event_id=columns["event_id"],
                reminder_id=columns["reminder_id"],
            )
            attachment_id = attachment.id

        await self._publish(
            attachment_id,
            workspace_id,
            file_id,
            target,
            target_id or "",
            action="attached",
        )
        return await self.require_attachment(attachment_id)

    async def get_attachment(self, attachment_id: str) -> WorkspaceAttachment | None:
        async with self._db.session() as sess:
            return await AttachmentRepository(sess).get(attachment_id)  # type: ignore[arg-type]

    async def require_attachment(self, attachment_id: str) -> WorkspaceAttachment:
        attachment = await self.get_attachment(attachment_id)
        if attachment is None:
            raise ServiceError(f"Attachment {attachment_id!r} does not exist.")
        return attachment

    async def list_attachments(
        self,
        *,
        workspace_id: str | None = None,
        file_id: str | None = None,
        target: str | None = None,
        target_id: str | None = None,
    ) -> list[WorkspaceAttachment]:
        if target is not None and target not in ATTACHMENT_TARGETS:
            raise ServiceError(f"Unknown attachment target {target!r}.")
        columns = (
            _target_columns(target, target_id)
            if target is not None
            else dict.fromkeys(_NARROW_COLUMNS)
        )
        async with self._db.session() as sess:
            return await AttachmentRepository(sess).list_attachments(  # type: ignore[arg-type]
                workspace_id=workspace_id,
                file_id=file_id,
                project_id=columns["project_id"],
                note_id=columns["note_id"],
                task_id=columns["task_id"],
                event_id=columns["event_id"],
                reminder_id=columns["reminder_id"],
            )

    async def detach(self, attachment_id: str) -> bool:
        async with self._db.session() as sess:
            attachments = AttachmentRepository(sess)  # type: ignore[arg-type]
            attachment = await attachments.get(attachment_id)
            if attachment is None:
                return False
            workspace_id, file_id = attachment.workspace_id, attachment.file_id
            target, target_id = describe_target(attachment)
            await attachments.delete(attachment_id)
        await self._publish(
            attachment_id, workspace_id, file_id, target, target_id, action="detached"
        )
        return True

    async def search_attachments(self, query: str, *, top_k: int = 10) -> list[SearchResult]:
        query = (query or "").strip()
        if not query:
            return []
        async with self._db.session() as sess:
            attachments = AttachmentRepository(sess)  # type: ignore[arg-type]
            hits = await attachments.search(query, limit=top_k)
            files = FileRepository(sess)  # type: ignore[arg-type]
            names = {hit.id: await files.get(hit.file_id) for hit in hits}

        results: list[SearchResult] = []
        for hit in hits:
            file = names.get(hit.id)
            target, target_id = describe_target(hit)
            filename = file.filename if file is not None else hit.file_id
            results.append(
                SearchResult(
                    id=hit.id,
                    title=filename,
                    content=hit.caption,
                    source="attachments",
                    score=_NAME_SCORE if query.lower() in hit.caption.lower() else _BODY_SCORE,
                    uri=f"attachment://{hit.id}",
                    metadata={
                        "workspace_id": hit.workspace_id,
                        "file_id": hit.file_id,
                        "target": target,
                        "target_id": target_id,
                    },
                )
            )
        return results

    async def _publish(
        self,
        attachment_id: str,
        workspace_id: str,
        file_id: str,
        target: str,
        target_id: str,
        *,
        action: str,
    ) -> None:
        if self._event_bus is None:
            return
        from jarvis.core.events.events import AttachmentUpdatedEvent

        await self._event_bus.publish(
            AttachmentUpdatedEvent(
                attachment_id=attachment_id,
                workspace_id=workspace_id,
                file_id=file_id,
                target=target,
                target_id=target_id,
                action=action,
            )
        )


def describe_target(attachment: WorkspaceAttachment) -> tuple[str, str]:
    """Flattens the five nullable foreign keys into ``(target, id)``.

    The row keeps real constraints; every reader wants the pair. Public
    because the REST layer serialises it too, and two implementations of
    the same collapse would drift.
    """
    for name, column in _TARGET_COLUMNS.items():
        if column is None:
            continue
        value = getattr(attachment, column, None)
        if value:
            return name, str(value)
    return "workspace", attachment.workspace_id


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def _validated(name: str, label: str) -> str:
    """``validate_name`` translated into the service layer's error type,
    so a caller catches ``ServiceError`` and not two exception families."""
    try:
        return validate_name(name, label=label)
    except FilePathError as exc:
        raise ServiceError(str(exc)) from exc


def _clean_tags(tags: list[str] | None) -> list[str]:
    seen: list[str] = []
    for raw in tags or []:
        tag = (raw or "").strip().lower()
        if tag and tag not in seen:
            seen.append(tag)
    return seen


def _unlink_quietly(path: Path) -> None:
    """Best-effort removal. A failure here leaves unreferenced bytes,
    which is recoverable; raising would fail an operation the catalogue
    has already completed."""
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:  # pragma: no cover - platform-specific
        _logger.warning("Could not remove {}: {}", path, exc)


async def _remove_tree(path: Path) -> None:
    """Best-effort, same reasoning as :func:`_unlink_quietly`: the
    catalogue row is already gone, so a directory that will not delete
    is garbage rather than a failure to report to the caller."""
    await asyncio.to_thread(shutil.rmtree, path, ignore_errors=True)
