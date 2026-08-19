"""Home Automation agent tool tests -- M7 (event-based triggers).

Real ``HomeAutomationService`` over real (temp-file) SQLite and a real
``PermissionModel``, matching ``test_m7_schedule_tools.py``'s own
fixtures.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("langchain_core")

from jarvis.agents.tools.home_automation_tools import build_home_automation_tools
from jarvis.core.plugins.permissions import PermissionModel
from jarvis.services.home_automation_service import (
    HOME_AUTOMATION_PRINCIPAL,
    HOME_AUTOMATION_SCOPE,
    HomeAutomationService,
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
def service(db, permissions, settings_obj, bus) -> HomeAutomationService:
    from jarvis.services.workflow_execution_service import WorkflowExecutionService

    workflow_executor = WorkflowExecutionService(settings=settings_obj)
    return HomeAutomationService(
        database=db,
        permissions=permissions,
        settings=settings_obj,
        event_bus=bus,
        workflow_executor=workflow_executor,
    )


@pytest.fixture
def tools(service: HomeAutomationService):
    return {t.name: t for t in build_home_automation_tools(service)}


async def _grant(permissions) -> None:
    await permissions.grant(HOME_AUTOMATION_PRINCIPAL, HOME_AUTOMATION_SCOPE)


def _steps() -> list[dict]:
    return [{"kind": "automation", "instruction": "x"}]


@pytest.mark.asyncio
async def test_registry_includes_home_automation_tools_only_when_wired() -> None:
    from jarvis.agents.tools.registry import build_tool_registry

    assert build_tool_registry() == []


@pytest.mark.asyncio
async def test_registry_includes_home_automation_tools_when_service_provided(
    service: HomeAutomationService,
) -> None:
    from jarvis.agents.tools.registry import build_tool_registry

    tools = build_tool_registry(home_automation=service)
    names = {t.name for t in tools}
    assert {
        "list_home_automations",
        "get_home_automation",
        "create_home_automation",
        "enable_home_automation",
        "disable_home_automation",
        "run_home_automation",
    } <= names
    assert "delete_home_automation" not in names


@pytest.mark.asyncio
async def test_list_home_automations_tool_denied_without_grant(tools) -> None:
    result = await tools["list_home_automations"].ainvoke({})
    assert "Couldn't" in result
    assert "permission" in result.lower()


@pytest.mark.asyncio
async def test_list_home_automations_tool_reports_none_once_granted(tools, permissions) -> None:
    await _grant(permissions)
    result = await tools["list_home_automations"].ainvoke({})
    assert "No Home Automations" in result


@pytest.mark.asyncio
async def test_create_home_automation_tool_denied_without_grant(tools) -> None:
    result = await tools["create_home_automation"].ainvoke(
        {"name": "x", "device_id": "light-1", "to_status": "paired", "steps": _steps()}
    )
    assert "Couldn't" in result
    assert "permission" in result.lower()


@pytest.mark.asyncio
async def test_create_then_list_then_get(tools, permissions) -> None:
    await _grant(permissions)

    created = await tools["create_home_automation"].ainvoke(
        {"name": "x", "device_id": "light-1", "to_status": "paired", "steps": _steps()}
    )
    assert '"device_id": "light-1"' in created

    listed = await tools["list_home_automations"].ainvoke({})
    assert "light-1" in listed

    import json

    trigger_id = json.loads(created)["id"]
    got = await tools["get_home_automation"].ainvoke({"automation_id": trigger_id})
    assert trigger_id in got


@pytest.mark.asyncio
async def test_enable_disable_round_trip(tools, permissions) -> None:
    await _grant(permissions)
    import json

    created = await tools["create_home_automation"].ainvoke(
        {"name": "x", "device_id": "light-1", "to_status": "paired", "steps": _steps()}
    )
    trigger_id = json.loads(created)["id"]

    disabled = await tools["disable_home_automation"].ainvoke({"automation_id": trigger_id})
    assert '"enabled": false' in disabled

    enabled = await tools["enable_home_automation"].ainvoke({"automation_id": trigger_id})
    assert '"enabled": true' in enabled


@pytest.mark.asyncio
async def test_run_home_automation_tool_executes_the_workflow(tools, permissions) -> None:
    await _grant(permissions)
    import json

    created = await tools["create_home_automation"].ainvoke(
        {
            "name": "x",
            "device_id": "light-1",
            "to_status": "paired",
            "steps": [{"kind": "agent_tool", "tool_name": "no_such_tool"}],
        }
    )
    trigger_id = json.loads(created)["id"]

    result = await tools["run_home_automation"].ainvoke({"automation_id": trigger_id})

    assert '"source": "manual"' in result
    assert '"status": "failed"' in result


@pytest.mark.asyncio
async def test_run_home_automation_tool_reports_unknown_automation(tools, permissions) -> None:
    await _grant(permissions)
    result = await tools["run_home_automation"].ainvoke({"automation_id": "no-such-id"})
    assert "Couldn't run" in result
