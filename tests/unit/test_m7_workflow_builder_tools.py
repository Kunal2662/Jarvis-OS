"""Workflow Builder agent tool tests -- M7 (standalone workflow authoring).

Real ``WorkflowBuilderService`` over real (temp-file) SQLite and a real
``PermissionModel``, matching ``test_m7_home_automation_tools.py``'s
own fixtures.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("langchain_core")

from jarvis.agents.tools.workflow_builder_tools import build_workflow_builder_tools
from jarvis.core.plugins.permissions import PermissionModel
from jarvis.services.workflow_builder_service import (
    WORKFLOW_BUILDER_PRINCIPAL,
    WORKFLOW_BUILDER_SCOPE,
    WorkflowBuilderService,
)


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
def settings_obj(tmp_path: Path, monkeypatch):
    return _settings(tmp_path, monkeypatch)


@pytest.fixture
def bus():
    from jarvis.core.events.event_bus import EventBus

    return EventBus()


@pytest.fixture
def permissions(tmp_path: Path, bus):
    return PermissionModel(bus, store_path=tmp_path / "permissions.json")


@pytest.fixture
def service(db, permissions, settings_obj) -> WorkflowBuilderService:
    from jarvis.services.workflow_execution_service import WorkflowExecutionService

    workflow_executor = WorkflowExecutionService(settings=settings_obj)
    return WorkflowBuilderService(
        database=db, permissions=permissions, workflow_executor=workflow_executor
    )


@pytest.fixture
def tools(service: WorkflowBuilderService):
    return {t.name: t for t in build_workflow_builder_tools(service)}


async def _grant(permissions) -> None:
    await permissions.grant(WORKFLOW_BUILDER_PRINCIPAL, WORKFLOW_BUILDER_SCOPE)


def _steps() -> list[dict]:
    return [{"kind": "automation", "instruction": "x"}]


@pytest.mark.asyncio
async def test_registry_omits_workflow_builder_tools_when_not_wired() -> None:
    from jarvis.agents.tools.registry import build_tool_registry

    assert build_tool_registry() == []


@pytest.mark.asyncio
async def test_registry_includes_workflow_builder_tools_when_service_provided(
    service: WorkflowBuilderService,
) -> None:
    from jarvis.agents.tools.registry import build_tool_registry

    tools = build_tool_registry(workflow_builder=service)
    names = {t.name for t in tools}
    assert {
        "list_workflows",
        "get_workflow",
        "create_workflow",
        "update_workflow",
        "run_workflow",
    } <= names
    assert "delete_workflow" not in names


@pytest.mark.asyncio
async def test_list_workflows_tool_denied_without_grant(tools) -> None:
    result = await tools["list_workflows"].ainvoke({})
    assert "Couldn't" in result
    assert "permission" in result.lower()


@pytest.mark.asyncio
async def test_list_workflows_tool_reports_none_once_granted(tools, permissions) -> None:
    await _grant(permissions)
    result = await tools["list_workflows"].ainvoke({})
    assert "No workflows" in result


@pytest.mark.asyncio
async def test_create_workflow_tool_denied_without_grant(tools) -> None:
    result = await tools["create_workflow"].ainvoke({"name": "x", "steps": _steps()})
    assert "Couldn't" in result
    assert "permission" in result.lower()


@pytest.mark.asyncio
async def test_create_then_list_then_get(tools, permissions) -> None:
    await _grant(permissions)

    created = await tools["create_workflow"].ainvoke({"name": "x", "steps": _steps()})
    assert '"name": "x"' in created

    listed = await tools["list_workflows"].ainvoke({})
    assert '"x"' in listed

    import json

    workflow_id = json.loads(created)["id"]
    got = await tools["get_workflow"].ainvoke({"workflow_id": workflow_id})
    assert workflow_id in got


@pytest.mark.asyncio
async def test_update_workflow_tool_renames_without_touching_steps(tools, permissions) -> None:
    await _grant(permissions)
    import json

    created = await tools["create_workflow"].ainvoke({"name": "x", "steps": _steps()})
    workflow_id = json.loads(created)["id"]

    updated = await tools["update_workflow"].ainvoke({"workflow_id": workflow_id, "name": "y"})
    assert '"name": "y"' in updated
    assert json.loads(updated)["steps"] == json.loads(created)["steps"]


@pytest.mark.asyncio
async def test_update_workflow_tool_reports_unknown_workflow(tools, permissions) -> None:
    await _grant(permissions)
    result = await tools["update_workflow"].ainvoke({"workflow_id": "no-such-id", "name": "y"})
    assert "Couldn't update" in result


@pytest.mark.asyncio
async def test_run_workflow_tool_executes_the_workflow(tools, permissions) -> None:
    await _grant(permissions)
    import json

    created = await tools["create_workflow"].ainvoke(
        {"name": "x", "steps": [{"kind": "agent_tool", "tool_name": "no_such_tool"}]}
    )
    workflow_id = json.loads(created)["id"]

    result = await tools["run_workflow"].ainvoke({"workflow_id": workflow_id})

    assert '"source": "manual"' in result
    assert '"status": "failed"' in result


@pytest.mark.asyncio
async def test_run_workflow_tool_reports_unknown_workflow(tools, permissions) -> None:
    await _grant(permissions)
    result = await tools["run_workflow"].ainvoke({"workflow_id": "no-such-id"})
    assert "Couldn't run" in result
