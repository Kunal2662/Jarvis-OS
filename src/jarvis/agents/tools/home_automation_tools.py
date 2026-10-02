"""Agent tools wrapping
:class:`~jarvis.services.home_automation_service.HomeAutomationService`
(M7 Home Automation).

**Six tools -- the minimum coherent surface** (Logic Contract §23):
``list_home_automations``/``get_home_automation``/
``create_home_automation``/``enable_home_automation``/
``disable_home_automation``/``run_home_automation``.
``delete_home_automation`` is deliberately **not** exposed here --
destructive/irreversible automation management stays REST/UI-driven
for MVP, mirroring ``schedule_tools.py``'s own identical precedent
exactly; ``disable_home_automation`` already covers "stop this from
firing" reversibly, the practical agent-facing need.

**No condition/attribute-trigger authoring.** ``create_home_automation``
only accepts a single device_id + target status + optional previous
status -- the exact MVP trigger shape the backend supports (Logic
Contract §11/§12). It does not accept, and cannot express, an
attribute-level trigger.

**Not confirmation-gated.** ``create_home_automation`` is not added to
``AgentSettings.confirm_required_tools`` -- creating an automation does
not itself execute anything immediately; future execution of whatever
it triggers is independently, separately gated at dispatch time (Logic
Contract §17/§18), unaffected by whether creation itself required
confirmation. ``run_home_automation`` does not bypass that gate either
-- see its own docstring below.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from langchain_core.tools import BaseTool, tool

from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.services.home_automation_service import HomeAutomationService

_logger = get_logger("jarvis.agents.tools.home_automation")

_MAX_RESULT_CHARS = 4_000


def build_home_automation_tools(home_automation: HomeAutomationService) -> list[BaseTool]:
    @tool
    async def list_home_automations(enabled_only: bool = False) -> str:
        """List every Home Automation trigger, optionally filtered to
        only enabled ones. Each entry shows the device it watches, the
        required status transition, enabled state, and last-fired
        time."""
        try:
            rows = await home_automation.list_automations(enabled_only=enabled_only)
        except Exception as err:
            _logger.warning("list_home_automations tool failed: {}", err)
            return f"Couldn't list automations: {err}"
        if not rows:
            return "No Home Automations exist yet."
        return _clip(json.dumps(rows, indent=2, default=str))

    @tool
    async def get_home_automation(automation_id: str) -> str:
        """Get one Home Automation's full detail, including its most
        recent execution's outcome, by automation id. Use
        list_home_automations first to find the automation id."""
        try:
            result = await home_automation.get_automation(automation_id)
        except Exception as err:
            _logger.warning("get_home_automation tool failed: {}", err)
            return f"Couldn't read that automation: {err}"
        return _clip(json.dumps(result, indent=2, default=str))

    @tool
    async def create_home_automation(
        name: str,
        device_id: str,
        to_status: str,
        steps: list[dict[str, Any]],
        *,
        from_status: str = "",
        description: str = "",
    ) -> str:
        """Create a new event-triggered automation: when device_id's
        status transitions to to_status (optionally, only when
        transitioning FROM from_status specifically -- leave from_status
        blank to match any previous status), run steps. status values
        are whatever the device's own lifecycle reports (e.g. "paired",
        "offline", "unreachable") -- this does not support attribute
        triggers like temperature or brightness. steps is an ordered
        list of workflow steps, each either {"kind": "automation",
        "instruction": "<natural-language instruction>"} or {"kind":
        "agent_tool", "tool_name": "<a registered tool name>",
        "tool_args": {...}}. A confirmation-required step (e.g.
        unlock_device, disarm) will always be denied when this
        automation fires unattended -- there is no interactive
        confirmation channel for event-triggered execution in this
        version."""
        try:
            result = await home_automation.create_automation(
                name=name,
                device_id=device_id,
                to_status=to_status,
                steps=steps,
                from_status=from_status,
                description=description,
            )
        except Exception as err:
            _logger.warning("create_home_automation tool failed: {}", err)
            return f"Couldn't create that automation: {err}"
        return _clip(json.dumps(result, indent=2, default=str))

    @tool
    async def enable_home_automation(automation_id: str) -> str:
        """Re-enable a previously disabled automation so it resumes
        firing on matching events."""
        try:
            result = await home_automation.enable_automation(automation_id)
        except Exception as err:
            _logger.warning("enable_home_automation tool failed: {}", err)
            return f"Couldn't enable that automation: {err}"
        return _clip(json.dumps(result, indent=2, default=str))

    @tool
    async def disable_home_automation(automation_id: str) -> str:
        """Pause an automation -- it stops firing on matching events but
        is not deleted, and can be re-enabled later."""
        try:
            result = await home_automation.disable_automation(automation_id)
        except Exception as err:
            _logger.warning("disable_home_automation tool failed: {}", err)
            return f"Couldn't disable that automation: {err}"
        return _clip(json.dumps(result, indent=2, default=str))

    @tool
    async def run_home_automation(automation_id: str) -> str:
        """Manually run an automation's workflow right now, as a test --
        reuses the exact same execution path an actual matching device
        event would use, including the same permission and confirmation
        checks (a confirmation-required step is still denied). Useful
        to verify an automation behaves as expected without waiting for
        the real device transition."""
        try:
            result = await home_automation.run_automation(automation_id)
        except Exception as err:
            _logger.warning("run_home_automation tool failed: {}", err)
            return f"Couldn't run that automation: {err}"
        return _clip(json.dumps(result, indent=2, default=str))

    return [
        list_home_automations,
        get_home_automation,
        create_home_automation,
        enable_home_automation,
        disable_home_automation,
        run_home_automation,
    ]


def _clip(text: str) -> str:
    if len(text) <= _MAX_RESULT_CHARS:
        return text
    return (
        text[:_MAX_RESULT_CHARS]
        + f"\n... (truncated at {_MAX_RESULT_CHARS} characters; narrow the query "
        "or ask for fewer results)"
    )
