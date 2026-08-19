"""Recorder agent tool tests -- M7 Recorder.

Real ``RecorderService`` over real (temp-file) SQLite and a real
``PermissionModel``, matching ``test_m7_workflow_builder_tools.py``'s
own fixtures.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("langchain_core")

from jarvis.agents.tools.recorder_tools import build_recorder_tools
from jarvis.core.plugins.permissions import PermissionModel
from jarvis.services.recorder_service import RECORDER_PRINCIPAL, RECORDER_SCOPE, RecorderService
from jarvis.services.workflow_builder_service import (
    WORKFLOW_BUILDER_PRINCIPAL,
    WORKFLOW_BUILDER_SCOPE,
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
def automation(settings_obj, db):
    from jarvis.services.automation_service import AutomationService
    from tests.fakes.fake_os_automation import FakeOSAutomation

    return AutomationService(FakeOSAutomation(), settings_obj, database=db)


@pytest.fixture
def history(db):
    from jarvis.features.automation.history import HistoryService

    return HistoryService(db)


@pytest.fixture
def workflow_builder(db, permissions, settings_obj, automation):
    from jarvis.services.workflow_builder_service import WorkflowBuilderService
    from jarvis.services.workflow_execution_service import WorkflowExecutionService

    workflow_executor = WorkflowExecutionService(settings=settings_obj, automation=automation)
    return WorkflowBuilderService(
        database=db, permissions=permissions, workflow_executor=workflow_executor
    )


@pytest.fixture
def service(db, permissions, history, workflow_builder) -> RecorderService:
    return RecorderService(
        database=db, permissions=permissions, history=history, workflow_builder=workflow_builder
    )


@pytest.fixture
def tools(service: RecorderService):
    return {t.name: t for t in build_recorder_tools(service)}


async def _grant_both(permissions: PermissionModel) -> None:
    await permissions.grant(RECORDER_PRINCIPAL, RECORDER_SCOPE)
    await permissions.grant(WORKFLOW_BUILDER_PRINCIPAL, WORKFLOW_BUILDER_SCOPE)


@pytest.mark.asyncio
async def test_registry_omits_recorder_tools_when_not_wired() -> None:
    from jarvis.agents.tools.registry import build_tool_registry

    assert build_tool_registry() == []


@pytest.mark.asyncio
async def test_registry_includes_recorder_tools_when_service_provided(
    service: RecorderService,
) -> None:
    from jarvis.agents.tools.registry import build_tool_registry

    tools = build_tool_registry(recorder=service)
    names = {t.name for t in tools}
    assert {
        "start_recording",
        "stop_recording",
        "cancel_recording",
        "list_recordings",
    } <= names


@pytest.mark.asyncio
async def test_start_recording_tool_denied_without_grant(tools) -> None:
    result = await tools["start_recording"].ainvoke({})
    assert "Couldn't" in result
    assert "permission" in result.lower()


@pytest.mark.asyncio
async def test_list_recordings_tool_reports_none_once_granted(tools, permissions) -> None:
    await _grant_both(permissions)
    result = await tools["list_recordings"].ainvoke({})
    assert "No recordings" in result


@pytest.mark.asyncio
async def test_start_then_list(tools, permissions) -> None:
    await _grant_both(permissions)
    started = await tools["start_recording"].ainvoke({})
    assert '"status": "recording"' in started

    listed = await tools["list_recordings"].ainvoke({})
    assert "recording" in listed


@pytest.mark.asyncio
async def test_cancel_recording_tool(tools, permissions) -> None:
    await _grant_both(permissions)
    import json

    started = json.loads(await tools["start_recording"].ainvoke({}))
    cancelled = await tools["cancel_recording"].ainvoke({"session_id": started["id"]})
    assert '"status": "cancelled"' in cancelled


@pytest.mark.asyncio
async def test_stop_recording_tool_with_nothing_captured_reports_failure(
    tools, permissions
) -> None:
    await _grant_both(permissions)
    import json

    started = json.loads(await tools["start_recording"].ainvoke({}))
    result = await tools["stop_recording"].ainvoke({"session_id": started["id"], "name": "x"})
    assert "Couldn't stop" in result


@pytest.mark.asyncio
async def test_stop_recording_tool_reports_unknown_session(tools, permissions) -> None:
    await _grant_both(permissions)
    result = await tools["stop_recording"].ainvoke({"session_id": "no-such-id", "name": "x"})
    assert "Couldn't stop" in result


@pytest.mark.asyncio
async def test_stop_recording_tool_creates_a_workflow(tools, permissions, automation) -> None:
    await _grant_both(permissions)
    import json

    started = json.loads(await tools["start_recording"].ainvoke({}))
    result = await automation.run_command("take a screenshot")
    assert result.succeeded

    stopped = await tools["stop_recording"].ainvoke({"session_id": started["id"], "name": "x"})
    assert '"status": "completed"' in stopped
    assert '"name": "x"' in stopped
