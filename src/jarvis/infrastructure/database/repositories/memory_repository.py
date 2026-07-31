"""Memory repository — CRUD + keyword search over ``memories``."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from jarvis.infrastructure.database.models import Memory


class MemoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(
        self,
        content: str,
        *,
        source: str = "user",
        memory_type: str = "conversation",
        meta_json: str = "{}",
        conversation_id: str | None = None,
        pinned: bool = False,
        expires_at: datetime | None = None,
    ) -> Memory:
        mem = Memory(
            content=content,
            source=source,
            memory_type=memory_type,
            meta_json=meta_json,
            conversation_id=conversation_id,
            pinned=pinned,
            expires_at=expires_at,
        )
        self._s.add(mem)
        await self._s.flush()
        return mem

    async def get(self, memory_id: str) -> Memory | None:
        return await self._s.get(Memory, memory_id)

    async def delete(self, memory_id: str) -> None:
        mem = await self.get(memory_id)
        if mem is not None:
            await self._s.delete(mem)

    async def delete_many(self, memory_ids: list[str]) -> int:
        if not memory_ids:
            return 0
        n = 0
        for mid in memory_ids:
            mem = await self.get(mid)
            if mem is not None:
                await self._s.delete(mem)
                n += 1
        return n

    async def delete_all(self) -> int:
        """Delete every memory row. Returns the number of rows removed."""
        rows = await self.list(limit=1_000_000, include_archived=True)
        for row in rows:
            await self._s.delete(row)
        return len(rows)

    async def list(
        self,
        *,
        limit: int = 200,
        memory_type: str | None = None,
        include_archived: bool = True,
    ) -> list[Memory]:
        stmt = select(Memory).order_by(Memory.created_at.desc()).limit(limit)
        if memory_type is not None:
            stmt = stmt.where(Memory.memory_type == memory_type)
        if not include_archived:
            stmt = stmt.where(Memory.archived.is_(False))
        return list((await self._s.execute(stmt)).scalars().all())

    async def count(self, *, include_archived: bool = True) -> int:
        stmt = select(func.count()).select_from(Memory)
        if not include_archived:
            stmt = stmt.where(Memory.archived.is_(False))
        return int((await self._s.execute(stmt)).scalar_one())

    async def keyword_search(
        self, query: str, *, limit: int = 20, memory_type: str | None = None
    ) -> list[Memory]:
        """Simple SQL LIKE search — cheap prefilter used by hybrid recall."""
        if not query.strip():
            return []
        # Break the query into whitespace-separated tokens; each token
        # must appear (any-of, not all-of) so we stay permissive at the
        # SQL layer and let the vector store handle precision.
        tokens = [t for t in query.split() if t]
        if not tokens:
            return []
        clauses = [Memory.content.ilike(f"%{t}%") for t in tokens]
        stmt = select(Memory).where(or_(*clauses)).order_by(Memory.created_at.desc()).limit(limit)
        if memory_type is not None:
            stmt = stmt.where(Memory.memory_type == memory_type)
        return list((await self._s.execute(stmt)).scalars().all())

    # ------------------------------------------------------------------
    # Memory-policy support (pruning / expiration / archival)
    # ------------------------------------------------------------------
    async def list_expired(self, *, as_of: datetime) -> list[Memory]:
        stmt = select(Memory).where(
            Memory.expires_at.is_not(None),
            Memory.expires_at <= as_of,
            Memory.archived.is_(False),
        )
        return list((await self._s.execute(stmt)).scalars().all())

    async def list_prunable(self, *, keep: int) -> list[Memory]:
        """Return the oldest, unpinned, non-archived rows that put the
        *total* non-archived collection (pinned + unpinned) over ``keep``.

        Pinned rows always count against the cap but are never returned
        for pruning — only unpinned rows are ever pruned.
        """
        total_stmt = select(func.count()).select_from(Memory).where(Memory.archived.is_(False))
        total = int((await self._s.execute(total_stmt)).scalar_one())
        if total <= keep:
            return []
        excess = total - keep

        stmt = (
            select(Memory)
            .where(Memory.pinned.is_(False), Memory.archived.is_(False))
            .order_by(Memory.created_at.asc())
        )
        unpinned = list((await self._s.execute(stmt)).scalars().all())
        return unpinned[:excess]

    async def archive(self, memory_id: str) -> Memory | None:
        mem = await self.get(memory_id)
        if mem is not None:
            mem.archived = True
        return mem

    async def set_pinned(self, memory_id: str, *, pinned: bool) -> Memory | None:
        mem = await self.get(memory_id)
        if mem is not None:
            mem.pinned = pinned
        return mem

    async def touch_access(self, memory_id: str, *, when: datetime) -> None:
        mem = await self.get(memory_id)
        if mem is not None:
            mem.last_accessed_at = when

    # ------------------------------------------------------------------
    # Milestone 3.1 — Timeline / browsing view support
    # ------------------------------------------------------------------
    async def list_filtered(
        self,
        *,
        memory_type: str | None = None,
        pinned_only: bool = False,
        include_archived: bool = False,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 200,
    ) -> list[Memory]:
        """Filtered listing backing the Memory ▸ Timeline UI view.

        Unlike :meth:`list`, this also supports a pinned-only toggle and an
        inclusive ``[start_date, end_date]`` window over ``created_at`` —
        the two extra dimensions the timeline view needs that plain
        Settings ▸ Memory maintenance never did.
        """
        stmt = select(Memory).order_by(Memory.created_at.desc()).limit(limit)
        if memory_type is not None:
            stmt = stmt.where(Memory.memory_type == memory_type)
        if not include_archived:
            stmt = stmt.where(Memory.archived.is_(False))
        if pinned_only:
            stmt = stmt.where(Memory.pinned.is_(True))
        if start_date is not None:
            stmt = stmt.where(Memory.created_at >= start_date)
        if end_date is not None:
            stmt = stmt.where(Memory.created_at <= end_date)
        return list((await self._s.execute(stmt)).scalars().all())

    # ------------------------------------------------------------------
    # Milestone 3.1 — Retention re-stamping
    # ------------------------------------------------------------------
    async def restamp_expirations(self, *, retention_days: int) -> int:
        """Recompute ``expires_at`` for every unpinned, non-archived row
        from its ``created_at`` + *retention_days*, instead of only ever
        deriving it once at write time.

        Pass ``retention_days <= 0`` to clear ``expires_at`` on every such
        row (i.e. "keep forever"). Returns the number of rows changed.
        """
        stmt = select(Memory).where(Memory.pinned.is_(False), Memory.archived.is_(False))
        rows = list((await self._s.execute(stmt)).scalars().all())
        changed = 0
        for row in rows:
            new_expiry = (
                row.created_at + timedelta(days=retention_days) if retention_days > 0 else None
            )
            if row.expires_at != new_expiry:
                row.expires_at = new_expiry
                changed += 1
        return changed
