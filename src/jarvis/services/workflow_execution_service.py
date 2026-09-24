"""Workflow execution service -- Milestone 7 (Home Automation slice).

Extracted, verbatim in behavior, from ``ScheduleService``'s own
private ``_run_workflow``/``_run_step``/``_run_automation_step``/
``_run_agent_tool_step`` methods -- see
``docs/M7_HOME_AUTOMATION_LOGIC_CONTRACT.md`` §8 for the full
extraction decision and its exact boundary. This is the **shared
execution owner** both ``ScheduleService`` (time-based triggers) and
``HomeAutomationService`` (event-based triggers) delegate to, so
neither duplicates workflow execution and neither is a second
execution engine.

**Policy A (always deny) is preserved exactly**: every call site below
supplies ``confirm=None`` -- no confirmation channel exists for either
caller, and both existing gates (``PermissionGate`` inside
``AutomationService``/``ActionExecutor``, and ``AgentPermissionGate``
here) already fail-safe to a denial with no callback. This service
introduces zero new authorization code.

**Two ``WorkflowStep`` kinds, unchanged**: ``AUTOMATION`` routes
through ``AutomationService.run_command`` (OS-automation engine, its
own per-step retry/timeout/rollback machinery, untouched);
``AGENT_TOOL`` routes through the same tool-registry/
``AgentPermissionGate`` pattern ``AgentOrchestrator`` itself uses for a
live agent turn -- a second *instance* of the gate, not a second
*implementation* (its own constructor-time config makes multiple
instances behaviorally interchangeable)."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from jarvis.agents.permission import AgentPermissionGate
from jarvis.agents.tools import build_tool_registry
from jarvis.core.logging.logger import get_logger
from jarvis.domain.workflow.models import WorkflowStepKind

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

    from jarvis.core.config.settings import Settings
    from jarvis.services.automation_service import AutomationService

_logger = get_logger("jarvis.services.workflow_execution")


class WorkflowExecutionService:
    def __init__(
        self,
        *,
        settings: Settings,
        automation: AutomationService | None = None,
        memory: Any | None = None,
        browser: Any | None = None,
        chat: Any | None = None,
        voice: Any | None = None,
        system: Any | None = None,
        vision: Any | None = None,
        knowledge: Any | None = None,
        intelligence: Any | None = None,
        workspace_assistant: Any | None = None,
        integrations: Any | None = None,
        smart_lighting: Any | None = None,
        smart_lock: Any | None = None,
        sensors: Any | None = None,
        smart_switch: Any | None = None,
        appliances: Any | None = None,
        thermostats: Any | None = None,
        vacuum_humidifier: Any | None = None,
        media_players: Any | None = None,
        water_heaters: Any | None = None,
        security: Any | None = None,
        siren: Any | None = None,
        alarm_control_panels: Any | None = None,
        smart_home_memory: Any | None = None,
    ) -> None:
        self._settings = settings
        self._automation = automation
        # Identical optional-service set `ScheduleService`/
        # `AgentOrchestrator`/`container.py`'s own `_build_agent_
        # orchestrator` already assemble, reused verbatim -- a workflow
        # step reaches any tool a live agent turn or a schedule already
        # can, regardless of which caller (Scheduler, Home Automation)
        # dispatched it.
        self._tool_services: dict[str, Any] = {
            "memory": memory,
            "browser": browser,
            "chat": chat,
            "voice": voice,
            "system": system,
            "vision": vision,
            "knowledge": knowledge,
            "intelligence": intelligence,
            "workspace_assistant": workspace_assistant,
            "integrations": integrations,
            "smart_lighting": smart_lighting,
            "smart_lock": smart_lock,
            "sensors": sensors,
            "smart_switch": smart_switch,
            "appliances": appliances,
            "thermostats": thermostats,
            "vacuum_humidifier": vacuum_humidifier,
            "media_players": media_players,
            "water_heaters": water_heaters,
            "security": security,
            "siren": siren,
            "alarm_control_panels": alarm_control_panels,
            "smart_home_memory": smart_home_memory,
            "automation": automation,
        }
        self._tools_by_name: dict[str, BaseTool] | None = None
        self._gate: AgentPermissionGate | None = None

    # ------------------------------------------------------------------
    # Agent-tool execution path (AGENT_TOOL-kind steps only)
    # ------------------------------------------------------------------
    def _ensure_tools_ready(self) -> None:
        """Lazily builds this service's own tool registry and its own
        `AgentPermissionGate` instance -- built once, shared by every
        caller of this service."""
        if self._tools_by_name is not None and self._gate is not None:
            return
        tools = build_tool_registry(**self._tool_services)
        self._tools_by_name = {t.name: t for t in tools}
        self._gate = AgentPermissionGate(
            confirm_required_tools=self._settings.agent.confirm_required_tools,
        )

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    async def run_workflow(
        self, steps: list[dict[str, Any]]
    ) -> tuple[str, str | None, list[dict[str, Any]]]:
        """Executes *steps* sequentially (`depends_on`-based parallel
        dispatch is out of scope here, unchanged from the pre-extraction
        behavior). Returns the workflow-level status, an optional
        top-level error summary, and the per-step result list."""
        results: list[dict[str, Any]] = []
        for step in steps:
            started = asyncio.get_event_loop().time()
            step_status, step_error = await self._run_step(step)
            duration_ms = (asyncio.get_event_loop().time() - started) * 1000
            results.append(
                {
                    "step_id": step.get("id", ""),
                    "status": step_status,
                    "error": step_error,
                    "duration_ms": duration_ms,
                }
            )

        succeeded = sum(1 for r in results if r["status"] == "succeeded")
        denied = sum(1 for r in results if r["status"] == "denied")
        failed = sum(1 for r in results if r["status"] == "failed")
        total = len(results)

        if succeeded == total:
            return "succeeded", None, results
        if succeeded == 0 and failed == 0 and denied == total:
            return "denied", "Every step in this workflow was denied.", results
        if succeeded == 0:
            return "failed", "No step in this workflow succeeded.", results
        return "partially_failed", "Some steps in this workflow did not succeed.", results

    async def _run_step(self, step: dict[str, Any]) -> tuple[str, str | None]:
        if step.get("kind") == WorkflowStepKind.AUTOMATION.value:
            return await self._run_automation_step(step)
        return await self._run_agent_tool_step(step)

    async def _run_automation_step(self, step: dict[str, Any]) -> tuple[str, str | None]:
        if self._automation is None:
            return "failed", "Automation service is not available."
        # No `confirm` supplied -- Policy A. Any confirm-required action
        # inside this instruction is denied by `PermissionGate` itself,
        # internally, and surfaces as a `StepStatus.DENIED` entry in
        # `PlanResult.step_results` -- `AutomationPermissionDeniedError`
        # never propagates out of `run_command`.
        result = await self._automation.run_command(step.get("instruction", ""))
        if result.plan_id == "disabled":
            return "failed", "Automation is disabled (AutomationSettings.enabled=False)."
        if result.succeeded:
            return "succeeded", None
        denied_statuses = {r.status.value for r in result.step_results}
        if denied_statuses and denied_statuses <= {"denied"}:
            errors = "; ".join(r.error or "" for r in result.step_results if r.error)
            return "denied", errors or "Denied: confirmation required."
        errors = "; ".join(r.error or "" for r in result.step_results if r.error)
        return "failed", errors or "Automation instruction failed."

    async def _run_agent_tool_step(self, step: dict[str, Any]) -> tuple[str, str | None]:
        self._ensure_tools_ready()
        assert self._tools_by_name is not None
        assert self._gate is not None

        tool_name = step.get("tool_name", "")
        tool_args = step.get("tool_args") or {}
        tool = self._tools_by_name.get(tool_name)
        if tool is None:
            return "failed", f"Unknown tool: {tool_name!r}."

        # No `confirm` supplied -- Policy A. `authorize()` never raises;
        # it returns a plain (allowed, reason) pair.
        allowed, reason = await self._gate.authorize(tool_name, tool_args, confirm=None)
        if not allowed:
            return "denied", f"Denied: {reason}"

        try:
            await tool.ainvoke(tool_args)
        except Exception as err:  # a step failure must not crash the caller
            _logger.warning("Workflow tool {!r} failed: {}", tool_name, err)
            return "failed", str(err)
        return "succeeded", None
