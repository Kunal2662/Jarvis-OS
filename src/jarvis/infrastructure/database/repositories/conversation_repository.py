"""Conversation repository — pure data access; no business logic."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jarvis.infrastructure.database.models import Conversation


class ConversationRepository:
    """CRUD over the ``conversations`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create(self, title: str = "New conversation") -> Conversation:
        conv = Conversation(title=title)
        self._s.add(conv)
        await self._s.flush()
        return conv

    async def get(self, conversation_id: str) -> Conversation | None:
        return await self._s.get(Conversation, conversation_id)

    async def list(self, *, limit: int = 100) -> list[Conversation]:
        stmt = select(Conversation).order_by(Conversation.updated_at.desc()).limit(limit)
        return list((await self._s.execute(stmt)).scalars().all())

    async def rename(self, conversation_id: str, title: str) -> None:
        conv = await self.get(conversation_id)
        if conv is not None:
            conv.title = title

    async def delete(self, conversation_id: str) -> None:
        conv = await self.get(conversation_id)
        if conv is not None:
            await self._s.delete(conv)
