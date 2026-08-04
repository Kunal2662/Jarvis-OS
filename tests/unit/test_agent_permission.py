"""Unit tests for :class:`AgentPermissionGate` (Milestone 10 AC3, interim)."""

from __future__ import annotations

import pytest

from jarvis.agents.permission import AgentPermissionGate


@pytest.mark.asyncio
async def test_tool_not_in_confirm_required_is_allowed_outright() -> None:
    gate = AgentPermissionGate(confirm_required_tools=frozenset({"run_automation"}))

    allowed, reason = await gate.authorize("recall_memory", {"query": "x"})

    assert allowed is True
    assert "No confirmation required" in reason


@pytest.mark.asyncio
async def test_confirm_required_tool_denied_when_no_callback_and_auto_deny() -> None:
    gate = AgentPermissionGate(
        confirm_required_tools=frozenset({"run_automation"}),
        auto_deny_when_unconfirmable=True,
    )

    allowed, reason = await gate.authorize("run_automation", {"instruction": "shutdown"})

    assert allowed is False
    assert "run_automation" in reason


@pytest.mark.asyncio
async def test_confirm_required_tool_allowed_when_callback_approves() -> None:
    gate = AgentPermissionGate(confirm_required_tools=frozenset({"run_automation"}))

    async def _approve(message: str) -> bool:
        assert "run_automation" in message
        return True

    allowed, reason = await gate.authorize(
        "run_automation", {"instruction": "shutdown"}, confirm=_approve
    )

    assert allowed is True
    assert reason == "User confirmed."


@pytest.mark.asyncio
async def test_confirm_required_tool_denied_when_callback_rejects() -> None:
    gate = AgentPermissionGate(confirm_required_tools=frozenset({"run_automation"}))

    async def _reject(message: str) -> bool:
        return False

    allowed, _reason = await gate.authorize(
        "run_automation", {"instruction": "shutdown"}, confirm=_reject
    )

    assert allowed is False


@pytest.mark.asyncio
async def test_auto_deny_when_unconfirmable_false_allows_by_default() -> None:
    gate = AgentPermissionGate(
        confirm_required_tools=frozenset({"run_automation"}),
        auto_deny_when_unconfirmable=False,
    )

    allowed, _reason = await gate.authorize("run_automation", {})

    assert allowed is True
