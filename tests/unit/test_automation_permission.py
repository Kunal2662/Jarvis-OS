"""Unit tests for :class:`PermissionGate`."""

from __future__ import annotations

import pytest

from jarvis.core.exceptions import AutomationPermissionDeniedError
from jarvis.domain.automation.models import (
    ActionType,
    Intent,
    PermissionDecision,
    RiskLevel,
    ValidationIssue,
)
from jarvis.features.automation.permission import PermissionGate


def test_safe_action_with_no_issues_is_allowed() -> None:
    gate = PermissionGate()
    intent = Intent(action=ActionType.OPEN_APP, target="Chrome")
    decision, _ = gate.decide(intent, [])
    assert decision is PermissionDecision.ALLOW


def test_delete_folder_always_requires_confirmation_even_with_no_issues() -> None:
    gate = PermissionGate()
    intent = Intent(action=ActionType.DELETE_FOLDER, target="Work")
    decision, _ = gate.decide(intent, [])
    assert decision is PermissionDecision.REQUIRE_CONFIRMATION


def test_critical_issue_is_denied() -> None:
    gate = PermissionGate()
    intent = Intent(action=ActionType.TERMINAL_COMMAND, arguments={"command": "rm -rf /"})
    issues = [ValidationIssue(RiskLevel.CRITICAL, "destructive pattern")]
    decision, _ = gate.decide(intent, issues)
    assert decision is PermissionDecision.DENY


@pytest.mark.asyncio
async def test_authorize_raises_on_deny() -> None:
    gate = PermissionGate()
    intent = Intent(action=ActionType.TERMINAL_COMMAND, arguments={"command": "rm -rf /"})
    issues = [ValidationIssue(RiskLevel.CRITICAL, "destructive pattern")]
    with pytest.raises(AutomationPermissionDeniedError):
        await gate.authorize(intent, issues)


@pytest.mark.asyncio
async def test_authorize_calls_confirmation_callback_and_honours_it() -> None:
    gate = PermissionGate()
    intent = Intent(action=ActionType.SHUTDOWN)
    calls: list[str] = []

    async def confirm(message: str) -> bool:
        calls.append(message)
        return True

    approved = await gate.authorize(intent, [], confirm=confirm)
    assert approved is True
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_authorize_denies_when_confirmation_declined() -> None:
    gate = PermissionGate()
    intent = Intent(action=ActionType.SHUTDOWN)

    async def confirm(message: str) -> bool:
        return False

    with pytest.raises(AutomationPermissionDeniedError):
        await gate.authorize(intent, [], confirm=confirm)


@pytest.mark.asyncio
async def test_authorize_auto_denies_when_no_callback_supplied() -> None:
    gate = PermissionGate(auto_deny_when_unconfirmable=True)
    intent = Intent(action=ActionType.SHUTDOWN)
    with pytest.raises(AutomationPermissionDeniedError):
        await gate.authorize(intent, [])
