"""Conversation service — read/write conversations & messages via repositories."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from jarvis.core.exceptions import ServiceError
from jarvis.core.types import ChatMessage, Role
from jarvis.infrastructure.database.repositories import (
    ConversationRepository,
    MessageRepository,
)

if TYPE_CHECKING:
    from jarvis.core.interfaces.database import IDatabase


@dataclass(frozen=True, slots=True)
class ConversationSummary:
    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationService:
    """Business API for conversations. Wraps repositories with sessions."""

    def __init__(self, database: IDatabase) -> None:
        self._db = database

    async def list(self) -> list[ConversationSummary]:
        async with self._db.session() as sess:  # type: ignore[assignment]
            convs = await ConversationRepository(sess).list()
            return [ConversationSummary(c.id, c.title, c.created_at, c.updated_at) for c in convs]

    async def create(self, title: str = "New conversation") -> ConversationSummary:
        async with self._db.session() as sess:  # type: ignore[assignment]
            c = await ConversationRepository(sess).create(title=title)
            return ConversationSummary(c.id, c.title, c.created_at, c.updated_at)

    async def rename(self, conversation_id: str, title: str) -> None:
        async with self._db.session() as sess:  # type: ignore[assignment]
            await ConversationRepository(sess).rename(conversation_id, title)

    async def delete(self, conversation_id: str) -> None:
        async with self._db.session() as sess:  # type: ignore[assignment]
            await ConversationRepository(sess).delete(conversation_id)

    async def history(self, conversation_id: str) -> list[ChatMessage]:
        async with self._db.session() as sess:  # type: ignore[assignment]
            msgs = await MessageRepository(sess).list(conversation_id)
            return [ChatMessage(role=m.role, content=m.content) for m in msgs]  # type: ignore[arg-type]

    async def append(self, conversation_id: str, role: Role, content: str) -> None:
        if not content:
            raise ServiceError("Cannot append empty message.")
        async with self._db.session() as sess:  # type: ignore[assignment]
            await MessageRepository(sess).add(conversation_id, role, content)
