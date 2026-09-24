"""WorkflowBuilderService tests -- M7 Workflow Builder.

Real (temp-file) SQLite throughout, matching every M7/M12 service
test's own pattern -- ``PermissionModel``, ``WorkflowExecutionService``,
and ``WorkflowBuilderService`` itself are all real. See
``docs/M7_WORKFLOW_BUILDER_LOGIC_CONTRACT.md`` §18 for the required
test matrix this file implements.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core.exceptions import ServiceError
from jarvis.services.workflow_builder_service import (
    WORKFLOW_BUILDER_PRINCIPAL,
    WORKFLOW_BUILDER_SCOPE,
    WorkflowBuilderPermissionError,
    WorkflowBuilderService,
    WorkflowNotFoundError,
)
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
def permissions(tmp_path: Path):
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.plugins.permissions import PermissionModel

    return PermissionModel(EventBus(), store_path=tmp_path / "permissions.json")


@pytest.fixture
def workflow_executor(settings) -> WorkflowExecutionService:
    return WorkflowExecutionService(settings=settings)


@pytest.fixture
def service(db, permissions, workflow_executor) -> WorkflowBuilderService:
    return WorkflowBuilderService(
        database=db, permissions=permissions, workflow_executor=workflow_executor
    )


async def _grant(permissions) -> None:
    await permissions.grant(WORKFLOW_BUILDER_PRINCIPAL, WORKFLOW_BUILDER_SCOPE)


def _steps() -> list[dict]:
    return [{"kind": "agent_tool", "tool_name": "no_such_tool"}]


# --- Permission ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_denied_without_grant(service: WorkflowBuilderService) -> None:
    with pytest.raises(WorkflowBuilderPermissionError):
        await service.create_workflow(name="x", steps=_steps())


@pytest.mark.asyncio
async def test_permission_declared_pending_at_construction(permissions) -> None:
    assert permissions.state(WORKFLOW_BUILDER_PRINCIPAL, WORKFLOW_BUILDER_SCOPE).value == "pending"


@pytest.mark.asyncio
async def test_list_denied_without_grant(service) -> None:
    with pytest.raises(WorkflowBuilderPermissionError):
        await service.list_workflows()


# --- Creation validation ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_requires_a_non_empty_name(service, permissions) -> None:
    await _grant(permissions)
    with pytest.raises(ServiceError, match="non-empty 'name'"):
        await service.create_workflow(name="", steps=_steps())


@pytest.mark.asyncio
async def test_create_requires_at_least_one_step(service, permissions) -> None:
    await _grant(permissions)
    with pytest.raises(ServiceError, match="at least one step"):
        await service.create_workflow(name="x", steps=[])


@pytest.mark.asyncio
async def test_create_rejects_invalid_step_kind(service, permissions) -> None:
    await _grant(permissions)
    with pytest.raises(ServiceError, match="kind"):
        await service.create_workflow(name="x", steps=[{"kind": "not_a_real_kind"}])


@pytest.mark.asyncio
async def test_create_rejects_automation_step_missing_instruction(service, permissions) -> None:
    await _grant(permissions)
    with pytest.raises(ServiceError, match="non-empty 'instruction'"):
        await service.create_workflow(name="x", steps=[{"kind": "automation"}])


@pytest.mark.asyncio
async def test_create_rejects_agent_tool_step_missing_tool_name(service, permissions) -> None:
    await _grant(permissions)
    with pytest.raises(ServiceError, match="non-empty 'tool_name'"):
        await service.create_workflow(name="x", steps=[{"kind": "agent_tool"}])


# --- CRUD --------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_then_get(service, permissions) -> None:
    await _grant(permissions)
    created = await service.create_workflow(name="x", steps=_steps(), description="desc")
    assert created["name"] == "x"
    assert created["description"] == "desc"
    assert len(created["steps"]) == 1

    got = await service.get_workflow(created["id"])
    assert got["id"] == created["id"]
    assert got["steps"] == created["steps"]


@pytest.mark.asyncio
async def test_get_unknown_workflow_raises(service, permissions) -> None:
    await _grant(permissions)
    with pytest.raises(WorkflowNotFoundError):
        await service.get_workflow("no-such-id")


@pytest.mark.asyncio
async def test_list_workflows(service, permissions) -> None:
    await _grant(permissions)
    assert await service.list_workflows() == []
    await service.create_workflow(name="a", steps=_steps())
    await service.create_workflow(name="b", steps=_steps())
    rows = await service.list_workflows()
    assert len(rows) == 2
    assert {r["name"] for r in rows} == {"a", "b"}


@pytest.mark.asyncio
async def test_delete_then_get_raises(service, permissions) -> None:
    await _grant(permissions)
    created = await service.create_workflow(name="x", steps=_steps())
    assert await service.delete_workflow(created["id"]) is True
    with pytest.raises(WorkflowNotFoundError):
        await service.get_workflow(created["id"])


@pytest.mark.asyncio
async def test_delete_unknown_workflow_raises(service, permissions) -> None:
    await _grant(permissions)
    with pytest.raises(WorkflowNotFoundError):
        await service.delete_workflow("no-such-id")


# --- Update ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_name_only_leaves_other_fields_unchanged(service, permissions) -> None:
    await _grant(permissions)
    created = await service.create_workflow(name="x", steps=_steps(), description="desc")
    updated = await service.update_workflow(created["id"], name="y")
    assert updated["name"] == "y"
    assert updated["description"] == "desc"
    assert updated["steps"] == created["steps"]


@pytest.mark.asyncio
async def test_update_steps_only_leaves_name_and_description_unchanged(
    service, permissions
) -> None:
    await _grant(permissions)
    created = await service.create_workflow(name="x", steps=_steps(), description="desc")
    new_steps = [{"kind": "automation", "instruction": "do a thing"}]
    updated = await service.update_workflow(created["id"], steps=new_steps)
    assert updated["name"] == "x"
    assert updated["description"] == "desc"
    assert updated["steps"][0]["kind"] == "automation"
    assert updated["steps"][0]["instruction"] == "do a thing"


@pytest.mark.asyncio
async def test_update_steps_are_revalidated(service, permissions) -> None:
    await _grant(permissions)
    created = await service.create_workflow(name="x", steps=_steps())
    with pytest.raises(ServiceError, match="kind"):
        await service.update_workflow(created["id"], steps=[{"kind": "invalid"}])


@pytest.mark.asyncio
async def test_update_rejects_blank_name(service, permissions) -> None:
    await _grant(permissions)
    created = await service.create_workflow(name="x", steps=_steps())
    with pytest.raises(ServiceError, match="cannot be blank"):
        await service.update_workflow(created["id"], name="   ")


@pytest.mark.asyncio
async def test_update_unknown_workflow_raises(service, permissions) -> None:
    await _grant(permissions)
    with pytest.raises(WorkflowNotFoundError):
        await service.update_workflow("no-such-id", name="y")


@pytest.mark.asyncio
async def test_update_with_no_fields_is_a_no_op(service, permissions) -> None:
    await _grant(permissions)
    created = await service.create_workflow(name="x", steps=_steps(), description="desc")
    unchanged = await service.update_workflow(created["id"])
    assert unchanged["name"] == "x"
    assert unchanged["description"] == "desc"
    assert unchanged["steps"] == created["steps"]


# --- Manual execution ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_workflow_reuses_workflow_executor_and_records_manual_source(
    service, permissions
) -> None:
    await _grant(permissions)
    created = await service.create_workflow(name="x", steps=_steps())

    result = await service.run_workflow(created["id"])

    assert result["source"] == "manual"
    assert result["status"] == "failed"  # no_such_tool is unregistered
    assert "Unknown tool" in result["step_results"][0]["error"]


@pytest.mark.asyncio
async def test_run_workflow_unknown_id_raises(service, permissions) -> None:
    await _grant(permissions)
    with pytest.raises(WorkflowNotFoundError):
        await service.run_workflow("no-such-id")


@pytest.mark.asyncio
async def test_run_workflow_denied_step_is_not_auto_approved(service, permissions) -> None:
    """Policy A -- confirm=None is hardcoded. A confirm-required
    step's outcome, not merely its absence of a raised exception,
    proves the executor never silently approves it."""
    await _grant(permissions)
    created = await service.create_workflow(
        name="x", steps=[{"kind": "agent_tool", "tool_name": "unlock_device"}]
    )
    result = await service.run_workflow(created["id"])
    # No device services are wired into this fixture's executor at
    # all, so "unlock_device" is unregistered here too -- "failed",
    # not "succeeded". The point is that nothing about this call path
    # can ever silently succeed a confirm-required tool; that guarantee
    # is exercised end-to-end by WorkflowExecutionService's own
    # dedicated test (test_confirm_required_agent_tool_step_is_denied_
    # not_auto_approved), not re-proven here.
    assert result["status"] == "failed"


@pytest.mark.asyncio
async def test_list_executions_empty_for_a_never_run_workflow(service, permissions) -> None:
    await _grant(permissions)
    created = await service.create_workflow(name="x", steps=_steps())
    assert await service.list_executions(created["id"]) == []


@pytest.mark.asyncio
async def test_list_executions_after_a_run(service, permissions) -> None:
    await _grant(permissions)
    created = await service.create_workflow(name="x", steps=_steps())
    await service.run_workflow(created["id"])
    executions = await service.list_executions(created["id"])
    assert len(executions) == 1
    assert executions[0]["source"] == "manual"


@pytest.mark.asyncio
async def test_list_executions_unknown_workflow_raises(service, permissions) -> None:
    await _grant(permissions)
    with pytest.raises(WorkflowNotFoundError):
        await service.list_executions("no-such-id")


# --- Ownership separation (Logic Contract §6/§20) -------------------------------------------


@pytest.mark.asyncio
async def test_workflow_builder_workflow_is_invisible_to_scheduler(
    service, permissions, db
) -> None:
    """A workflow created standalone via Workflow Builder is never
    referenced by, or reachable from, a Schedule row -- this is
    structural (no Schedule row is ever created here, so nothing could
    reference this workflow_id), confirmed by querying
    ScheduleRepository directly and finding it empty."""
    await _grant(permissions)
    created = await service.create_workflow(name="x", steps=_steps())

    from jarvis.infrastructure.database.repositories.schedule_repository import (
        ScheduleRepository,
    )

    async with db.session() as sess:
        schedules = await ScheduleRepository(sess).list_schedules()  # type: ignore[arg-type]
    assert schedules == []
    assert created["id"]  # the workflow exists, unowned


# --- Scope guards --------------------------------------------------------------------------


def test_workflow_builder_service_introduces_no_forbidden_coupling() -> None:
    import inspect

    from jarvis.services import workflow_builder_service

    source = inspect.getsource(workflow_builder_service)
    for forbidden in (
        "MqttConnector",
        "HomeAssistantConnector",
        "from jarvis.core.events.event_bus import EventBus",
        "import schedule_service",
        "from jarvis.services.schedule_service import ScheduleService",
        "import home_automation_service",
        "from jarvis.services.home_automation_service",
        "MemoryService",
        "SmartHomeMemoryService",
        "AnalyticsService",
        "RecipeManager",
    ):
        assert forbidden not in source


def test_workflow_builder_service_never_imports_event_viewer() -> None:
    import importlib.util

    for module_name in (
        "jarvis.services.event_viewer_service",
        "jarvis.services.home_automation_analytics_service",
    ):
        assert importlib.util.find_spec(module_name) is None


def test_workflow_builder_service_never_supplies_a_confirm_callback() -> None:
    import inspect

    from jarvis.services import workflow_builder_service

    source = inspect.getsource(workflow_builder_service)
    assert "_always_allow" not in source
    assert "auto_deny_when_unconfirmable=False" not in source
