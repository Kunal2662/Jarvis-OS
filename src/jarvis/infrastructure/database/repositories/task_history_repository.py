"""Task-history repository — pure data access; no business logic."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from jarvis.infrastructure.database.models import TaskHistory


class TaskHistoryRepository:
    """CRUD over the ``automation_task_history`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(
        self,
        *,
        plan_id: str,
        action: str,
        target: str | None,
        status: str,
        args_json: str = "{}",
        result: str | None = None,
        error: str | None = None,
        duration_ms: float = 0.0,
        record_id: str | None = None,
    ) -> TaskHistory:
        row = TaskHistory(
            plan_id=plan_id,
            action=action,
            target=target,
            status=status,
            args_json=args_json,
            result=result,
            error=error,
            duration_ms=duration_ms,
        )
        if record_id is not None:
            row.id = record_id
        self._s.add(row)
        await self._s.flush()
        return row

    async def list_recent(self, *, limit: int = 50) -> list[TaskHistory]:
        stmt = select(TaskHistory).order_by(TaskHistory.created_at.desc()).limit(limit)
        return list((await self._s.execute(stmt)).scalars().all())

    async def list_for_plan(self, plan_id: str) -> list[TaskHistory]:
        stmt = (
            select(TaskHistory)
            .where(TaskHistory.plan_id == plan_id)
            .order_by(TaskHistory.created_at.asc())
        )
        return list((await self._s.execute(stmt)).scalars().all())

    async def purge_older_than(self, days: int) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        result = await self._s.execute(delete(TaskHistory).where(TaskHistory.created_at < cutoff))
        return result.rowcount or 0

    async def clear(self) -> int:
        result = await self._s.execute(delete(TaskHistory))
        return result.rowcount or 0
