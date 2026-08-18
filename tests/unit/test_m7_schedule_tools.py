"""Schedule agent tool tests -- Milestone 7 Phase 6 (Scheduler MVP).

Real ``ScheduleService`` over real (temp-file) SQLite and a real
``PermissionModel``, matching ``test_m12_sensor_tools.py``'s own
fixtures.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("langchain_core")

from jarvis.agents.tools.schedule_tools import build_schedule_tools
from jarvis.core.plugins.permissions import PermissionModel
from jarvis.services.schedule_service import SCHEDULER_PRINCIPAL, SCHEDULER_SCOPE, ScheduleService


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
def permissions(tmp_path: Path):
    from jarvis.core.events.event_bus import EventBus

    return PermissionModel(EventBus(), store_path=tmp_path / "permissions.json")


@pytest.fixture
def service(db, permissions, settings_obj) -> ScheduleService:
    return ScheduleService(database=db, permissions=permissions, settings=settings_obj)


@pytest.fixture
def tools(service: ScheduleService):
    return {t.name: t for t in build_schedule_tools(service)}


async def _grant(permissions: PermissionModel) -> None:
    await permissions.grant(SCHEDULER_PRINCIPAL, SCHEDULER_SCOPE)


# --- Registry integration ---------------------------------------------------------


def test_registry_omits_schedule_tools_when_not_wired() -> None:
    from jarvis.agents.tools import build_tool_registry

    tools = build_tool_registry()
    assert not any(t.name == "list_schedules" for t in tools)


def test_registry_includes_schedule_tools_when_service_provided(service: ScheduleService) -> None:
    from jarvis.agents.tools import build_tool_registry

    tools = build_tool_registry(schedules=service)
    names = {t.name for t in tools}
    assert {
        "list_schedules",
        "get_schedule",
        "create_schedule",
        "enable_schedule",
        "disable_schedule",
    } <= names


def test_exactly_five_tools_registered(tools) -> None:
    assert set(tools.keys()) == {
        "list_schedules",
        "get_schedule",
        "create_schedule",
        "enable_schedule",
        "disable_schedule",
    }


def test_delete_and_cancel_are_not_agent_tools(tools) -> None:
    assert "delete_schedule" not in tools
    assert "cancel_schedule" not in tools


def test_create_schedule_is_not_confirmation_gated() -> None:
    """Logic Contract §13: creating a schedule does not itself execute
    anything immediately -- future execution is independently gated."""
    from jarvis.core.config.settings import AgentSettings

    assert "create_schedule" not in AgentSettings().confirm_required_tools


# --- Permission boundary -------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_schedules_tool_denied_without_grant(tools) -> None:
    result = await tools["list_schedules"].ainvoke({})
    assert "permission" in result.lower() or "couldn't" in result.lower()


@pytest.mark.asyncio
async def test_create_schedule_tool_denied_without_grant(tools) -> None:
    result = await tools["create_schedule"].ainvoke(
        {
            "name": "x",
            "kind": "interval",
            "interval_seconds": 60.0,
            "steps": [{"kind": "automation", "instruction": "x"}],
        }
    )
    assert "couldn't create" in result.lower()


# --- Functional behavior ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_schedules_tool_reports_none_yet(tools, permissions: PermissionModel) -> None:
    await _grant(permissions)
    result = await tools["list_schedules"].ainvoke({})
    assert "no schedules" in result.lower()


@pytest.mark.asyncio
async def test_create_then_list_then_get_via_tools(tools, permissions: PermissionModel) -> None:
    await _grant(permissions)
    created_raw = await tools["create_schedule"].ainvoke(
        {
            "name": "Morning check",
            "kind": "interval",
            "interval_seconds": 300.0,
            "steps": [{"kind": "automation", "instruction": "take a screenshot"}],
        }
    )
    created = json.loads(created_raw)
    assert created["name"] == "Morning check"

    listed = await tools["list_schedules"].ainvoke({})
    assert "Morning check" in listed

    got_raw = await tools["get_schedule"].ainvoke({"schedule_id": created["id"]})
    got = json.loads(got_raw)
    assert got["id"] == created["id"]


@pytest.mark.asyncio
async def test_create_schedule_tool_reports_invalid_cron_without_raising(
    tools, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    result = await tools["create_schedule"].ainvoke(
        {
            "name": "x",
            "kind": "cron",
            "cron_expression": "not a cron",
            "steps": [{"kind": "automation", "instruction": "x"}],
        }
    )
    assert "couldn't create" in result.lower()


@pytest.mark.asyncio
async def test_enable_disable_round_trip_via_tools(tools, permissions: PermissionModel) -> None:
    await _grant(permissions)
    created = json.loads(
        await tools["create_schedule"].ainvoke(
            {
                "name": "x",
                "kind": "interval",
                "interval_seconds": 60.0,
                "steps": [{"kind": "automation", "instruction": "x"}],
            }
        )
    )
    disabled = json.loads(await tools["disable_schedule"].ainvoke({"schedule_id": created["id"]}))
    assert disabled["enabled"] is False
    enabled = json.loads(await tools["enable_schedule"].ainvoke({"schedule_id": created["id"]}))
    assert enabled["enabled"] is True


@pytest.mark.asyncio
async def test_get_schedule_tool_reports_unknown_id_without_raising(
    tools, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    result = await tools["get_schedule"].ainvoke({"schedule_id": "no-such-id"})
    assert "couldn't" in result.lower()
