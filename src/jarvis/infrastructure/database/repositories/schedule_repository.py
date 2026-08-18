"""Scheduler repositories -- Milestone 7 Phase 6 (Scheduler MVP).

Three small repositories over the three Scheduler tables, following
``smart_lighting_repository.py``'s shape exactly: each constructed with an
``AsyncSession``, no session or transaction management of its own (the
service owns that via ``db.session()``), ``flush()`` rather than
``commit()`` after a write so the caller's transaction boundary stays the
caller's. See ``docs/M7_SCHEDULER_LOGIC_CONTRACT.md`` §7.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jarvis.infrastructure.database.models import Schedule, WorkflowDefinition, WorkflowExecution


class WorkflowRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, *, name: str, steps_json: str, description: str = "") -> WorkflowDefinition:
        workflow = WorkflowDefinition(name=name, description=description, steps_json=steps_json)
        self._s.add(workflow)
        await self._s.flush()
        return workflow

    async def get(self, workflow_id: str) -> WorkflowDefinition | None:
        return await self._s.get(WorkflowDefinition, workflow_id)

    async def delete(self, workflow_id: str) -> bool:
        workflow = await self.get(workflow_id)
        if workflow is None:
            return False
        await self._s.delete(workflow)
        await self._s.flush()
        return True


class ScheduleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(
        self,
        *,
        workflow_id: str,
        kind: str,
        interval_seconds: float,
        cron_expression: str,
        timezone: str,
        next_fire_at: datetime | None,
        enabled: bool = True,
    ) -> Schedule:
        schedule = Schedule(
            workflow_id=workflow_id,
            kind=kind,
            interval_seconds=interval_seconds,
            cron_expression=cron_expression,
            timezone=timezone,
            enabled=enabled,
            next_fire_at=next_fire_at,
        )
        self._s.add(schedule)
        await self._s.flush()
        return schedule

    async def get(self, schedule_id: str) -> Schedule | None:
        return await self._s.get(Schedule, schedule_id)

    async def list_schedules(
        self, *, enabled_only: bool = False, limit: int = 200, offset: int = 0
    ) -> list[Schedule]:
        stmt = select(Schedule).order_by(Schedule.created_at.desc()).limit(limit).offset(offset)
        if enabled_only:
            stmt = stmt.where(Schedule.enabled.is_(True))
        return list((await self._s.execute(stmt)).scalars().all())

    async def list_due(self, *, now: datetime) -> list[Schedule]:
        """Every enabled schedule whose ``next_fire_at`` is at or before
        *now* -- the Scheduler firing loop's own due-set query. Excludes
        disabled schedules entirely, so a disabled schedule is never
        evaluated for misfire either (Logic Contract §9)."""
        stmt = select(Schedule).where(
            Schedule.enabled.is_(True),
            Schedule.next_fire_at.is_not(None),
            Schedule.next_fire_at <= now,
        )
        return list((await self._s.execute(stmt)).scalars().all())

    async def set_enabled(self, schedule_id: str, *, enabled: bool) -> Schedule | None:
        schedule = await self.get(schedule_id)
        if schedule is None:
            return None
        schedule.enabled = enabled
        await self._s.flush()
        return schedule

    async def record_fire(
        self,
        schedule_id: str,
        *,
        next_fire_at: datetime | None,
        last_fired_at: datetime | None,
        last_execution_id: str | None,
    ) -> Schedule | None:
        schedule = await self.get(schedule_id)
        if schedule is None:
            return None
        schedule.next_fire_at = next_fire_at
        schedule.last_fired_at = last_fired_at
        schedule.last_execution_id = last_execution_id
        await self._s.flush()
        return schedule

    async def delete(self, schedule_id: str) -> bool:
        schedule = await self.get(schedule_id)
        if schedule is None:
            return False
        await self._s.delete(schedule)
        await self._s.flush()
        return True


class WorkflowExecutionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(
        self, *, schedule_id: str, workflow_id: str, status: str = "queued"
    ) -> WorkflowExecution:
        execution = WorkflowExecution(
            schedule_id=schedule_id, workflow_id=workflow_id, status=status
        )
        self._s.add(execution)
        await self._s.flush()
        return execution

    async def get(self, execution_id: str) -> WorkflowExecution | None:
        return await self._s.get(WorkflowExecution, execution_id)

    async def has_non_terminal(self, schedule_id: str) -> bool:
        """True if *schedule_id* has a ``queued``/``running`` execution --
        the sole duplicate-fire-prevention check (Logic Contract §10)."""
        stmt = select(WorkflowExecution.id).where(
            WorkflowExecution.schedule_id == schedule_id,
            WorkflowExecution.status.in_(("queued", "running")),
        )
        return (await self._s.execute(stmt)).first() is not None

    async def list_for_schedule(
        self, schedule_id: str, *, limit: int = 50, offset: int = 0
    ) -> list[WorkflowExecution]:
        stmt = (
            select(WorkflowExecution)
            .where(WorkflowExecution.schedule_id == schedule_id)
            .order_by(WorkflowExecution.started_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self._s.execute(stmt)).scalars().all())

    async def finish(
        self,
        execution_id: str,
        *,
        status: str,
        error: str | None,
        step_results_json: str,
        finished_at: datetime,
    ) -> WorkflowExecution | None:
        execution = await self.get(execution_id)
        if execution is None:
            return None
        execution.status = status
        execution.error = error
        execution.step_results_json = step_results_json
        execution.finished_at = finished_at
        await self._s.flush()
        return execution
