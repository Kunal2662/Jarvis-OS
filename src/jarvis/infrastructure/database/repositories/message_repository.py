"""Message repository — pure data access; no business logic."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jarvis.core.types import Role
from jarvis.infrastructure.database.models import Message


class MessageRepository:
    """CRUD over the ``messages`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, conversation_id: str, role: Role, content: str) -> Message:
        msg = Message(conversation_id=conversation_id, role=role, content=content)
        self._s.add(msg)
        await self._s.flush()
        return msg

    async def list(self, conversation_id: str, *, limit: int = 500) -> list[Message]:
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
            .limit(limit)
        )
        return list((await self._s.execute(stmt)).scalars().all())
