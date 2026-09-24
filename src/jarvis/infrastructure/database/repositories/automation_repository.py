"""Home Automation repositories -- M7 (event-based triggers).

Two small repositories over the two Home Automation tables, following
``schedule_repository.py``'s shape exactly: each constructed with an
``AsyncSession``, no session or transaction management of its own (the
service owns that via ``db.session()``), ``flush()`` rather than
``commit()`` after a write so the caller's transaction boundary stays
the caller's. See ``docs/M7_HOME_AUTOMATION_LOGIC_CONTRACT.md`` §10/§32.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jarvis.infrastructure.database.models import AutomationExecution, AutomationTrigger


class AutomationTriggerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(
        self,
        *,
        workflow_id: str,
        device_id: str,
        to_status: str,
        from_status: str = "",
        enabled: bool = True,
    ) -> AutomationTrigger:
        trigger = AutomationTrigger(
            workflow_id=workflow_id,
            device_id=device_id,
            to_status=to_status,
            from_status=from_status,
            enabled=enabled,
        )
        self._s.add(trigger)
        await self._s.flush()
        return trigger

    async def get(self, trigger_id: str) -> AutomationTrigger | None:
        return await self._s.get(AutomationTrigger, trigger_id)

    async def list_triggers(
        self, *, enabled_only: bool = False, limit: int = 200, offset: int = 0
    ) -> list[AutomationTrigger]:
        stmt = (
            select(AutomationTrigger)
            .order_by(AutomationTrigger.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if enabled_only:
            stmt = stmt.where(AutomationTrigger.enabled.is_(True))
        return list((await self._s.execute(stmt)).scalars().all())

    async def list_matching(
        self, *, device_id: str, status: str, previous_status: str
    ) -> list[AutomationTrigger]:
        """Every enabled trigger matching *device_id* and the observed
        transition -- the Home Automation event-matching engine's own
        hot-path query (Logic Contract §11). ``from_status = ""`` is
        the wildcard: matches any previous status."""
        stmt = select(AutomationTrigger).where(
            AutomationTrigger.enabled.is_(True),
            AutomationTrigger.device_id == device_id,
            AutomationTrigger.to_status == status,
            (AutomationTrigger.from_status == "")
            | (AutomationTrigger.from_status == previous_status),
        )
        return list((await self._s.execute(stmt)).scalars().all())

    async def set_enabled(self, trigger_id: str, *, enabled: bool) -> AutomationTrigger | None:
        trigger = await self.get(trigger_id)
        if trigger is None:
            return None
        trigger.enabled = enabled
        await self._s.flush()
        return trigger

    async def record_fire(
        self,
        trigger_id: str,
        *,
        last_fired_at: datetime | None,
        last_execution_id: str | None,
    ) -> AutomationTrigger | None:
        trigger = await self.get(trigger_id)
        if trigger is None:
            return None
        trigger.last_fired_at = last_fired_at
        trigger.last_execution_id = last_execution_id
        await self._s.flush()
        return trigger

    async def delete(self, trigger_id: str) -> bool:
        trigger = await self.get(trigger_id)
        if trigger is None:
            return False
        await self._s.delete(trigger)
        await self._s.flush()
        return True


class AutomationExecutionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(
        self, *, automation_trigger_id: str, workflow_id: str, source: str, status: str = "queued"
    ) -> AutomationExecution:
        execution = AutomationExecution(
            automation_trigger_id=automation_trigger_id,
            workflow_id=workflow_id,
            source=source,
            status=status,
        )
        self._s.add(execution)
        await self._s.flush()
        return execution

    async def get(self, execution_id: str) -> AutomationExecution | None:
        return await self._s.get(AutomationExecution, execution_id)

    async def has_non_terminal(self, automation_trigger_id: str) -> bool:
        """True if *automation_trigger_id* has a ``queued``/``running``
        execution -- the sole duplicate-fire-prevention check, mirroring
        `WorkflowExecutionRepository.has_non_terminal` exactly (Logic
        Contract §14)."""
        stmt = select(AutomationExecution.id).where(
            AutomationExecution.automation_trigger_id == automation_trigger_id,
            AutomationExecution.status.in_(("queued", "running")),
        )
        return (await self._s.execute(stmt)).first() is not None

    async def list_for_trigger(
        self, automation_trigger_id: str, *, limit: int = 50, offset: int = 0
    ) -> list[AutomationExecution]:
        stmt = (
            select(AutomationExecution)
            .where(AutomationExecution.automation_trigger_id == automation_trigger_id)
            .order_by(AutomationExecution.started_at.desc())
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
    ) -> AutomationExecution | None:
        execution = await self.get(execution_id)
        if execution is None:
            return None
        execution.status = status
        execution.error = error
        execution.step_results_json = step_results_json
        execution.finished_at = finished_at
        await self._s.flush()
        return execution
