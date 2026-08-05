"""File Platform repositories -- Milestone 11 Task Group C.

``FolderRepository`` / ``FileRepository`` / ``AttachmentRepository`` /
``MetadataRepository``, following ``WorkspaceRepository`` and
``productivity_repository`` exactly: constructed with an
``AsyncSession``, no transaction management of its own, ``flush()``
rather than ``commit()`` after an insert, and per-entity method names
(``list_files``, not ``list``) so a method never shadows the builtin in
its own return annotation.

``MetadataRepository`` owns both ``file_metadata`` and
``file_index_records`` -- the two derived-fact tables. They are written
by the same indexing pass and read by the same callers, and splitting
them would give one of the two a class whose every method takes a
``file_id`` and nothing else.

**Foreign keys are enforced** (see ``sqlite_client.py``), so an insert
naming a parent that does not exist now raises rather than writing a
dangling row. Nothing here works around that: the services validate
parents up front so the caller gets a clear message instead of an
``IntegrityError``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from jarvis.infrastructure.database.models import (
    File,
    FileMetadata,
    FileTag,
    Folder,
    IndexRecord,
    WorkspaceAttachment,
)


class FolderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(
        self,
        workspace_id: str,
        name: str,
        *,
        parent_folder_id: str | None = None,
        relative_path: str = "",
    ) -> Folder:
        folder = Folder(
            workspace_id=workspace_id,
            name=name,
            parent_folder_id=parent_folder_id,
            relative_path=relative_path,
        )
        self._s.add(folder)
        await self._s.flush()
        return folder

    async def get(self, folder_id: str) -> Folder | None:
        return await self._s.get(Folder, folder_id)

    async def list_folders(
        self,
        *,
        workspace_id: str | None = None,
        parent_folder_id: str | None = None,
        root_only: bool = False,
        limit: int = 500,
        offset: int = 0,
    ) -> list[Folder]:
        stmt = select(Folder).order_by(Folder.relative_path.asc()).limit(limit).offset(offset)
        if workspace_id is not None:
            stmt = stmt.where(Folder.workspace_id == workspace_id)
        if root_only:
            stmt = stmt.where(Folder.parent_folder_id.is_(None))
        elif parent_folder_id is not None:
            stmt = stmt.where(Folder.parent_folder_id == parent_folder_id)
        return list((await self._s.execute(stmt)).scalars().all())

    async def list_subtree(self, folder: Folder, *, limit: int = 500) -> list[Folder]:
        """Every descendant, via the denormalized ``relative_path``
        prefix -- one indexed ``LIKE`` instead of a recursive walk.

        The prefix ends with ``/`` so ``docs/`` cannot match
        ``docs-archive/``, which is the classic way this optimisation
        goes wrong.
        """
        prefix = f"{folder.relative_path}/"
        stmt = (
            select(Folder)
            .where(
                Folder.workspace_id == folder.workspace_id,
                Folder.relative_path.like(f"{prefix}%"),
            )
            .order_by(Folder.relative_path.asc())
            .limit(limit)
        )
        return list((await self._s.execute(stmt)).scalars().all())

    async def find_child(
        self, parent_id: str | None, workspace_id: str, name: str
    ) -> Folder | None:
        """Sibling-name lookup, so a duplicate is refused before the
        filesystem is touched."""
        stmt = select(Folder).where(
            Folder.workspace_id == workspace_id,
            Folder.name == name,
            (
                Folder.parent_folder_id.is_(None)
                if parent_id is None
                else Folder.parent_folder_id == parent_id
            ),
        )
        return (await self._s.execute(stmt)).scalars().first()

    async def update(
        self,
        folder_id: str,
        *,
        name: str | None = None,
        parent_folder_id: str | None = None,
        relative_path: str | None = None,
        detach_parent: bool = False,
    ) -> Folder | None:
        folder = await self.get(folder_id)
        if folder is None:
            return None
        if name is not None:
            folder.name = name
        if detach_parent:
            folder.parent_folder_id = None
        elif parent_folder_id is not None:
            folder.parent_folder_id = parent_folder_id
        if relative_path is not None:
            folder.relative_path = relative_path
        return folder

    async def delete(self, folder_id: str) -> bool:
        folder = await self.get(folder_id)
        if folder is None:
            return False
        await self._s.delete(folder)
        return True

    async def search(self, query: str, *, limit: int = 10) -> list[Folder]:
        pattern = f"%{query.lower()}%"
        stmt = (
            select(Folder)
            .where(
                or_(
                    func.lower(Folder.name).like(pattern),
                    func.lower(Folder.relative_path).like(pattern),
                )
            )
            .order_by(Folder.updated_at.desc())
            .limit(limit)
        )
        return list((await self._s.execute(stmt)).scalars().all())


class FileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(
        self,
        workspace_id: str,
        filename: str,
        relative_path: str,
        *,
        folder_id: str | None = None,
        project_id: str | None = None,
        extension: str = "",
        mime_type: str = "application/octet-stream",
        size_bytes: int = 0,
        description: str = "",
    ) -> File:
        file = File(
            workspace_id=workspace_id,
            folder_id=folder_id,
            project_id=project_id,
            filename=filename,
            relative_path=relative_path,
            extension=extension,
            mime_type=mime_type,
            size_bytes=size_bytes,
            description=description,
        )
        self._s.add(file)
        await self._s.flush()
        return file

    async def get(self, file_id: str) -> File | None:
        return await self._s.get(File, file_id)

    async def find_by_relative_path(self, workspace_id: str, relative_path: str) -> File | None:
        stmt = select(File).where(
            File.workspace_id == workspace_id, File.relative_path == relative_path
        )
        return (await self._s.execute(stmt)).scalars().first()

    async def list_files(
        self,
        *,
        workspace_id: str | None = None,
        folder_id: str | None = None,
        project_id: str | None = None,
        extension: str | None = None,
        unfiled_only: bool = False,
        limit: int = 500,
        offset: int = 0,
    ) -> list[File]:
        stmt = select(File).order_by(File.filename.asc()).limit(limit).offset(offset)
        if workspace_id is not None:
            stmt = stmt.where(File.workspace_id == workspace_id)
        if unfiled_only:
            stmt = stmt.where(File.folder_id.is_(None))
        elif folder_id is not None:
            stmt = stmt.where(File.folder_id == folder_id)
        if project_id is not None:
            stmt = stmt.where(File.project_id == project_id)
        if extension is not None:
            stmt = stmt.where(File.extension == extension)
        return list((await self._s.execute(stmt)).scalars().all())

    async def list_by_tag(
        self, tag: str, *, workspace_id: str | None = None, limit: int = 500
    ) -> list[File]:
        """A real join, not a ``LIKE`` over serialized JSON -- which is
        why file tags are their own table (see ``FileTag``)."""
        stmt = (
            select(File)
            .join(FileTag, FileTag.file_id == File.id)
            .where(FileTag.tag == tag)
            .order_by(File.filename.asc())
            .limit(limit)
        )
        if workspace_id is not None:
            stmt = stmt.where(File.workspace_id == workspace_id)
        return list((await self._s.execute(stmt)).scalars().all())

    async def update(
        self,
        file_id: str,
        *,
        filename: str | None = None,
        relative_path: str | None = None,
        folder_id: str | None = None,
        project_id: str | None = None,
        extension: str | None = None,
        mime_type: str | None = None,
        size_bytes: int | None = None,
        description: str | None = None,
        detach_folder: bool = False,
        clear_project: bool = False,
    ) -> File | None:
        file = await self.get(file_id)
        if file is None:
            return None
        if filename is not None:
            file.filename = filename
        if relative_path is not None:
            file.relative_path = relative_path
        if detach_folder:
            file.folder_id = None
        elif folder_id is not None:
            file.folder_id = folder_id
        if clear_project:
            file.project_id = None
        elif project_id is not None:
            file.project_id = project_id
        if extension is not None:
            file.extension = extension
        if mime_type is not None:
            file.mime_type = mime_type
        if size_bytes is not None:
            file.size_bytes = size_bytes
        if description is not None:
            file.description = description
        return file

    async def delete(self, file_id: str) -> bool:
        file = await self.get(file_id)
        if file is None:
            return False
        await self._s.delete(file)
        return True

    async def search(self, query: str, *, limit: int = 10) -> list[File]:
        """Name, description, tags *and* extracted body -- the last via
        a join onto the index record, which is the whole point of having
        one."""
        pattern = f"%{query.lower()}%"
        stmt = (
            select(File)
            .outerjoin(IndexRecord, IndexRecord.file_id == File.id)
            .outerjoin(FileTag, FileTag.file_id == File.id)
            .where(
                or_(
                    func.lower(File.filename).like(pattern),
                    func.lower(File.description).like(pattern),
                    func.lower(File.relative_path).like(pattern),
                    func.lower(IndexRecord.content_text).like(pattern),
                    func.lower(FileTag.tag).like(pattern),
                )
            )
            .distinct()
            .limit(limit)
        )
        return list((await self._s.execute(stmt)).scalars().all())

    # ---- Tags --------------------------------------------------------
    async def add_tag(self, file_id: str, tag: str) -> None:
        """Idempotent -- re-tagging is a no-op rather than a primary-key
        violation, matching ``KnowledgeRepository.link_entity_memory``."""
        existing = await self._s.get(FileTag, {"file_id": file_id, "tag": tag})
        if existing is None:
            self._s.add(FileTag(file_id=file_id, tag=tag))
            await self._s.flush()

    async def remove_tag(self, file_id: str, tag: str) -> bool:
        existing = await self._s.get(FileTag, {"file_id": file_id, "tag": tag})
        if existing is None:
            return False
        await self._s.delete(existing)
        return True

    async def tags_for(self, file_id: str) -> list[str]:
        stmt = select(FileTag.tag).where(FileTag.file_id == file_id).order_by(FileTag.tag.asc())
        return list((await self._s.execute(stmt)).scalars().all())

    async def counts_by_extension(self, workspace_id: str) -> dict[str, int]:
        stmt = (
            select(File.extension, func.count())
            .where(File.workspace_id == workspace_id)
            .group_by(File.extension)
        )
        return {(row[0] or ""): int(row[1]) for row in (await self._s.execute(stmt)).all()}

    async def total_size(self, workspace_id: str) -> int:
        value = await self._s.scalar(
            select(func.coalesce(func.sum(File.size_bytes), 0)).where(
                File.workspace_id == workspace_id
            )
        )
        return int(value or 0)


class MetadataRepository:
    """``file_metadata`` and ``file_index_records`` -- the two derived
    tables, written by the same indexing pass."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def set_metadata(self, file_id: str, key: str, value: str) -> FileMetadata:
        existing = await self._s.get(FileMetadata, {"file_id": file_id, "key": key})
        if existing is not None:
            existing.value = value
            return existing
        row = FileMetadata(file_id=file_id, key=key, value=value)
        self._s.add(row)
        await self._s.flush()
        return row

    async def get_metadata(self, file_id: str, key: str) -> FileMetadata | None:
        return await self._s.get(FileMetadata, {"file_id": file_id, "key": key})

    async def list_metadata(self, file_id: str) -> list[FileMetadata]:
        stmt = (
            select(FileMetadata)
            .where(FileMetadata.file_id == file_id)
            .order_by(FileMetadata.key.asc())
        )
        return list((await self._s.execute(stmt)).scalars().all())

    async def delete_metadata(self, file_id: str, key: str) -> bool:
        existing = await self.get_metadata(file_id, key)
        if existing is None:
            return False
        await self._s.delete(existing)
        return True

    # ---- Index records -----------------------------------------------
    async def upsert_index(
        self, file_id: str, *, content_text: str, status: str, detail: str = ""
    ) -> IndexRecord:
        """One record per file, replaced on re-index rather than
        appended: an index is a current statement about a file, not a
        history of what it used to contain."""
        existing = await self._s.get(IndexRecord, file_id)
        if existing is not None:
            existing.content_text = content_text
            existing.status = status
            existing.detail = detail
            existing.indexed_at = datetime.now(UTC)
            return existing
        record = IndexRecord(
            file_id=file_id, content_text=content_text, status=status, detail=detail
        )
        self._s.add(record)
        await self._s.flush()
        return record

    async def get_index(self, file_id: str) -> IndexRecord | None:
        return await self._s.get(IndexRecord, file_id)

    async def counts_by_status(self, workspace_id: str) -> dict[str, int]:
        stmt = (
            select(IndexRecord.status, func.count())
            .join(File, File.id == IndexRecord.file_id)
            .where(File.workspace_id == workspace_id)
            .group_by(IndexRecord.status)
        )
        return {row[0]: int(row[1]) for row in (await self._s.execute(stmt)).all()}


class AttachmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(
        self,
        workspace_id: str,
        file_id: str,
        *,
        project_id: str | None = None,
        note_id: str | None = None,
        task_id: str | None = None,
        event_id: str | None = None,
        reminder_id: str | None = None,
        caption: str = "",
    ) -> WorkspaceAttachment:
        attachment = WorkspaceAttachment(
            workspace_id=workspace_id,
            file_id=file_id,
            project_id=project_id,
            note_id=note_id,
            task_id=task_id,
            event_id=event_id,
            reminder_id=reminder_id,
            caption=caption,
        )
        self._s.add(attachment)
        await self._s.flush()
        return attachment

    async def get(self, attachment_id: str) -> WorkspaceAttachment | None:
        return await self._s.get(WorkspaceAttachment, attachment_id)

    async def list_attachments(
        self,
        *,
        workspace_id: str | None = None,
        file_id: str | None = None,
        project_id: str | None = None,
        note_id: str | None = None,
        task_id: str | None = None,
        event_id: str | None = None,
        reminder_id: str | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> list[WorkspaceAttachment]:
        stmt = (
            select(WorkspaceAttachment)
            .order_by(WorkspaceAttachment.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        for column, value in (
            (WorkspaceAttachment.workspace_id, workspace_id),
            (WorkspaceAttachment.file_id, file_id),
            (WorkspaceAttachment.project_id, project_id),
            (WorkspaceAttachment.note_id, note_id),
            (WorkspaceAttachment.task_id, task_id),
            (WorkspaceAttachment.event_id, event_id),
            (WorkspaceAttachment.reminder_id, reminder_id),
        ):
            if value is not None:
                stmt = stmt.where(column == value)
        return list((await self._s.execute(stmt)).scalars().all())

    async def delete(self, attachment_id: str) -> bool:
        attachment = await self.get(attachment_id)
        if attachment is None:
            return False
        await self._s.delete(attachment)
        return True

    async def search(self, query: str, *, limit: int = 10) -> list[WorkspaceAttachment]:
        """Matches the caption or the attached file's name -- an
        attachment has little text of its own, and "the invoice I
        attached" is a search for the file through the attachment."""
        pattern = f"%{query.lower()}%"
        stmt = (
            select(WorkspaceAttachment)
            .join(File, File.id == WorkspaceAttachment.file_id)
            .where(
                or_(
                    func.lower(WorkspaceAttachment.caption).like(pattern),
                    func.lower(File.filename).like(pattern),
                )
            )
            .order_by(WorkspaceAttachment.created_at.desc())
            .limit(limit)
        )
        return list((await self._s.execute(stmt)).scalars().all())
