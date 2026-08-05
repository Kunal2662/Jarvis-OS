"""AI Workspace repository -- Milestone 11 Task Group D.

One repository over ``workspace_knowledge_links``, following
``AttachmentRepository``'s shape exactly: constructed with an
``AsyncSession``, no session or transaction management of its own (the
service owns that via ``db.session()``), and ``flush()`` rather than
``commit()`` after an insert so the caller's transaction boundary stays
the caller's.

One class rather than three, unlike the workspace repositories: this
task group adds one table, and the entity rows it joins to are
``KnowledgeRepository``'s -- reading them through a join here rather
than re-implementing entity access is the same choice
``AttachmentRepository.search`` already made when it joined ``files``.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from jarvis.infrastructure.database.models import KnowledgeEntity, WorkspaceKnowledgeLink


class WorkspaceLinkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(
        self,
        workspace_id: str,
        entity_id: str,
        *,
        project_id: str | None = None,
        note_id: str | None = None,
        task_id: str | None = None,
        file_id: str | None = None,
        source: str = "extracted",
        confidence: float = 0.7,
    ) -> WorkspaceKnowledgeLink:
        link = WorkspaceKnowledgeLink(
            workspace_id=workspace_id,
            entity_id=entity_id,
            project_id=project_id,
            note_id=note_id,
            task_id=task_id,
            file_id=file_id,
            source=source,
            confidence=confidence,
        )
        self._s.add(link)
        await self._s.flush()
        return link

    async def get(self, link_id: str) -> WorkspaceKnowledgeLink | None:
        return await self._s.get(WorkspaceKnowledgeLink, link_id)

    async def find(
        self,
        workspace_id: str,
        entity_id: str,
        *,
        project_id: str | None = None,
        note_id: str | None = None,
        task_id: str | None = None,
        file_id: str | None = None,
    ) -> WorkspaceKnowledgeLink | None:
        """The exact-match lookup that makes linking idempotent.

        Every narrow column is compared, including the ``None`` ones:
        "this note is about Ada" and "this workspace is about Ada" are
        different rows, and a lookup that ignored the nulls would
        collapse them into one and then refuse to create the second.
        """
        stmt = select(WorkspaceKnowledgeLink).where(
            WorkspaceKnowledgeLink.workspace_id == workspace_id,
            WorkspaceKnowledgeLink.entity_id == entity_id,
            (
                WorkspaceKnowledgeLink.project_id.is_(None)
                if project_id is None
                else WorkspaceKnowledgeLink.project_id == project_id
            ),
            (
                WorkspaceKnowledgeLink.note_id.is_(None)
                if note_id is None
                else WorkspaceKnowledgeLink.note_id == note_id
            ),
            (
                WorkspaceKnowledgeLink.task_id.is_(None)
                if task_id is None
                else WorkspaceKnowledgeLink.task_id == task_id
            ),
            (
                WorkspaceKnowledgeLink.file_id.is_(None)
                if file_id is None
                else WorkspaceKnowledgeLink.file_id == file_id
            ),
        )
        return (await self._s.execute(stmt.limit(1))).scalars().first()

    async def list_links(
        self,
        *,
        workspace_id: str | None = None,
        entity_id: str | None = None,
        project_id: str | None = None,
        note_id: str | None = None,
        task_id: str | None = None,
        file_id: str | None = None,
        source: str | None = None,
        limit: int = 500,
    ) -> list[WorkspaceKnowledgeLink]:
        stmt = (
            select(WorkspaceKnowledgeLink)
            .order_by(
                WorkspaceKnowledgeLink.confidence.desc(),
                WorkspaceKnowledgeLink.created_at.desc(),
            )
            .limit(limit)
        )
        for column, value in (
            (WorkspaceKnowledgeLink.workspace_id, workspace_id),
            (WorkspaceKnowledgeLink.entity_id, entity_id),
            (WorkspaceKnowledgeLink.project_id, project_id),
            (WorkspaceKnowledgeLink.note_id, note_id),
            (WorkspaceKnowledgeLink.task_id, task_id),
            (WorkspaceKnowledgeLink.file_id, file_id),
            (WorkspaceKnowledgeLink.source, source),
        ):
            if value is not None:
                stmt = stmt.where(column == value)
        return list((await self._s.execute(stmt)).scalars().all())

    async def delete(self, link_id: str) -> bool:
        link = await self.get(link_id)
        if link is None:
            return False
        await self._s.delete(link)
        return True

    async def delete_extracted_for_target(
        self,
        workspace_id: str,
        *,
        project_id: str | None = None,
        note_id: str | None = None,
        task_id: str | None = None,
        file_id: str | None = None,
    ) -> int:
        """Clears one target's ``extracted`` links, leaving ``manual``
        ones alone. Called before re-ingesting a target, so an edited
        note stops claiming entities its text no longer mentions without
        discarding what a caller asserted by hand."""
        links = await self.list_links(
            workspace_id=workspace_id,
            project_id=project_id,
            note_id=note_id,
            task_id=task_id,
            file_id=file_id,
            source="extracted",
        )
        matching = [
            link
            for link in links
            if link.project_id == project_id
            and link.note_id == note_id
            and link.task_id == task_id
            and link.file_id == file_id
        ]
        for link in matching:
            await self._s.delete(link)
        return len(matching)

    async def entities_for_workspace(
        self, workspace_id: str, *, limit: int = 50
    ) -> list[tuple[KnowledgeEntity, int, float]]:
        """``(entity, link_count, best_confidence)`` for one workspace,
        most-linked first.

        A join and two aggregates rather than loading every link and
        grouping in Python: this backs the knowledge section of an AI
        context, which is assembled on every assist call, and a workspace
        with a thousand links must not cost a thousand-row load to
        produce ten lines.
        """
        stmt = (
            select(
                KnowledgeEntity,
                func.count(WorkspaceKnowledgeLink.id),
                func.max(WorkspaceKnowledgeLink.confidence),
            )
            .join(WorkspaceKnowledgeLink, WorkspaceKnowledgeLink.entity_id == KnowledgeEntity.id)
            .where(WorkspaceKnowledgeLink.workspace_id == workspace_id)
            .group_by(KnowledgeEntity.id)
            .order_by(func.count(WorkspaceKnowledgeLink.id).desc(), KnowledgeEntity.name)
            .limit(limit)
        )
        rows = (await self._s.execute(stmt)).all()
        return [(row[0], int(row[1] or 0), float(row[2] or 0.0)) for row in rows]

    async def count_for_workspace(self, workspace_id: str) -> int:
        value = await self._s.scalar(
            select(func.count())
            .select_from(WorkspaceKnowledgeLink)
            .where(WorkspaceKnowledgeLink.workspace_id == workspace_id)
        )
        return int(value or 0)
