"""File Platform managers -- Milestone 11 Task Group C.

``FolderManager`` / ``FileManager`` / ``AttachmentManager``: the
read-side coordinators for the file domain, following
``WorkspaceManager`` and the Task Group B managers exactly -- they
**collect and never compute**, hold no state, persist nothing, and treat
every collaborator except their own service as optional so a
partially-wired container degrades to less context rather than failing.

**Why three, and why any at all.** The services own one domain and one
storage root; the moment they also reach into Workspace, Knowledge,
Search and Memory they own four more subsystems' failure modes. Each
manager answers a question no single service call does:

* :class:`FolderManager` -- *what does this workspace's tree look like*:
  folders, their depths and their file counts, plus the unfiled files
  that belong to no folder and would otherwise be invisible in a
  tree view.
* :class:`FileManager` -- *what is this file, and what else relates to
  it*: the row, its tags, its index status, what it is attached to, and
  the neighbouring subsystems' hits for its own text.
* :class:`AttachmentManager` -- *what is attached to this thing*, and
  the reverse: what a given file is attached to across five entity
  types.

They share the module-level :func:`related_items` helper by import rather
than a base class -- composition over inheritance, the rule
`ARCHITECTURE.md` §1 states.

**What these do not do.** No indexing (that is ``FileService``), no
storage (the services own the root), no lifecycle, no scheduling. A
manager that wrote something would stop being a read-side coordinator
and start being a second service for the same tables.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from jarvis.core.logging.logger import get_logger
from jarvis.services.file_service import describe_target
from jarvis.services.productivity_managers import related_items

if TYPE_CHECKING:
    from jarvis.core.interfaces.search import SearchResult
    from jarvis.services.file_service import (
        AttachmentService,
        FileService,
        FolderService,
    )
    from jarvis.services.knowledge_service import KnowledgeService
    from jarvis.services.memory_service import MemoryService
    from jarvis.services.search_service import SearchService
    from jarvis.services.workspace_service import WorkspaceService

_logger = get_logger("jarvis.services.file_managers")


class FolderManager:
    """Composes ``FolderService`` with ``FileService`` and Workspace.
    Answers "what does this tree look like"."""

    def __init__(
        self,
        folder_service: FolderService,
        *,
        file_service: FileService | None = None,
        workspace_service: WorkspaceService | None = None,
        search_service: SearchService | None = None,
    ) -> None:
        self._folders = folder_service
        self._files = file_service
        self._workspaces = workspace_service
        self._search = search_service

    async def tree(self, workspace_id: str) -> dict[str, Any]:
        """The workspace's folder tree plus its unfiled files.

        Unfiled files are included because a tree that only shows what
        is inside a folder hides everything that is not, and "I uploaded
        it and it vanished" is the bug that produces. They are the
        normal case, not an error -- the same posture ``Note`` takes
        toward projects.
        """
        rows = await self._folders.tree(workspace_id)
        workspace: dict[str, Any] | None = None
        if self._workspaces is not None:
            found = await self._workspaces.get_workspace(workspace_id)
            if found is not None:
                workspace = {"id": found.id, "name": found.name}

        unfiled: list[dict[str, Any]] = []
        if self._files is not None:
            unfiled = [
                _file_row(file)
                for file in await self._files.list_files(
                    workspace_id=workspace_id, unfiled_only=True
                )
            ]

        return {
            "workspace_id": workspace_id,
            "workspace": workspace,
            "folders": rows,
            "unfiled_files": unfiled,
            "folder_count": len(rows),
        }

    async def contents(self, folder_id: str) -> dict[str, Any]:
        """One folder's immediate children -- subfolders and files.

        Immediate, not recursive: a folder view shows one level, and
        returning a subtree would make opening the root of a large
        workspace load everything in it.
        """
        folder = await self._folders.require_folder(folder_id)
        subfolders = await self._folders.list_folders(
            workspace_id=folder.workspace_id, parent_folder_id=folder_id
        )
        files = (
            await self._files.list_files(workspace_id=folder.workspace_id, folder_id=folder_id)
            if self._files is not None
            else []
        )
        return {
            "folder": _folder_row(folder),
            "subfolders": [_folder_row(child) for child in subfolders],
            "files": [_file_row(file) for file in files],
        }

    async def search(self, query: str, *, top_k: int = 10) -> list[SearchResult]:
        """Through the shared ``SearchService`` when wired, so results
        are ranked alongside every other source; otherwise this domain
        alone -- narrower, never wrong."""
        if self._search is not None:
            return await self._search.search(query, top_k=top_k)
        return await self._folders.search_folders(query, top_k=top_k)


class FileManager:
    """Composes ``FileService`` with Folders, Attachments, Workspace,
    Knowledge, Search and Memory. Answers "what is this file"."""

    def __init__(
        self,
        file_service: FileService,
        *,
        folder_service: FolderService | None = None,
        attachment_service: AttachmentService | None = None,
        workspace_service: WorkspaceService | None = None,
        knowledge_service: KnowledgeService | None = None,
        search_service: SearchService | None = None,
        memory_service: MemoryService | None = None,
    ) -> None:
        self._files = file_service
        self._folders = folder_service
        self._attachments = attachment_service
        self._workspaces = workspace_service
        self._knowledge = knowledge_service
        self._search = search_service
        self._memory = memory_service

    async def context(self, file_id: str) -> dict[str, Any]:
        """One file plus everything the neighbouring subsystems relate
        to it.

        Relatedness is the file's own name and description used as a
        query against Knowledge and Memory -- deterministic text
        matching, the same approach ``WorkspaceManager.context`` and
        ``TaskManager.context`` take, and honest about being that rather
        than a learned association. Task Group D replaces this method's
        body without changing its shape.
        """
        file = await self._files.require_file(file_id)
        record = await self._files.index_record(file_id)
        query = f"{file.filename} {file.description}".strip()

        folder: dict[str, Any] | None = None
        if file.folder_id and self._folders is not None:
            found = await self._folders.get_folder(file.folder_id)
            if found is not None:
                folder = _folder_row(found)

        workspace: dict[str, Any] | None = None
        if self._workspaces is not None:
            found_workspace = await self._workspaces.get_workspace(file.workspace_id)
            if found_workspace is not None:
                workspace = {"id": found_workspace.id, "name": found_workspace.name}

        attached_to: list[dict[str, Any]] = []
        if self._attachments is not None:
            attached_to = [
                _attachment_row(attachment)
                for attachment in await self._attachments.list_attachments(file_id=file_id)
            ]

        return {
            "file": _file_row(file),
            "tags": await self._files.tags_for(file_id),
            "folder": folder,
            "workspace": workspace,
            "attached_to": attached_to,
            "index": {
                "status": record.status if record is not None else "unindexed",
                "detail": record.detail if record is not None else "",
                "indexed_at": (
                    record.indexed_at.isoformat()
                    if record is not None and record.indexed_at
                    else None
                ),
                "characters": len(record.content_text) if record is not None else 0,
            },
            "related_knowledge": await related_items(self._knowledge, query, kind="knowledge"),
            "related_memories": await related_items(self._memory, query, kind="memory"),
        }

    async def overview(self, workspace_id: str) -> dict[str, Any]:
        """Counts, sizes and index health for one workspace.

        Collected from ``FileService.workspace_stats`` rather than
        recomputed here -- the manager's job is to assemble, and a
        second implementation of "how many bytes" would be a second
        answer waiting to disagree with the first.
        """
        stats = await self._files.workspace_stats(workspace_id)
        recent = await self._files.list_files(workspace_id=workspace_id)
        return {
            **stats,
            "recent_files": [_file_row(file) for file in recent[:10]],
        }

    async def search(self, query: str, *, top_k: int = 10) -> list[SearchResult]:
        if self._search is not None:
            return await self._search.search(query, top_k=top_k)
        return await self._files.search_files(query, top_k=top_k)


class AttachmentManager:
    """Composes ``AttachmentService`` with ``FileService``. Answers
    "what is attached to this, and what is this attached to"."""

    def __init__(
        self,
        attachment_service: AttachmentService,
        *,
        file_service: FileService | None = None,
        workspace_service: WorkspaceService | None = None,
        search_service: SearchService | None = None,
    ) -> None:
        self._attachments = attachment_service
        self._files = file_service
        self._workspaces = workspace_service
        self._search = search_service

    async def for_target(
        self, target: str, target_id: str, *, workspace_id: str | None = None
    ) -> dict[str, Any]:
        """Everything attached to one entity, with each file resolved.

        A caller showing a task's attachments needs filenames and sizes,
        not five foreign keys and a file id -- resolving them here is
        exactly the collection this class exists for.
        """
        attachments = await self._attachments.list_attachments(
            workspace_id=workspace_id, target=target, target_id=target_id
        )
        rows: list[dict[str, Any]] = []
        for attachment in attachments:
            row = _attachment_row(attachment)
            if self._files is not None:
                file = await self._files.get_file(attachment.file_id)
                row["file"] = _file_row(file) if file is not None else None
            rows.append(row)
        return {
            "target": target,
            "target_id": target_id,
            "workspace_id": workspace_id,
            "attachments": rows,
            "count": len(rows),
        }

    async def for_file(self, file_id: str) -> dict[str, Any]:
        """The reverse view: every place one file is attached."""
        attachments = await self._attachments.list_attachments(file_id=file_id)
        file_row: dict[str, Any] | None = None
        if self._files is not None:
            file = await self._files.get_file(file_id)
            file_row = _file_row(file) if file is not None else None
        return {
            "file_id": file_id,
            "file": file_row,
            "attached_to": [_attachment_row(attachment) for attachment in attachments],
            "count": len(attachments),
        }

    async def search(self, query: str, *, top_k: int = 10) -> list[SearchResult]:
        if self._search is not None:
            return await self._search.search(query, top_k=top_k)
        return await self._attachments.search_attachments(query, top_k=top_k)


# ---------------------------------------------------------------------------
# Row shapes
# ---------------------------------------------------------------------------
def _folder_row(folder: Any) -> dict[str, Any]:
    return {
        "id": folder.id,
        "name": folder.name,
        "workspace_id": folder.workspace_id,
        "parent_folder_id": folder.parent_folder_id,
        "relative_path": folder.relative_path,
    }


def _file_row(file: Any) -> dict[str, Any]:
    return {
        "id": file.id,
        "filename": file.filename,
        "workspace_id": file.workspace_id,
        "folder_id": file.folder_id,
        "project_id": file.project_id,
        "relative_path": file.relative_path,
        "extension": file.extension,
        "mime_type": file.mime_type,
        "size_bytes": file.size_bytes,
        "description": file.description,
    }


def _attachment_row(attachment: Any) -> dict[str, Any]:
    target, target_id = describe_target(attachment)
    return {
        "id": attachment.id,
        "workspace_id": attachment.workspace_id,
        "file_id": attachment.file_id,
        "target": target,
        "target_id": target_id,
        "caption": attachment.caption,
    }
