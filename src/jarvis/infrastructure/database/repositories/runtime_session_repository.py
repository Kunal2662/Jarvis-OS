"""Runtime session repository -- pure data access; no business logic."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jarvis.infrastructure.database.models import RuntimeSession


class RuntimeSessionRepository:
    """CRUD over the ``runtime_sessions`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create(
        self,
        *,
        conversation_id: str | None = None,
        thread_id: str | None = None,
        meta_json: str = "{}",
    ) -> RuntimeSession:
        row = RuntimeSession(
            conversation_id=conversation_id, thread_id=thread_id, meta_json=meta_json
        )
        self._s.add(row)
        await self._s.flush()
        return row

    async def get(self, session_id: str) -> RuntimeSession | None:
        return await self._s.get(RuntimeSession, session_id)

    async def list_open(self) -> list[RuntimeSession]:
        """Every session with no ``closed_at`` -- on a clean run this is
        only sessions created earlier *this* process; at startup, before
        this process has created any, it is exactly the set left dangling
        by an unclean previous shutdown."""
        stmt = select(RuntimeSession).where(RuntimeSession.closed_at.is_(None))
        return list((await self._s.execute(stmt)).scalars().all())

    async def touch(self, session_id: str) -> None:
        row = await self.get(session_id)
        if row is not None:
            row.last_active_at = datetime.now(UTC)

    async def close(self, session_id: str) -> None:
        row = await self.get(session_id)
        if row is not None and row.closed_at is None:
            row.closed_at = datetime.now(UTC)
