"""Permission gate -- the AI must never perform dangerous actions silently.

Combines a static per-action policy (delete / shutdown / restart / registry
/ terminal / admin / overwrite always need a human yes) with the dynamic
risk the :class:`~jarvis.features.automation.validator.SafetyValidator`
found for *this specific* instruction, then asks the caller-supplied
confirmation callback when required.
"""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Protocol, runtime_checkable

from jarvis.core.exceptions import AutomationPermissionDeniedError
from jarvis.core.logging.logger import get_logger
from jarvis.domain.automation.models import (
    ActionType,
    Intent,
    PermissionDecision,
    RiskLevel,
    ValidationIssue,
)

_logger = get_logger("jarvis.features.automation.permission")

# Actions that ALWAYS require an explicit human "yes", regardless of risk
# classification. This mirrors the milestone brief's fixed list: delete,
# shutdown, restart, registry, terminal, admin, file overwrite. ("registry"
# and "admin" are not standalone ActionTypes yet -- TERMINAL_COMMAND is the
# vector for both today; see Remaining TODOs.)
CONFIRM_REQUIRED_ACTIONS: frozenset[ActionType] = frozenset(
    {
        ActionType.DELETE_FOLDER,
        ActionType.EMPTY_RECYCLE_BIN,
        ActionType.SHUTDOWN,
        ActionType.RESTART,
        ActionType.SLEEP,
        ActionType.TERMINAL_COMMAND,
    }
)

_RISK_ORDER = [RiskLevel.SAFE, RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]


@runtime_checkable
class ConfirmationCallback(Protocol):
    """Awaited with a human-readable prompt; returns True to proceed."""

    def __call__(self, message: str) -> Awaitable[bool]: ...


async def _default_deny(message: str) -> bool:
    _logger.warning("No confirmation channel available -- auto-denying: {}", message)
    return False


class PermissionGate:
    """Decides ALLOW / REQUIRE_CONFIRMATION / DENY for one :class:`Intent`."""

    def __init__(self, *, auto_deny_when_unconfirmable: bool = True) -> None:
        self._auto_deny_when_unconfirmable = auto_deny_when_unconfirmable

    def decide(
        self, intent: Intent, issues: list[ValidationIssue]
    ) -> tuple[PermissionDecision, str]:
        if any(i.risk is RiskLevel.CRITICAL for i in issues):
            reason = "; ".join(i.reason for i in issues if i.risk is RiskLevel.CRITICAL)
            return PermissionDecision.DENY, reason or "Blocked by safety validator."

        highest = max((i.risk for i in issues), key=_RISK_ORDER.index, default=RiskLevel.SAFE)

        if intent.action in CONFIRM_REQUIRED_ACTIONS or highest in (
            RiskLevel.MEDIUM,
            RiskLevel.HIGH,
        ):
            return (
                PermissionDecision.REQUIRE_CONFIRMATION,
                f"{intent.action.value} is a sensitive action and needs your confirmation.",
            )

        return PermissionDecision.ALLOW, "No safety concerns."

    async def authorize(
        self,
        intent: Intent,
        issues: list[ValidationIssue],
        *,
        confirm: ConfirmationCallback | None = None,
    ) -> bool:
        """Returns True if the caller may proceed; raises on hard denial."""
        decision, reason = self.decide(intent, issues)

        if decision is PermissionDecision.DENY:
            _logger.warning("Denied {}: {}", intent.action.value, reason)
            raise AutomationPermissionDeniedError(reason)

        if decision is PermissionDecision.ALLOW:
            return True

        # REQUIRE_CONFIRMATION
        callback = confirm or (
            _default_deny if self._auto_deny_when_unconfirmable else _always_allow
        )
        prompt = self._build_prompt(intent, reason)
        approved = await callback(prompt)
        if not approved:
            _logger.info("User declined confirmation for {}.", intent.action.value)
            raise AutomationPermissionDeniedError(f"User did not confirm: {reason}")
        return True

    @staticmethod
    def _build_prompt(intent: Intent, reason: str) -> str:
        target = f" ({intent.target})" if intent.target else ""
        return f"Confirm {intent.action.value}{target}? {reason}"


async def _always_allow(message: str) -> bool:  # pragma: no cover -- opt-in escape hatch
    _logger.warning("auto_deny_when_unconfirmable=False -- auto-approving: {}", message)
    return True
