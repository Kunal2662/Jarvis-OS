"""Agent-level Permission Validation (Milestone 10 AC3, interim).

The single enforcement point every proposed tool call now passes through
before execution, replacing the pre-M10 gap where only ``run_automation``
had any permission awareness at all (via
``features/automation/permission.py``'s ``PermissionGate``, internal to
``AutomationService`` and invisible to the graph) and every other tool
(memory writes, browser navigation, ...) executed with no check whatsoever.

Interim, not final: M10's own spec says Permission Validation "routes every
tool invocation through M14's Authorization Engine once that milestone
ships" -- M14 (Security Platform / Authorization Engine) has not shipped
(``docs/MASTER_ROADMAP.md``, status Planned). ``AgentPermissionGate`` is
deliberately a single, narrow class so that swapping in a real M14-backed
implementation later means replacing this class's ``authorize()`` body, not
touching the graph wiring (``agents/nodes/permission_validator.py``,
``agents/graph.py``) that calls it -- the same "ad-hoc per-tool checks
replaced by one enforcement point" migration path M10 describes for itself.

Reuses ``features/automation/permission.py``'s ``ConfirmationCallback``
protocol rather than redefining an identical one -- the same
awaitable-prompt-returns-bool shape applies at this layer unchanged.
"""

from __future__ import annotations

from typing import Any

from jarvis.core.logging.logger import get_logger
from jarvis.features.automation.permission import ConfirmationCallback

_logger = get_logger("jarvis.agents.permission")


async def _default_deny(message: str) -> bool:
    _logger.warning(
        "No confirmation channel available for agent tool call -- auto-denying: {}", message
    )
    return False


async def _always_allow(message: str) -> bool:  # pragma: no cover -- opt-in escape hatch
    _logger.warning(
        "Agent permission auto_deny_when_unconfirmable=False -- auto-approving: {}", message
    )
    return True


class AgentPermissionGate:
    """ALLOW / REQUIRE_CONFIRMATION for one proposed agent tool call.

    Policy is deliberately simple and declarative: tool names in
    ``confirm_required_tools`` need an explicit confirmation; everything
    else is allowed outright. This mirrors ``PermissionGate``'s
    "sensitive actions always need a human yes" model at the coarser
    granularity available before a real per-tool risk classifier (M14's
    job) exists.
    """

    def __init__(
        self,
        *,
        confirm_required_tools: frozenset[str] = frozenset(),
        auto_deny_when_unconfirmable: bool = True,
    ) -> None:
        self._confirm_required = confirm_required_tools
        self._auto_deny_when_unconfirmable = auto_deny_when_unconfirmable

    async def authorize(
        self,
        tool_name: str,
        args: dict[str, Any],
        *,
        confirm: ConfirmationCallback | None = None,
    ) -> tuple[bool, str]:
        """Returns ``(allowed, reason)``. Never raises."""
        if tool_name not in self._confirm_required:
            return True, "No confirmation required."

        callback = confirm or (
            _default_deny if self._auto_deny_when_unconfirmable else _always_allow
        )
        prompt = f"Agent wants to call {tool_name}({args}). Allow?"
        approved = await callback(prompt)
        if approved:
            return True, "User confirmed."
        return False, f"{tool_name} requires confirmation and was not approved."
