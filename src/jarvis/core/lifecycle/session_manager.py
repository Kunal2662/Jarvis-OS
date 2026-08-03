"""``SessionManager`` -- runtime session tracking (Milestone 9 Task Group
B). A *runtime session* is one connected client/runtime context: today,
the desktop UI's single primary session; once the Runtime WebSocket API
(this same task group) is in use, one per WebSocket connection -- and
the ``Depends(get_current_session)`` mechanism ``docs/ARCHITECTURE.md``
section 6 already references for Bearer-token auth.

**Why a session is its own id space**, not a reuse of
``Conversation.id`` or the agent orchestrator's LangGraph ``thread_id``:
those model two different, already-real things --
:class:`~jarvis.services.conversation_service.ConversationService`'s
saved chat history, and :class:`~jarvis.agents.checkpointer.
AgentCheckpointer`'s LangGraph checkpoint lineage -- and today have no
link between them at all. Forcing them to share one id, or inventing a
third, disconnected id space, would both be worse than what
:class:`RuntimeSession` (``infrastructure/database/models.py``) actually
is: the first real place those two ids can optionally sit side by side.
Both columns stay nullable -- a session can exist before either is
chosen.

**Persistence and recovery.** A session row is written as soon as it's
created (not batched) so an unclean shutdown can never silently lose
one. "Recovery after restart" does not mean resuming a dead WebSocket
-- a closed OS process has no socket to hand back. It means
:meth:`SessionManager.recover` finds every row left with no
``closed_at`` from the previous run (an unclean shutdown skipped
:meth:`close`), closes each out for accurate bookkeeping, and reports
what it found -- so the sessions table never accumulates permanently
"open" ghosts, and a reconnecting frontend can still look up its last
``conversation_id``/``thread_id`` by session id if it kept one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from jarvis.core.events.events import SessionClosedEvent, SessionCreatedEvent
from jarvis.core.logging.logger import get_logger
from jarvis.infrastructure.database.repositories import RuntimeSessionRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.interfaces.database import IDatabase
    from jarvis.infrastructure.database.models import RuntimeSession

_logger = get_logger("jarvis.core.lifecycle.session_manager")


@dataclass(frozen=True, slots=True)
class SessionInfo:
    session_id: str
    conversation_id: str | None
    thread_id: str | None
    created_at: datetime
    last_active_at: datetime
    closed_at: datetime | None
    metadata: dict[str, Any]

    @classmethod
    def _from_row(cls, row: RuntimeSession) -> SessionInfo:
        try:
            metadata = json.loads(row.meta_json)
        except (TypeError, ValueError):
            metadata = {}
        return cls(
            session_id=row.id,
            conversation_id=row.conversation_id,
            thread_id=row.thread_id,
            created_at=row.created_at,
            last_active_at=row.last_active_at,
            closed_at=row.closed_at,
            metadata=metadata,
        )


class SessionManager:
    def __init__(self, database: IDatabase, event_bus: EventBus) -> None:
        self._db = database
        self._event_bus = event_bus
        self._active: dict[str, SessionInfo] = {}

    async def recover(self) -> tuple[SessionInfo, ...]:
        """Call once at startup, before any new session is created in
        this process. Closes out every session an unclean previous
        shutdown left open and publishes :class:`SessionClosedEvent`
        for each -- graceful cleanup deferred from the run that
        couldn't do it itself."""
        async with self._db.session() as sess:
            repo = RuntimeSessionRepository(cast("AsyncSession", sess))
            dangling = await repo.list_open()
            recovered = tuple(SessionInfo._from_row(row) for row in dangling)
            for row in dangling:
                await repo.close(row.id)

        for info in recovered:
            _logger.warning(
                "Recovered dangling session {!r} from an unclean shutdown.", info.session_id
            )
            await self._event_bus.publish(SessionClosedEvent(session_id=info.session_id))
        return recovered

    async def create(
        self,
        *,
        conversation_id: str | None = None,
        thread_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SessionInfo:
        meta_json = json.dumps(metadata or {})
        async with self._db.session() as sess:
            row = await RuntimeSessionRepository(cast("AsyncSession", sess)).create(
                conversation_id=conversation_id, thread_id=thread_id, meta_json=meta_json
            )
            info = SessionInfo._from_row(row)

        self._active[info.session_id] = info
        _logger.info("Session {!r} created.", info.session_id)
        await self._event_bus.publish(
            SessionCreatedEvent(session_id=info.session_id, recovered=False)
        )
        return info

    async def touch(self, session_id: str) -> None:
        """Heartbeat -- bumps ``last_active_at``. Silently a no-op for an
        unknown/already-closed session id (a late heartbeat racing a
        close is expected, not an error)."""
        async with self._db.session() as sess:
            await RuntimeSessionRepository(cast("AsyncSession", sess)).touch(session_id)

    async def close(self, session_id: str) -> None:
        if session_id not in self._active:
            return
        async with self._db.session() as sess:
            await RuntimeSessionRepository(cast("AsyncSession", sess)).close(session_id)
        del self._active[session_id]
        _logger.info("Session {!r} closed.", session_id)
        await self._event_bus.publish(SessionClosedEvent(session_id=session_id))

    async def close_all(self) -> None:
        """Graceful cleanup at application shutdown -- every session
        still open when ``RuntimeManager.shutdown()`` runs is closed
        properly, so :meth:`recover` finds nothing to do on the next
        clean start."""
        for session_id in tuple(self._active):
            await self.close(session_id)

    def get(self, session_id: str) -> SessionInfo | None:
        return self._active.get(session_id)

    @property
    def active_sessions(self) -> tuple[SessionInfo, ...]:
        return tuple(self._active.values())
