"""Workspace repositories -- Milestone 11 Task Group A.

Three repositories over ``workspaces`` / ``projects`` / ``notes``,
following ``IntelligenceRepository``'s shape exactly: constructed with
an ``AsyncSession``, one class per aggregate, no session or transaction
management of its own (the service owns that via ``db.session()``), and
``flush()`` rather than ``commit()`` after an insert so the caller's
transaction boundary stays the caller's.

Three classes rather than one, unlike ``IntelligenceRepository``'s
combined goals/routines/preferences: those three are one bounded
context queried together by a single service method, whereas a project
listing and a note listing are independently useful and this milestone
has five more task groups that will each want one of them without the
other two.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from jarvis.infrastructure.database.models import Note, Project, Workspace


class WorkspaceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(
        self, name: str, *, description: str = "", settings_json: str = "{}"
    ) -> Workspace:
        workspace = Workspace(name=name, description=description, settings_json=settings_json)
        self._s.add(workspace)
        await self._s.flush()
        return workspace

    async def get(self, workspace_id: str) -> Workspace | None:
        return await self._s.get(Workspace, workspace_id)

    async def list_workspaces(
        self,
        *,
        status: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[Workspace]:
        stmt = select(Workspace).order_by(Workspace.created_at.desc()).limit(limit).offset(offset)
        if status is not None:
            stmt = stmt.where(Workspace.status == status)
        return list((await self._s.execute(stmt)).scalars().all())

    async def update(
        self,
        workspace_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        status: str | None = None,
        settings_json: str | None = None,
    ) -> Workspace | None:
        """Partial update: ``None`` means "leave alone", which is why
        every parameter is optional rather than the caller having to
        read-modify-write a whole row to change one field."""
        workspace = await self.get(workspace_id)
        if workspace is None:
            return None
        if name is not None:
            workspace.name = name
        if description is not None:
            workspace.description = description
        if status is not None:
            workspace.status = status
        if settings_json is not None:
            workspace.settings_json = settings_json
        return workspace

    async def delete(self, workspace_id: str) -> bool:
        workspace = await self.get(workspace_id)
        if workspace is None:
            return False
        await self._s.delete(workspace)
        return True

    async def search(self, query: str, *, limit: int = 10) -> list[Workspace]:
        pattern = f"%{query.lower()}%"
        stmt = (
            select(Workspace)
            .where(
                or_(
                    func.lower(Workspace.name).like(pattern),
                    func.lower(Workspace.description).like(pattern),
                )
            )
            .order_by(Workspace.updated_at.desc())
            .limit(limit)
        )
        return list((await self._s.execute(stmt)).scalars().all())

    async def counts(self, workspace_id: str) -> tuple[int, int, int]:
        """``(project_count, active_project_count, note_count)`` for one
        workspace, as three aggregate queries rather than loading the
        rows -- this backs ``WorkspaceMetadata``, which is derived on
        every read and must not cost a full collection load to produce.
        """
        projects = await self._s.scalar(
            select(func.count()).select_from(Project).where(Project.workspace_id == workspace_id)
        )
        active = await self._s.scalar(
            select(func.count())
            .select_from(Project)
            .where(Project.workspace_id == workspace_id, Project.status == "active")
        )
        notes = await self._s.scalar(
            select(func.count()).select_from(Note).where(Note.workspace_id == workspace_id)
        )
        return int(projects or 0), int(active or 0), int(notes or 0)


class ProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, workspace_id: str, name: str, *, description: str = "") -> Project:
        project = Project(workspace_id=workspace_id, name=name, description=description)
        self._s.add(project)
        await self._s.flush()
        return project

    async def get(self, project_id: str) -> Project | None:
        return await self._s.get(Project, project_id)

    async def list_projects(
        self,
        *,
        workspace_id: str | None = None,
        status: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[Project]:
        stmt = select(Project).order_by(Project.created_at.desc()).limit(limit).offset(offset)
        if workspace_id is not None:
            stmt = stmt.where(Project.workspace_id == workspace_id)
        if status is not None:
            stmt = stmt.where(Project.status == status)
        return list((await self._s.execute(stmt)).scalars().all())

    async def update(
        self,
        project_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        status: str | None = None,
    ) -> Project | None:
        project = await self.get(project_id)
        if project is None:
            return None
        if name is not None:
            project.name = name
        if description is not None:
            project.description = description
        if status is not None:
            project.status = status
        return project

    async def delete(self, project_id: str) -> bool:
        project = await self.get(project_id)
        if project is None:
            return False
        await self._s.delete(project)
        return True

    async def detach_notes(self, project_id: str) -> int:
        """Clears ``project_id`` on this project's notes, returning how
        many moved. Called before deleting a project so its notes fall
        back to the workspace instead of vanishing -- see ``Note``'s own
        docstring for why that is the intended behaviour rather than the
        cascade's."""
        notes = list(
            (await self._s.execute(select(Note).where(Note.project_id == project_id)))
            .scalars()
            .all()
        )
        for note in notes:
            note.project_id = None
        return len(notes)

    async def search(self, query: str, *, limit: int = 10) -> list[Project]:
        pattern = f"%{query.lower()}%"
        stmt = (
            select(Project)
            .where(
                or_(
                    func.lower(Project.name).like(pattern),
                    func.lower(Project.description).like(pattern),
                )
            )
            .order_by(Project.updated_at.desc())
            .limit(limit)
        )
        return list((await self._s.execute(stmt)).scalars().all())


class NoteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(
        self,
        workspace_id: str,
        title: str,
        *,
        content: str = "",
        project_id: str | None = None,
        content_format: str = "markdown",
    ) -> Note:
        note = Note(
            workspace_id=workspace_id,
            project_id=project_id,
            title=title,
            content=content,
            content_format=content_format,
        )
        self._s.add(note)
        await self._s.flush()
        return note

    async def get(self, note_id: str) -> Note | None:
        return await self._s.get(Note, note_id)

    async def list_notes(
        self,
        *,
        workspace_id: str | None = None,
        project_id: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[Note]:
        """Pinned notes first, then most-recently-updated -- the order a
        note list is actually read in, applied here rather than left to
        each caller to re-sort."""
        stmt = (
            select(Note)
            .order_by(Note.pinned.desc(), Note.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if workspace_id is not None:
            stmt = stmt.where(Note.workspace_id == workspace_id)
        if project_id is not None:
            stmt = stmt.where(Note.project_id == project_id)
        return list((await self._s.execute(stmt)).scalars().all())

    async def update(
        self,
        note_id: str,
        *,
        title: str | None = None,
        content: str | None = None,
        content_format: str | None = None,
        project_id: str | None = None,
        pinned: bool | None = None,
        clear_project: bool = False,
    ) -> Note | None:
        """``clear_project`` exists because ``project_id=None`` already
        means "leave alone" in this partial-update convention, and
        "move this note out of its project" is a real operation that
        would otherwise be unexpressible."""
        note = await self.get(note_id)
        if note is None:
            return None
        if title is not None:
            note.title = title
        if content is not None:
            note.content = content
        if content_format is not None:
            note.content_format = content_format
        if clear_project:
            note.project_id = None
        elif project_id is not None:
            note.project_id = project_id
        if pinned is not None:
            note.pinned = pinned
        return note

    async def delete(self, note_id: str) -> bool:
        note = await self.get(note_id)
        if note is None:
            return False
        await self._s.delete(note)
        return True

    async def search(self, query: str, *, limit: int = 10) -> list[Note]:
        pattern = f"%{query.lower()}%"
        stmt = (
            select(Note)
            .where(
                or_(
                    func.lower(Note.title).like(pattern),
                    func.lower(Note.content).like(pattern),
                )
            )
            .order_by(Note.pinned.desc(), Note.updated_at.desc())
            .limit(limit)
        )
        return list((await self._s.execute(stmt)).scalars().all())

    async def last_activity_at(self, workspace_id: str) -> datetime | None:
        """Most recent note update in this workspace, or ``None``.
        Feeds ``WorkspaceMetadata.last_activity_at``.

        ``scalar()`` is typed ``Any``, so the result is narrowed here
        rather than returned straight through -- an empty workspace
        genuinely yields ``None``, and a caller should be able to trust
        the annotation.
        """
        value = await self._s.scalar(
            select(func.max(Note.updated_at)).where(Note.workspace_id == workspace_id)
        )
        return value if isinstance(value, datetime) else None
