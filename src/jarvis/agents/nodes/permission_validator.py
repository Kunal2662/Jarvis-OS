"""Permission-validator node (Milestone 10 AC3, interim) -- the one point
in the graph every proposed tool call passes through before
``tool_executor`` gets to run it. See ``agents/permission.py`` for the
policy this node enforces and why it is explicitly interim pending M14.

Denied calls are written directly into ``tool_calls`` as error entries
(the same shape ``tool_executor`` already produces for an unknown tool or a
failed call) and never reach ``tool_executor`` at all -- a denial is a
terminal outcome for that call, not a retryable error.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from jarvis.agents.state import AgentState

if TYPE_CHECKING:
    from jarvis.agents.permission import AgentPermissionGate
    from jarvis.features.automation.permission import ConfirmationCallback


def make_permission_validator_node(
    gate: AgentPermissionGate,
    *,
    confirm: ConfirmationCallback | None = None,
) -> Callable[[AgentState], Awaitable[dict[str, Any]]]:
    async def permission_validator_node(state: AgentState) -> dict[str, Any]:
        tool_calls = list(state.get("tool_calls", []))

        if state.get("next_action") == "tool_parallel":
            calls = state.get("pending_tool_calls") or []
            approved: list[dict[str, Any]] = []
            denied_count = 0
            for call in calls:
                name = call.get("tool", "")
                args = call.get("args") or {}
                allowed, reason = await gate.authorize(name, args, confirm=confirm)
                if allowed:
                    approved.append(call)
                else:
                    tool_calls.append({"tool": name, "args": args, "error": f"Denied: {reason}"})
                    denied_count += 1
            return {
                "pending_tool_calls": approved,
                "tool_calls": tool_calls,
                "step": state.get("step", 0) + denied_count,
                "last_node": "permission_validator",
            }

        name = state.get("tool_name", "")
        args = state.get("tool_args") or {}
        allowed, reason = await gate.authorize(name, args, confirm=confirm)
        if allowed:
            return {"permission_denied": False, "last_node": "permission_validator"}

        tool_calls.append({"tool": name, "args": args, "error": f"Denied: {reason}"})
        return {
            "permission_denied": True,
            "tool_calls": tool_calls,
            "step": state.get("step", 0) + 1,
            "last_node": "permission_validator",
        }

    return permission_validator_node
