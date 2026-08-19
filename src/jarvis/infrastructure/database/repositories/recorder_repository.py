"""Recording session repository -- M7 Recorder.

One small repository over ``recording_sessions``, following
``workflow_builder_repository.py``'s shape exactly: constructed with
an ``AsyncSession``, no session or transaction management of its own
(the service owns that via ``db.session()``), ``flush()`` rather than
``commit()`` after a write so the caller's transaction boundary stays
the caller's. See ``docs/M7_RECORDER_LOGIC_CONTRACT.md`` §7/§8.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jarvis.infrastructure.database.models import RecordingSession


class RecordingSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self) -> RecordingSession:
        row = RecordingSession(status="recording")
        self._s.add(row)
        await self._s.flush()
        return row

    async def get(self, session_id: str) -> RecordingSession | None:
        return await self._s.get(RecordingSession, session_id)

    async def get_active(self) -> RecordingSession | None:
        """The single-active-session check (Logic Contract §13) --
        None if nothing is currently `"recording"`."""
        stmt = select(RecordingSession).where(RecordingSession.status == "recording")
        return (await self._s.execute(stmt)).scalars().first()

    async def list_all(self, *, limit: int = 50, offset: int = 0) -> list[RecordingSession]:
        stmt = (
            select(RecordingSession)
            .order_by(RecordingSession.started_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self._s.execute(stmt)).scalars().all())

    async def finish(
        self,
        session_id: str,
        *,
        status: str,
        stopped_at: datetime,
        resulting_workflow_id: str | None = None,
    ) -> RecordingSession | None:
        row = await self.get(session_id)
        if row is None:
            return None
        row.status = status
        row.stopped_at = stopped_at
        row.resulting_workflow_id = resulting_workflow_id
        await self._s.flush()
        return row
