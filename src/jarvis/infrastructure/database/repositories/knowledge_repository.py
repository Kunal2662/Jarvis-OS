"""Knowledge repository — CRUD + keyword search over the knowledge graph
(``knowledge_entities`` / ``knowledge_relationships`` /
``knowledge_entity_memories``), mirroring ``MemoryRepository``'s shape."""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from jarvis.infrastructure.database.models import (
    KnowledgeEntity,
    KnowledgeEntityMemory,
    KnowledgeRelationship,
)


class KnowledgeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # ------------------------------------------------------------------
    # Entities
    # ------------------------------------------------------------------
    async def add_entity(
        self,
        name: str,
        *,
        entity_type: str = "other",
        description: str = "",
        confidence: float = 0.7,
    ) -> KnowledgeEntity:
        entity = KnowledgeEntity(
            name=name,
            entity_type=entity_type,
            description=description,
            confidence=confidence,
        )
        self._s.add(entity)
        await self._s.flush()
        return entity

    async def get_entity(self, entity_id: str) -> KnowledgeEntity | None:
        return await self._s.get(KnowledgeEntity, entity_id)

    async def find_entity_by_name(self, name: str) -> KnowledgeEntity | None:
        """Case-insensitive exact-name lookup — the fast path callers try
        before falling back to semantic resolution (see
        ``KnowledgeService``)."""
        stmt = select(KnowledgeEntity).where(func.lower(KnowledgeEntity.name) == name.lower())
        return (await self._s.execute(stmt)).scalars().first()

    async def search_entities(self, query: str, *, limit: int = 20) -> list[KnowledgeEntity]:
        """SQL ``LIKE`` search over name + description — the keyword half
        of entity resolution, mirroring
        ``MemoryRepository.keyword_search``."""
        tokens = [t for t in query.split() if t]
        if not tokens:
            return []
        clauses = [
            or_(
                KnowledgeEntity.name.ilike(f"%{t}%"),
                KnowledgeEntity.description.ilike(f"%{t}%"),
            )
            for t in tokens
        ]
        stmt = select(KnowledgeEntity).where(or_(*clauses)).limit(limit)
        return list((await self._s.execute(stmt)).scalars().all())

    async def list_entities(
        self, *, limit: int = 200, entity_type: str | None = None
    ) -> list[KnowledgeEntity]:
        stmt = select(KnowledgeEntity).order_by(KnowledgeEntity.updated_at.desc()).limit(limit)
        if entity_type is not None:
            stmt = stmt.where(KnowledgeEntity.entity_type == entity_type)
        return list((await self._s.execute(stmt)).scalars().all())

    async def delete_entity(self, entity_id: str) -> None:
        entity = await self.get_entity(entity_id)
        if entity is not None:
            await self._s.delete(entity)

    async def count_entities(self) -> int:
        stmt = select(func.count()).select_from(KnowledgeEntity)
        return int((await self._s.execute(stmt)).scalar_one())

    # ------------------------------------------------------------------
    # Entity <-> memory links
    # ------------------------------------------------------------------
    async def link_entity_memory(self, entity_id: str, memory_id: str) -> None:
        """Idempotent: does nothing if the link already exists."""
        exists_stmt = select(KnowledgeEntityMemory).where(
            KnowledgeEntityMemory.entity_id == entity_id,
            KnowledgeEntityMemory.memory_id == memory_id,
        )
        if (await self._s.execute(exists_stmt)).scalars().first() is not None:
            return
        self._s.add(KnowledgeEntityMemory(entity_id=entity_id, memory_id=memory_id))
        await self._s.flush()

    async def list_memory_ids_for_entity(self, entity_id: str) -> list[str]:
        stmt = select(KnowledgeEntityMemory.memory_id).where(
            KnowledgeEntityMemory.entity_id == entity_id
        )
        return list((await self._s.execute(stmt)).scalars().all())

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    async def add_relationship(
        self,
        subject_id: str,
        predicate: str,
        object_id: str,
        *,
        confidence: float = 0.7,
        source_memory_id: str | None = None,
    ) -> KnowledgeRelationship:
        rel = KnowledgeRelationship(
            subject_id=subject_id,
            predicate=predicate,
            object_id=object_id,
            confidence=confidence,
            source_memory_id=source_memory_id,
        )
        self._s.add(rel)
        await self._s.flush()
        return rel

    async def list_relationships_for_entity(
        self, entity_id: str, *, include_superseded: bool = False
    ) -> list[KnowledgeRelationship]:
        """Every relationship where *entity_id* is either the subject or
        the object -- the knowledge graph is directed but this query is
        symmetric, matching how a caller thinks about "what do we know
        about X" regardless of edge direction."""
        stmt = select(KnowledgeRelationship).where(
            or_(
                KnowledgeRelationship.subject_id == entity_id,
                KnowledgeRelationship.object_id == entity_id,
            )
        )
        if not include_superseded:
            stmt = stmt.where(KnowledgeRelationship.superseded.is_(False))
        stmt = stmt.order_by(KnowledgeRelationship.created_at.desc())
        return list((await self._s.execute(stmt)).scalars().all())

    async def supersede_relationships(
        self, subject_id: str, predicate: str, *, exclude_id: str | None = None
    ) -> int:
        """Mark every non-superseded ``(subject_id, predicate)`` edge as
        superseded -- the correction primitive Milestone 10A's Acceptance
        Criterion 3 relies on: a new, higher-confidence relationship
        replaces the old one without deleting it. Returns the count
        superseded."""
        stmt = select(KnowledgeRelationship).where(
            KnowledgeRelationship.subject_id == subject_id,
            KnowledgeRelationship.predicate == predicate,
            KnowledgeRelationship.superseded.is_(False),
        )
        if exclude_id is not None:
            stmt = stmt.where(KnowledgeRelationship.id != exclude_id)
        rows = list((await self._s.execute(stmt)).scalars().all())
        for row in rows:
            row.superseded = True
        return len(rows)

    async def list_all_entities(self) -> list[KnowledgeEntity]:
        """Unbounded listing for export -- see ``list_entities`` for the
        bounded, UI-facing equivalent."""
        stmt = select(KnowledgeEntity)
        return list((await self._s.execute(stmt)).scalars().all())

    async def list_all_relationships(self) -> list[KnowledgeRelationship]:
        stmt = select(KnowledgeRelationship)
        return list((await self._s.execute(stmt)).scalars().all())

    async def count_relationships(self) -> int:
        stmt = select(func.count()).select_from(KnowledgeRelationship)
        return int((await self._s.execute(stmt)).scalar_one())
