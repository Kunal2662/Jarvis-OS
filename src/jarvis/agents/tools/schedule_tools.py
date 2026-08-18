"""Agent tools wrapping
:class:`~jarvis.services.schedule_service.ScheduleService` (Milestone 7
Phase 6, Scheduler MVP).

**Five tools -- the minimum coherent surface** (Logic Contract §13):
``list_schedules``/``get_schedule``/``create_schedule``/
``enable_schedule``/``disable_schedule``. ``delete_schedule``/
``cancel_schedule`` are deliberately **not** exposed here -- destructive/
irreversible schedule management stays REST/UI-driven for MVP;
``disable_schedule`` already covers "stop this from running"
reversibly, the practical agent-facing need.

**Natural-language schedule interpretation is out of scope.**
``create_schedule`` takes structured parameters (a cron expression or
interval seconds, a workflow-step list) -- an LLM caller composing that
JSON from conversational context is not this codebase building new NLU
infrastructure.

**Not confirmation-gated.** ``create_schedule`` is not added to
``AgentSettings.confirm_required_tools`` -- creating a schedule does
not itself execute anything immediately; future execution of whatever
it schedules is independently, separately gated at run time (Logic
Contract §2/§12), unaffected by whether creation itself required
confirmation.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from langchain_core.tools import BaseTool, tool

from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.services.schedule_service import ScheduleService

_logger = get_logger("jarvis.agents.tools.schedule")

_MAX_RESULT_CHARS = 4_000


def build_schedule_tools(schedules: ScheduleService) -> list[BaseTool]:
    @tool
    async def list_schedules(enabled_only: bool = False) -> str:
        """List every schedule, optionally filtered to only enabled
        ones. Each entry shows its kind, cadence, timezone, enabled
        state, and next/last fire time."""
        try:
            rows = await schedules.list_schedules(enabled_only=enabled_only)
        except Exception as err:
            _logger.warning("list_schedules tool failed: {}", err)
            return f"Couldn't list schedules: {err}"
        if not rows:
            return "No schedules exist yet."
        return _clip(json.dumps(rows, indent=2, default=str))

    @tool
    async def get_schedule(schedule_id: str) -> str:
        """Get one schedule's full detail, including its most recent
        execution's outcome, by schedule id. Use list_schedules first
        to find the schedule id."""
        try:
            result = await schedules.get_schedule(schedule_id)
        except Exception as err:
            _logger.warning("get_schedule tool failed: {}", err)
            return f"Couldn't read that schedule: {err}"
        return _clip(json.dumps(result, indent=2, default=str))

    @tool
    async def create_schedule(
        name: str,
        kind: str,
        steps: list[dict[str, Any]],
        *,
        interval_seconds: float = 0.0,
        cron_expression: str = "",
        timezone: str = "",
        description: str = "",
    ) -> str:
        """Create a new unattended schedule. kind is 'interval' or
        'cron'. For 'interval', set interval_seconds (minimum 60). For
        'cron', set cron_expression (5-field POSIX syntax: minute hour
        day-of-month month day-of-week) -- compute the exact expression
        yourself, this tool does not interpret natural language.
        timezone is an IANA name (e.g. "Asia/Kolkata"); left blank, the
        server's own configured default is used. steps is an ordered
        list of workflow steps, each either
        {"kind": "automation", "instruction": "<natural-language
        instruction>"} or {"kind": "agent_tool", "tool_name": "<a
        registered tool name>", "tool_args": {...}}. A confirmation-
        required step (e.g. unlock_device, disarm) will always be
        denied when this schedule fires unattended -- there is no
        interactive confirmation channel for scheduled execution in
        this version."""
        try:
            result = await schedules.create_schedule(
                name=name,
                steps=steps,
                kind=kind,
                description=description,
                interval_seconds=interval_seconds,
                cron_expression=cron_expression,
                timezone=timezone or None,
            )
        except Exception as err:
            _logger.warning("create_schedule tool failed: {}", err)
            return f"Couldn't create that schedule: {err}"
        return _clip(json.dumps(result, indent=2, default=str))

    @tool
    async def enable_schedule(schedule_id: str) -> str:
        """Re-enable a previously disabled schedule so it resumes
        firing."""
        try:
            result = await schedules.enable_schedule(schedule_id)
        except Exception as err:
            _logger.warning("enable_schedule tool failed: {}", err)
            return f"Couldn't enable that schedule: {err}"
        return _clip(json.dumps(result, indent=2, default=str))

    @tool
    async def disable_schedule(schedule_id: str) -> str:
        """Pause a schedule -- it stops firing but is not deleted, and
        can be re-enabled later."""
        try:
            result = await schedules.disable_schedule(schedule_id)
        except Exception as err:
            _logger.warning("disable_schedule tool failed: {}", err)
            return f"Couldn't disable that schedule: {err}"
        return _clip(json.dumps(result, indent=2, default=str))

    return [list_schedules, get_schedule, create_schedule, enable_schedule, disable_schedule]


def _clip(text: str) -> str:
    if len(text) <= _MAX_RESULT_CHARS:
        return text
    return (
        text[:_MAX_RESULT_CHARS]
        + f"\n... (truncated at {_MAX_RESULT_CHARS} characters; narrow the query "
        "or ask for fewer results)"
    )
