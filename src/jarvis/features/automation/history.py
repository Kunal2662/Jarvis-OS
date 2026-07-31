"""Task history -- persists every executed step to SQLite.

Thin business-API wrapper over :class:`TaskHistoryRepository`, following
the same "open a session per call" pattern as
:class:`~jarvis.services.conversation_service.ConversationService`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from jarvis.domain.automation.models import StepResult
from jarvis.infrastructure.database.repositories import TaskHistoryRepository

if TYPE_CHECKING:
    from jarvis.core.interfaces.database import IDatabase


@dataclass(frozen=True, slots=True)
class TaskHistoryEntry:
    id: str
    plan_id: str
    action: str
    target: str | None
    status: str
    result: str | None
    error: str | None
    duration_ms: float
    created_at: datetime


class HistoryService:
    def __init__(self, database: IDatabase) -> None:
        self._db = database

    async def record(
        self,
        *,
        plan_id: str,
        step_id: str,
        result: StepResult,
        target: str | None,
        args: dict,
    ) -> None:
        async with self._db.session() as sess:  # type: ignore[assignment]
            await TaskHistoryRepository(sess).add(
                record_id=step_id,
                plan_id=plan_id,
                action=result.action.value,
                target=target,
                status=result.status.value,
                args_json=json.dumps(args, default=str),
                result=(
                    json.dumps(result.output, default=str) if result.output is not None else None
                ),
                error=result.error,
                duration_ms=result.duration_ms,
            )

    async def list_recent(self, *, limit: int = 50) -> list[TaskHistoryEntry]:
        async with self._db.session() as sess:  # type: ignore[assignment]
            rows = await TaskHistoryRepository(sess).list_recent(limit=limit)
            return [
                TaskHistoryEntry(
                    id=r.id,
                    plan_id=r.plan_id,
                    action=r.action,
                    target=r.target,
                    status=r.status,
                    result=r.result,
                    error=r.error,
                    duration_ms=r.duration_ms,
                    created_at=r.created_at,
                )
                for r in rows
            ]

    async def purge_expired(self, *, retention_days: int) -> int:
        async with self._db.session() as sess:  # type: ignore[assignment]
            return await TaskHistoryRepository(sess).purge_older_than(retention_days)

    async def clear(self) -> int:
        async with self._db.session() as sess:  # type: ignore[assignment]
            return await TaskHistoryRepository(sess).clear()
