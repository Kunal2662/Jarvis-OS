"""Workflow Builder execution repository -- M7 Workflow Builder.

One small repository over ``workflow_builder_executions``, following
``automation_repository.py``'s shape exactly: constructed with an
``AsyncSession``, no session or transaction management of its own (the
service owns that via ``db.session()``), ``flush()`` rather than
``commit()`` after a write so the caller's transaction boundary stays
the caller's. No ``has_non_terminal``/duplicate-fire check -- there is
no trigger, so no automatic re-fire risk to guard against (Logic
Contract §9). See ``docs/M7_WORKFLOW_BUILDER_LOGIC_CONTRACT.md`` §6.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jarvis.infrastructure.database.models import WorkflowBuilderExecution


class WorkflowBuilderExecutionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, *, workflow_id: str, status: str = "queued") -> WorkflowBuilderExecution:
        execution = WorkflowBuilderExecution(
            workflow_id=workflow_id, source="manual", status=status
        )
        self._s.add(execution)
        await self._s.flush()
        return execution

    async def get(self, execution_id: str) -> WorkflowBuilderExecution | None:
        return await self._s.get(WorkflowBuilderExecution, execution_id)

    async def list_for_workflow(
        self, workflow_id: str, *, limit: int = 50, offset: int = 0
    ) -> list[WorkflowBuilderExecution]:
        stmt = (
            select(WorkflowBuilderExecution)
            .where(WorkflowBuilderExecution.workflow_id == workflow_id)
            .order_by(WorkflowBuilderExecution.started_at.desc())
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
    ) -> WorkflowBuilderExecution | None:
        execution = await self.get(execution_id)
        if execution is None:
            return None
        execution.status = status
        execution.error = error
        execution.step_results_json = step_results_json
        execution.finished_at = finished_at
        await self._s.flush()
        return execution
