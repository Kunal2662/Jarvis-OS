"""WorkflowExecutionService tests -- M7 (Home Automation Logic Contract
§8 extraction).

Verifies the extracted service in isolation -- not merely indirectly
via the Scheduler regression -- covering both ``WorkflowStep`` kinds,
failure aggregation across a multi-step workflow, and that the lazy
tool registry/``AgentPermissionGate`` is built once and reused across
calls. Real (temp-file) SQLite where a real device-category service is
needed; ``FakeOSAutomation`` for the OS-automation side effect
boundary, matching every sibling test file's own convention.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.services.workflow_execution_service import WorkflowExecutionService


def _settings(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JARVIS_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'jarvis.db'}")

    from jarvis.core.config import settings as settings_mod

    settings_mod.load_settings.cache_clear()  # type: ignore[attr-defined]
    return settings_mod.load_settings()


@pytest.fixture
async def db(tmp_path: Path, monkeypatch):
    settings = _settings(tmp_path, monkeypatch)
    from jarvis.infrastructure.database.sqlite_client import SQLiteDatabase

    database = SQLiteDatabase(settings.db)
    await database.initialize()
    try:
        yield database
    finally:
        await database.dispose()


@pytest.fixture
def settings(tmp_path: Path, monkeypatch):
    return _settings(tmp_path, monkeypatch)


@pytest.fixture
def automation(settings, db):
    from jarvis.services.automation_service import AutomationService
    from tests.fakes.fake_os_automation import FakeOSAutomation

    return AutomationService(FakeOSAutomation(), settings, database=db)


def _agent_tool_step(tool_name: str) -> dict:
    return {"kind": "agent_tool", "tool_name": tool_name, "tool_args": {}}


def _automation_step(instruction: str) -> dict:
    return {"kind": "automation", "instruction": instruction}


@pytest.mark.asyncio
async def test_unknown_agent_tool_step_fails(settings) -> None:
    executor = WorkflowExecutionService(settings=settings)

    status, _error, results = await executor.run_workflow([_agent_tool_step("no_such_tool")])

    assert status == "failed"
    assert results[0]["status"] == "failed"
    assert "Unknown tool" in results[0]["error"]


@pytest.mark.asyncio
async def test_automation_step_succeeds(automation, settings) -> None:
    executor = WorkflowExecutionService(settings=settings, automation=automation)

    status, error, results = await executor.run_workflow([_automation_step("take a screenshot")])

    assert status == "succeeded"
    assert error is None
    assert results[0]["status"] == "succeeded"


@pytest.mark.asyncio
async def test_automation_step_fails_gracefully_with_no_automation_service(settings) -> None:
    executor = WorkflowExecutionService(settings=settings)  # no automation=

    status, _error, results = await executor.run_workflow([_automation_step("x")])

    assert status == "failed"
    assert results[0]["status"] == "failed"
    assert "Automation service is not available" in results[0]["error"]


@pytest.mark.asyncio
async def test_mixed_success_and_failure_is_partially_failed(automation, settings) -> None:
    executor = WorkflowExecutionService(settings=settings, automation=automation)

    status, _error, results = await executor.run_workflow(
        [_automation_step("take a screenshot"), _agent_tool_step("no_such_tool")]
    )

    assert status == "partially_failed"
    assert results[0]["status"] == "succeeded"
    assert results[1]["status"] == "failed"


@pytest.mark.asyncio
async def test_confirm_required_agent_tool_step_is_denied_not_auto_approved(
    automation, settings
) -> None:
    """Policy A -- confirm=None is hardcoded, verified behaviorally: a
    confirm-required tool with no confirm callback available is denied,
    never silently auto-approved. Uses run_automation (registered via
    the `automation` fixture) rather than unlock_device -- an
    unregistered tool name would hit the "Unknown tool" branch before
    ever reaching the confirmation gate, proving nothing about Policy A
    specifically."""
    executor = WorkflowExecutionService(settings=settings, automation=automation)

    status, _error, results = await executor.run_workflow([_agent_tool_step("run_automation")])

    assert status == "denied"
    assert results[0]["status"] == "denied"


@pytest.mark.asyncio
async def test_tool_registry_and_gate_are_built_once_and_reused(settings) -> None:
    executor = WorkflowExecutionService(settings=settings)

    await executor.run_workflow([_agent_tool_step("no_such_tool")])
    first_tools = executor._tools_by_name
    first_gate = executor._gate
    await executor.run_workflow([_agent_tool_step("also_no_such_tool")])

    assert executor._tools_by_name is first_tools
    assert executor._gate is first_gate


def test_workflow_execution_service_never_supplies_a_confirm_callback() -> None:
    import inspect

    from jarvis.services import workflow_execution_service

    source = inspect.getsource(workflow_execution_service)
    assert "confirm=None" in source
    assert "_always_allow" not in source
    assert "auto_deny_when_unconfirmable=False" not in source
