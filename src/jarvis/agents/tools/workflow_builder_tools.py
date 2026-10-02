"""Agent tools wrapping
:class:`~jarvis.services.workflow_builder_service.WorkflowBuilderService`
(M7 Workflow Builder).

**Five tools -- the minimum coherent surface** (Logic Contract §14):
``list_workflows``/``get_workflow``/``create_workflow``/
``update_workflow``/``run_workflow``. ``delete_workflow`` is
deliberately **not** exposed here -- destructive/irreversible workflow
management stays REST/UI-driven for MVP, mirroring
``schedule_tools.py``/``home_automation_tools.py``'s own identical
precedent exactly.

**Standalone only.** A workflow authored here is never attached to a
Schedule or Automation Trigger (Logic Contract §6) -- these tools
manage only the workflow's own name/description/steps and its manual
execution history.

**Not confirmation-gated.** ``create_workflow``/``update_workflow`` are
not added to ``AgentSettings.confirm_required_tools`` -- authoring a
workflow does not itself execute anything; execution is independently,
separately gated at run time (Logic Contract §12), unaffected by
whether authoring itself required confirmation. ``run_workflow`` does
not bypass that gate either -- see its own docstring below.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from langchain_core.tools import BaseTool, tool

from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.services.workflow_builder_service import WorkflowBuilderService

_logger = get_logger("jarvis.agents.tools.workflow_builder")

_MAX_RESULT_CHARS = 4_000


def build_workflow_builder_tools(workflow_builder: WorkflowBuilderService) -> list[BaseTool]:
    @tool
    async def list_workflows() -> str:
        """List every standalone workflow authored via Workflow
        Builder. Each entry shows its name, description, and step
        list."""
        try:
            rows = await workflow_builder.list_workflows()
        except Exception as err:
            _logger.warning("list_workflows tool failed: {}", err)
            return f"Couldn't list workflows: {err}"
        if not rows:
            return "No workflows exist yet."
        return _clip(json.dumps(rows, indent=2, default=str))

    @tool
    async def get_workflow(workflow_id: str) -> str:
        """Get one workflow's full detail, including its steps, by
        workflow id. Use list_workflows first to find the workflow
        id."""
        try:
            result = await workflow_builder.get_workflow(workflow_id)
        except Exception as err:
            _logger.warning("get_workflow tool failed: {}", err)
            return f"Couldn't read that workflow: {err}"
        return _clip(json.dumps(result, indent=2, default=str))

    @tool
    async def create_workflow(
        name: str,
        steps: list[dict[str, Any]],
        *,
        description: str = "",
    ) -> str:
        """Create a new standalone workflow -- an ordered list of steps
        you can run manually later. Not attached to any schedule or
        device trigger. steps is an ordered list of workflow steps,
        each either {"kind": "automation", "instruction": "<natural-
        language instruction>"} or {"kind": "agent_tool", "tool_name":
        "<a registered tool name>", "tool_args": {...}}. At least one
        step is required."""
        try:
            result = await workflow_builder.create_workflow(
                name=name, steps=steps, description=description
            )
        except Exception as err:
            _logger.warning("create_workflow tool failed: {}", err)
            return f"Couldn't create that workflow: {err}"
        return _clip(json.dumps(result, indent=2, default=str))

    @tool
    async def update_workflow(
        workflow_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        steps: list[dict[str, Any]] | None = None,
    ) -> str:
        """Edit an existing workflow -- only the fields you supply
        change. Supplying steps replaces the entire step list (it is
        not merged with the existing one); leave it unset to keep the
        workflow's current steps."""
        try:
            result = await workflow_builder.update_workflow(
                workflow_id, name=name, description=description, steps=steps
            )
        except Exception as err:
            _logger.warning("update_workflow tool failed: {}", err)
            return f"Couldn't update that workflow: {err}"
        return _clip(json.dumps(result, indent=2, default=str))

    @tool
    async def run_workflow(workflow_id: str) -> str:
        """Run a workflow's steps right now, in order -- the only way
        a standalone workflow ever executes, since it has no trigger.
        Uses the same permission and confirmation checks as any other
        execution path (a confirmation-required step is still
        denied)."""
        try:
            result = await workflow_builder.run_workflow(workflow_id)
        except Exception as err:
            _logger.warning("run_workflow tool failed: {}", err)
            return f"Couldn't run that workflow: {err}"
        return _clip(json.dumps(result, indent=2, default=str))

    return [
        list_workflows,
        get_workflow,
        create_workflow,
        update_workflow,
        run_workflow,
    ]


def _clip(text: str) -> str:
    if len(text) <= _MAX_RESULT_CHARS:
        return text
    return (
        text[:_MAX_RESULT_CHARS]
        + f"\n... (truncated at {_MAX_RESULT_CHARS} characters; narrow the query "
        "or ask for fewer results)"
    )
