"""Agent tools wrapping :class:`~jarvis.services.automation_service.AutomationService`.

No confirmation callback is passed to ``run_command`` — per
``AutomationSettings.auto_deny_when_unconfirmable`` (default ``True``,
see ``core/config/settings.py``), any action that would normally need an
interactive confirmation is auto-denied rather than silently proceeding.
The agent has no UI to prompt through yet, so "deny by default" is the
only safe behavior; wiring a real confirmation surface is future work
(see the milestone delivery doc's Remaining Work section).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool, tool

from jarvis.core.exceptions import AutomationError, AutomationPermissionDeniedError
from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.services.automation_service import AutomationService

_logger = get_logger("jarvis.agents.tools.automation")


def build_automation_tools(automation: AutomationService) -> list[BaseTool]:
    @tool
    async def run_automation(instruction: str) -> str:
        """Execute a desktop, file, or system automation instruction phrased
        in plain English (e.g. "open notepad", "create a folder named
        Reports", "search google for python tutorials"). Dangerous or
        destructive actions are automatically denied rather than confirmed,
        since this tool has no interactive prompt available."""
        try:
            result = await automation.run_command(instruction)
        except AutomationPermissionDeniedError as err:
            return f"Denied: {err}"
        except AutomationError as err:
            _logger.warning("run_automation tool failed: {}", err)
            return f"Automation failed: {err}"
        failed = result.failed_steps
        if failed:
            return f"Plan {result.plan_id} finished with {len(failed)} failed step(s)."
        return f"Plan {result.plan_id} completed successfully ({len(result.step_results)} step(s))."

    return [run_automation]
