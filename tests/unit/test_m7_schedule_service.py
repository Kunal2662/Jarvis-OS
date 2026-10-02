"""ScheduleService tests -- Milestone 7 Phase 6 (Scheduler MVP).

Real (temp-file) SQLite throughout, matching every M12 service test's
own pattern -- only `FakeOSAutomation` (the OS-automation side effect
boundary) is faked; `AutomationService`, `PermissionModel`, and
`ScheduleService` itself are all real. See
``docs/M7_SCHEDULER_LOGIC_CONTRACT.md`` §21 for the required test
matrix this file implements.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from jarvis.core.exceptions import ServiceError


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
def bus():
    from jarvis.core.events.event_bus import EventBus

    return EventBus()


@pytest.fixture
def permissions(tmp_path: Path, bus):
    from jarvis.core.plugins.permissions import PermissionModel

    return PermissionModel(bus, store_path=tmp_path / "permissions.json")


@pytest.fixture
def automation(settings, db):
    from jarvis.services.automation_service import AutomationService
    from tests.fakes.fake_os_automation import FakeOSAutomation

    return AutomationService(FakeOSAutomation(), settings, database=db)


@pytest.fixture
def sensor_permissions(tmp_path: Path, bus):
    from jarvis.core.plugins.permissions import PermissionModel

    return PermissionModel(bus, store_path=tmp_path / "sensor_permissions.json")


@pytest.fixture
def sensors(db, bus, sensor_permissions):
    """A real, permission-independent `SensorService` -- used only to
    give AGENT_TOOL-kind steps a safe, non-confirm-required tool
    (`list_sensors`) to call. `SensorService`'s own permission gate is
    independent of `ScheduleService`'s -- an empty sensor list with
    zero registered sensors is itself a valid, deterministic
    "succeeded" outcome with no device setup required."""
    from jarvis.core.connectivity.registry import ConnectorFactoryRegistry
    from jarvis.services.connectivity_service import ConnectivityService
    from jarvis.services.sensor_service import SensorService
    from jarvis.services.smart_home_service import SmartHomeService

    smart_home = SmartHomeService(database=db, event_bus=bus)
    connectivity = ConnectivityService(
        registry=ConnectorFactoryRegistry(), smart_home=smart_home, event_bus=bus
    )
    return SensorService(
        smart_home=smart_home, connectivity=connectivity, permissions=sensor_permissions
    )


@pytest.fixture
async def sensors_granted(sensors, sensor_permissions):
    from jarvis.services.sensor_service import SENSOR_PRINCIPAL, SMART_HOME_SCOPE

    await sensor_permissions.grant(SENSOR_PRINCIPAL, SMART_HOME_SCOPE)
    return sensors


@pytest.fixture
def workflow_executor(settings, automation, sensors_granted):
    from jarvis.services.workflow_execution_service import WorkflowExecutionService

    return WorkflowExecutionService(
        settings=settings, automation=automation, sensors=sensors_granted
    )


@pytest.fixture
def service(db, permissions, settings, workflow_executor):
    from jarvis.services.schedule_service import ScheduleService

    return ScheduleService(
        database=db,
        permissions=permissions,
        settings=settings,
        workflow_executor=workflow_executor,
    )


async def _grant(permissions) -> None:
    from jarvis.services.schedule_service import SCHEDULER_PRINCIPAL, SCHEDULER_SCOPE

    await permissions.grant(SCHEDULER_PRINCIPAL, SCHEDULER_SCOPE)


def _automation_step(instruction: str) -> dict:
    return {"kind": "automation", "instruction": instruction}


def _agent_tool_step(tool_name: str, tool_args: dict | None = None) -> dict:
    return {"kind": "agent_tool", "tool_name": tool_name, "tool_args": tool_args or {}}


async def _force_due(db, schedule_id: str, *, seconds_ago: float = 1.0) -> None:
    from jarvis.infrastructure.database.repositories.schedule_repository import ScheduleRepository

    async with db.session() as sess:
        repo = ScheduleRepository(sess)
        row = await repo.get(schedule_id)
        row.next_fire_at = datetime.now(UTC) - timedelta(seconds=seconds_ago)
        await sess.flush()


# --- Permission enforcement -----------------------------------------------------


@pytest.mark.asyncio
async def test_create_schedule_denied_by_default(service) -> None:
    with pytest.raises(ServiceError, match="permission"):
        await service.create_schedule(
            name="x",
            kind="interval",
            interval_seconds=60.0,
            steps=[_automation_step("take a screenshot")],
        )


@pytest.mark.asyncio
async def test_list_schedules_denied_by_default(service) -> None:
    with pytest.raises(ServiceError, match="permission"):
        await service.list_schedules()


@pytest.mark.asyncio
async def test_permission_declared_pending_at_construction(permissions) -> None:
    from jarvis.services.schedule_service import SCHEDULER_PRINCIPAL, SCHEDULER_SCOPE

    assert permissions.state(SCHEDULER_PRINCIPAL, SCHEDULER_SCOPE).value == "pending"


@pytest.mark.asyncio
async def test_reads_and_writes_succeed_once_granted(service, permissions) -> None:
    await _grant(permissions)
    schedule = await service.create_schedule(
        name="x",
        kind="interval",
        interval_seconds=60.0,
        steps=[_automation_step("take a screenshot")],
    )
    rows = await service.list_schedules()
    assert len(rows) == 1
    assert rows[0]["id"] == schedule["id"]


# --- Creation validation ---------------------------------------------------------


@pytest.mark.asyncio
async def test_create_schedule_rejects_empty_name(service, permissions) -> None:
    await _grant(permissions)
    with pytest.raises(ServiceError, match="name"):
        await service.create_schedule(
            name="  ", kind="interval", interval_seconds=60.0, steps=[_automation_step("x")]
        )


@pytest.mark.asyncio
async def test_create_schedule_rejects_empty_steps(service, permissions) -> None:
    await _grant(permissions)
    with pytest.raises(ServiceError, match="step"):
        await service.create_schedule(name="x", kind="interval", interval_seconds=60.0, steps=[])


@pytest.mark.asyncio
async def test_create_schedule_rejects_interval_below_minimum(service, permissions) -> None:
    await _grant(permissions)
    with pytest.raises(ServiceError, match="at least 60"):
        await service.create_schedule(
            name="x", kind="interval", interval_seconds=30.0, steps=[_automation_step("x")]
        )


@pytest.mark.asyncio
async def test_create_schedule_rejects_invalid_cron(service, permissions) -> None:
    await _grant(permissions)
    with pytest.raises(ServiceError, match="cron"):
        await service.create_schedule(
            name="x", kind="cron", cron_expression="not a cron", steps=[_automation_step("x")]
        )


@pytest.mark.asyncio
async def test_create_schedule_rejects_unknown_timezone(service, permissions) -> None:
    await _grant(permissions)
    with pytest.raises(ServiceError, match=r"[Tt]imezone"):
        await service.create_schedule(
            name="x",
            kind="interval",
            interval_seconds=60.0,
            timezone="Not/AZone",
            steps=[_automation_step("x")],
        )


@pytest.mark.asyncio
async def test_create_schedule_rejects_unknown_kind(service, permissions) -> None:
    await _grant(permissions)
    with pytest.raises(ServiceError, match="kind"):
        await service.create_schedule(
            name="x", kind="daily", interval_seconds=60.0, steps=[_automation_step("x")]
        )


@pytest.mark.asyncio
async def test_create_schedule_rejects_malformed_step(service, permissions) -> None:
    await _grant(permissions)
    with pytest.raises(ServiceError, match="kind"):
        await service.create_schedule(
            name="x", kind="interval", interval_seconds=60.0, steps=[{"kind": "not_a_kind"}]
        )


@pytest.mark.asyncio
async def test_create_schedule_rejects_automation_step_without_instruction(
    service, permissions
) -> None:
    await _grant(permissions)
    with pytest.raises(ServiceError, match="instruction"):
        await service.create_schedule(
            name="x", kind="interval", interval_seconds=60.0, steps=[{"kind": "automation"}]
        )


@pytest.mark.asyncio
async def test_create_schedule_rejects_agent_tool_step_without_tool_name(
    service, permissions
) -> None:
    await _grant(permissions)
    with pytest.raises(ServiceError, match="tool_name"):
        await service.create_schedule(
            name="x", kind="interval", interval_seconds=60.0, steps=[{"kind": "agent_tool"}]
        )


@pytest.mark.asyncio
async def test_create_schedule_default_timezone_is_utc(service, permissions) -> None:
    await _grant(permissions)
    schedule = await service.create_schedule(
        name="x", kind="interval", interval_seconds=60.0, steps=[_automation_step("x")]
    )
    assert schedule["timezone"] == "UTC"


@pytest.mark.asyncio
async def test_create_schedule_first_fire_is_after_creation_not_immediate(
    service, permissions
) -> None:
    await _grant(permissions)
    schedule = await service.create_schedule(
        name="x", kind="interval", interval_seconds=300.0, steps=[_automation_step("x")]
    )
    created = datetime.fromisoformat(schedule["created_at"])
    next_fire = datetime.fromisoformat(schedule["next_fire_at"])
    assert next_fire > created


@pytest.mark.asyncio
async def test_create_schedule_flags_confirm_required_agent_tool_step(service, permissions) -> None:
    """Best-effort, non-blocking scan (Logic Contract §2) -- accurate
    for AGENT_TOOL steps against `AgentSettings.confirm_required_tools`."""
    await _grant(permissions)
    schedule = await service.create_schedule(
        name="x",
        kind="interval",
        interval_seconds=60.0,
        steps=[_agent_tool_step("run_automation", {"instruction": "shutdown"})],
    )
    assert schedule["contains_confirm_required_steps"] is True


@pytest.mark.asyncio
async def test_create_schedule_does_not_flag_safe_agent_tool_step(service, permissions) -> None:
    await _grant(permissions)
    schedule = await service.create_schedule(
        name="x", kind="interval", interval_seconds=60.0, steps=[_agent_tool_step("list_schedules")]
    )
    assert schedule["contains_confirm_required_steps"] is False


# --- Lifecycle: enable/disable/delete --------------------------------------------


@pytest.mark.asyncio
async def test_enable_disable_round_trip(service, permissions) -> None:
    await _grant(permissions)
    schedule = await service.create_schedule(
        name="x", kind="interval", interval_seconds=60.0, steps=[_automation_step("x")]
    )
    disabled = await service.disable_schedule(schedule["id"])
    assert disabled["enabled"] is False
    enabled = await service.enable_schedule(schedule["id"])
    assert enabled["enabled"] is True


@pytest.mark.asyncio
async def test_enable_unknown_schedule_is_404_shaped(service, permissions) -> None:
    from jarvis.services.schedule_service import ScheduleNotFoundError

    await _grant(permissions)
    with pytest.raises(ScheduleNotFoundError):
        await service.enable_schedule("no-such-schedule")


@pytest.mark.asyncio
async def test_delete_schedule_removes_it_and_its_workflow(service, permissions, db) -> None:
    from jarvis.infrastructure.database.repositories.schedule_repository import WorkflowRepository

    await _grant(permissions)
    schedule = await service.create_schedule(
        name="x", kind="interval", interval_seconds=60.0, steps=[_automation_step("x")]
    )
    workflow_id = schedule["workflow_id"]

    deleted = await service.delete_schedule(schedule["id"])
    assert deleted is True

    rows = await service.list_schedules()
    assert rows == []
    async with db.session() as sess:
        assert await WorkflowRepository(sess).get(workflow_id) is None


@pytest.mark.asyncio
async def test_get_schedule_includes_latest_execution_after_a_fire(
    service, permissions, db
) -> None:
    await _grant(permissions)
    schedule = await service.create_schedule(
        name="x",
        kind="interval",
        interval_seconds=60.0,
        steps=[_automation_step("take a screenshot")],
    )
    await _force_due(db, schedule["id"])
    await service.tick()

    got = await service.get_schedule(schedule["id"])
    assert "last_execution" in got
    assert got["last_execution"]["status"] == "succeeded"


# --- Execution: outcomes -----------------------------------------------------------


@pytest.mark.asyncio
async def test_automation_step_succeeds(service, permissions, db, tmp_path: Path) -> None:
    await _grant(permissions)
    target = tmp_path / "ScheduledFolder"
    schedule = await service.create_schedule(
        name="x",
        kind="interval",
        interval_seconds=60.0,
        steps=[_automation_step(f"create folder named {target}")],
    )
    await _force_due(db, schedule["id"])
    await service.tick()

    executions = await service.list_executions(schedule["id"])
    assert len(executions) == 1
    assert executions[0]["status"] == "succeeded"
    assert target.is_dir()


@pytest.mark.asyncio
async def test_agent_tool_step_succeeds(service, permissions, db) -> None:
    await _grant(permissions)
    schedule = await service.create_schedule(
        name="x", kind="interval", interval_seconds=60.0, steps=[_agent_tool_step("list_sensors")]
    )
    await _force_due(db, schedule["id"])
    await service.tick()

    executions = await service.list_executions(schedule["id"])
    assert executions[0]["status"] == "succeeded"


@pytest.mark.asyncio
async def test_unknown_agent_tool_fails(service, permissions, db) -> None:
    await _grant(permissions)
    schedule = await service.create_schedule(
        name="x",
        kind="interval",
        interval_seconds=60.0,
        steps=[_agent_tool_step("not_a_real_tool")],
    )
    await _force_due(db, schedule["id"])
    await service.tick()

    executions = await service.list_executions(schedule["id"])
    assert executions[0]["status"] == "failed"
    assert "Unknown tool" in executions[0]["step_results"][0]["error"]


@pytest.mark.asyncio
async def test_confirm_required_agent_tool_step_is_denied_not_auto_approved(
    service, permissions, db
) -> None:
    """The single most important execution test in this file (Logic
    Contract §2, Policy A): a scheduled, unattended confirm-required
    step is denied, never silently approved."""
    await _grant(permissions)
    schedule = await service.create_schedule(
        name="x",
        kind="interval",
        interval_seconds=60.0,
        steps=[_agent_tool_step("run_automation", {"instruction": "shutdown the computer"})],
    )
    await _force_due(db, schedule["id"])
    await service.tick()

    executions = await service.list_executions(schedule["id"])
    assert executions[0]["status"] == "denied"

    # The schedule remains enabled after a denied execution (Logic
    # Contract §2) -- a denial is policy-correct, not a broken schedule.
    got = await service.get_schedule(schedule["id"])
    assert got["enabled"] is True


# --- Device command events (M7 EventBus Tier 1) -----------------------------
# See docs/M7_EVENTBUS_DEVICE_COMMAND_EVENTS_LOGIC_CONTRACT.md §14: a
# scheduled command converges on the identical ConnectivityService.
# send_command() chokepoint any other caller does -- no Scheduler-specific
# event path exists or is added here.


@pytest.mark.asyncio
async def test_confirm_required_agent_tool_step_publishes_no_device_command_event(
    service, permissions, db, bus
) -> None:
    """The denied ``run_automation`` step (Policy A) never invokes its
    underlying tool at all, so -- regardless of which service that tool
    would have called -- zero command-executed events can result."""
    from jarvis.core.events.events import DeviceCommandExecutedEvent

    seen: list[DeviceCommandExecutedEvent] = []
    bus.subscribe(DeviceCommandExecutedEvent, seen.append)
    await _grant(permissions)
    schedule = await service.create_schedule(
        name="x",
        kind="interval",
        interval_seconds=60.0,
        steps=[_agent_tool_step("run_automation", {"instruction": "shutdown the computer"})],
    )
    await _force_due(db, schedule["id"])
    await service.tick()

    executions = await service.list_executions(schedule["id"])
    assert executions[0]["status"] == "denied"
    assert seen == []


@pytest.mark.asyncio
async def test_scheduled_agent_tool_step_success_publishes_device_command_executed_event(
    db, bus, permissions, *, settings, automation, sensors_granted, tmp_path
) -> None:
    """A scheduled, non-confirm-required device-command step (Smart
    Lighting's own ``set_light_state``, not in
    ``AgentSettings.confirm_required_tools``) reaches
    ``ConnectivityService.send_command()`` exactly as a REST- or
    agent-tool-originated call does, and produces the identical event --
    with no schedule identifier or scheduler-specific metadata attached,
    per the Logic Contract's explicit boundary."""
    from jarvis.core.connectivity.registry import ConnectorFactoryRegistry
    from jarvis.core.events.events import DeviceCommandExecutedEvent
    from jarvis.core.plugins.permissions import PermissionModel
    from jarvis.services.connectivity_service import ConnectivityService
    from jarvis.services.schedule_service import ScheduleService
    from jarvis.services.smart_home_service import SmartHomeService
    from jarvis.services.smart_lighting_service import (
        SMART_HOME_SCOPE,
        SMART_LIGHTING_PRINCIPAL,
        SmartLightingService,
    )
    from tests.fakes.fake_device_connector import FakeDeviceConnector

    seen: list[DeviceCommandExecutedEvent] = []
    bus.subscribe(DeviceCommandExecutedEvent, seen.append)

    fake_connector = FakeDeviceConnector()
    registry = ConnectorFactoryRegistry()
    registry.register("home_assistant", lambda config: fake_connector)
    smart_home = SmartHomeService(database=db, event_bus=bus)
    connectivity = ConnectivityService(registry=registry, smart_home=smart_home, event_bus=bus)
    lighting_permissions = PermissionModel(bus, store_path=tmp_path / "lighting_permissions.json")
    lighting = SmartLightingService(
        database=db,
        smart_home=smart_home,
        connectivity=connectivity,
        permissions=lighting_permissions,
    )
    await lighting_permissions.grant(SMART_LIGHTING_PRINCIPAL, SMART_HOME_SCOPE)
    await connectivity.connect("home_assistant")
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Lamp",
        device_type="light",
        external_id="light.lamp",
        metadata={"connector_type": "home_assistant"},
    )

    from jarvis.services.workflow_execution_service import WorkflowExecutionService

    workflow_executor = WorkflowExecutionService(
        settings=settings, automation=automation, sensors=sensors_granted, smart_lighting=lighting
    )
    service = ScheduleService(
        database=db,
        permissions=permissions,
        settings=settings,
        workflow_executor=workflow_executor,
    )
    await _grant(permissions)
    schedule = await service.create_schedule(
        name="x",
        kind="interval",
        interval_seconds=60.0,
        steps=[_agent_tool_step("set_light_state", {"device_id": device.id, "on": True})],
    )
    await _force_due(db, schedule["id"])
    await service.tick()

    executions = await service.list_executions(schedule["id"])
    assert executions[0]["status"] == "succeeded"
    assert len(seen) == 1
    assert seen[0].device_id == device.id
    assert seen[0].command == "turn_on"
    assert seen[0].success is True


@pytest.mark.asyncio
async def test_confirm_required_automation_step_is_denied(service, permissions, db) -> None:
    """The identical Policy A guarantee, exercised through the OTHER
    step kind (AUTOMATION, via AutomationService's own PermissionGate,
    not AgentPermissionGate) -- confirms the fail-safe default holds
    for both execution paths, not just one."""
    await _grant(permissions)
    schedule = await service.create_schedule(
        name="x",
        kind="interval",
        interval_seconds=60.0,
        steps=[_automation_step("shutdown the computer")],
    )
    await _force_due(db, schedule["id"])
    await service.tick()

    executions = await service.list_executions(schedule["id"])
    assert executions[0]["status"] == "denied"


@pytest.mark.asyncio
async def test_mixed_success_and_failure_is_partially_failed(service, permissions, db) -> None:
    await _grant(permissions)
    schedule = await service.create_schedule(
        name="x",
        kind="interval",
        interval_seconds=60.0,
        steps=[_agent_tool_step("list_sensors"), _agent_tool_step("not_a_real_tool")],
    )
    await _force_due(db, schedule["id"])
    await service.tick()

    executions = await service.list_executions(schedule["id"])
    assert executions[0]["status"] == "partially_failed"
    assert len(executions[0]["step_results"]) == 2


@pytest.mark.asyncio
async def test_all_steps_denied_is_denied_not_partially_failed(service, permissions, db) -> None:
    await _grant(permissions)
    schedule = await service.create_schedule(
        name="x",
        kind="interval",
        interval_seconds=60.0,
        steps=[
            _agent_tool_step("run_automation", {"instruction": "shutdown"}),
            _agent_tool_step("run_automation", {"instruction": "restart"}),
        ],
    )
    await _force_due(db, schedule["id"])
    await service.tick()

    executions = await service.list_executions(schedule["id"])
    assert executions[0]["status"] == "denied"


@pytest.mark.asyncio
async def test_no_automation_service_available_fails_gracefully(permissions, db, settings) -> None:
    from jarvis.services.schedule_service import ScheduleService
    from jarvis.services.workflow_execution_service import WorkflowExecutionService

    workflow_executor = WorkflowExecutionService(settings=settings)  # no automation=
    svc = ScheduleService(
        database=db, permissions=permissions, settings=settings, workflow_executor=workflow_executor
    )
    await _grant(permissions)
    schedule = await svc.create_schedule(
        name="x",
        kind="interval",
        interval_seconds=60.0,
        steps=[_automation_step("take a screenshot")],
    )
    await _force_due(db, schedule["id"])
    await svc.tick()

    executions = await svc.list_executions(schedule["id"])
    assert executions[0]["status"] == "failed"
    assert "not available" in (executions[0]["error"] or "").lower() or "Automation" in "".join(
        r["error"] or "" for r in executions[0]["step_results"]
    )


# --- Concurrency / duplicate-fire prevention --------------------------------------


@pytest.mark.asyncio
async def test_next_fire_is_advanced_after_a_normal_fire(service, permissions, db) -> None:
    await _grant(permissions)
    schedule = await service.create_schedule(
        name="x",
        kind="interval",
        interval_seconds=60.0,
        steps=[_automation_step("take a screenshot")],
    )
    before = schedule["next_fire_at"]
    await _force_due(db, schedule["id"])
    await service.tick()

    got = await service.get_schedule(schedule["id"])
    assert got["next_fire_at"] != before
    assert got["last_fired_at"] is not None


@pytest.mark.asyncio
async def test_second_tick_while_still_running_does_not_double_fire(
    service, permissions, db
) -> None:
    """Duplicate-fire prevention (Logic Contract §10): a schedule with
    a still-non-terminal execution is skipped, not re-dispatched, on a
    second tick."""
    from jarvis.infrastructure.database.repositories.schedule_repository import (
        ScheduleRepository,
        WorkflowExecutionRepository,
    )

    await _grant(permissions)
    schedule = await service.create_schedule(
        name="x",
        kind="interval",
        interval_seconds=60.0,
        steps=[_automation_step("take a screenshot")],
    )
    await _force_due(db, schedule["id"])

    # Simulate "still running" by inserting a non-terminal execution
    # directly, then ticking -- the dispatch must be skipped, not
    # produce a second execution row.
    async with db.session() as sess:
        await WorkflowExecutionRepository(sess).add(
            schedule_id=schedule["id"], workflow_id=schedule["workflow_id"], status="running"
        )

    await service.tick()

    executions = await service.list_executions(schedule["id"])
    assert len(executions) == 1  # only the pre-inserted running one
    async with db.session() as sess:
        row = await ScheduleRepository(sess).get(schedule["id"])
        assert row.last_fired_at is None  # never actually fired


@pytest.mark.asyncio
async def test_disabled_schedule_is_never_dispatched(service, permissions, db) -> None:
    await _grant(permissions)
    schedule = await service.create_schedule(
        name="x",
        kind="interval",
        interval_seconds=60.0,
        steps=[_automation_step("take a screenshot")],
    )
    await service.disable_schedule(schedule["id"])
    await _force_due(db, schedule["id"])
    await service.tick()

    executions = await service.list_executions(schedule["id"])
    assert executions == []


# --- Misfire policy ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_misfire_within_grace_period_fires_once(service, permissions, db) -> None:
    await _grant(permissions)
    schedule = await service.create_schedule(
        name="x",
        kind="interval",
        interval_seconds=60.0,
        steps=[_automation_step("take a screenshot")],
    )
    # 200s overdue, well within the 300s default grace period.
    await _force_due(db, schedule["id"], seconds_ago=200.0)
    await service.tick()

    executions = await service.list_executions(schedule["id"])
    assert len(executions) == 1
    assert executions[0]["status"] == "succeeded"


@pytest.mark.asyncio
async def test_misfire_beyond_grace_period_is_skipped_not_caught_up(
    service, permissions, db
) -> None:
    await _grant(permissions)
    schedule = await service.create_schedule(
        name="x",
        kind="interval",
        interval_seconds=60.0,
        steps=[_automation_step("take a screenshot")],
    )
    # 3600s (1 hour) overdue -- well beyond the 300s default grace period.
    await _force_due(db, schedule["id"], seconds_ago=3600.0)
    await service.tick()

    executions = await service.list_executions(schedule["id"])
    assert len(executions) == 1
    assert executions[0]["status"] == "skipped"
    assert "Misfire" in (executions[0]["error"] or "")

    # `last_fired_at` is untouched -- a skip never counts as a real fire.
    got = await service.get_schedule(schedule["id"])
    assert got["last_fired_at"] is None


@pytest.mark.asyncio
async def test_misfire_beyond_grace_resumes_from_now_not_a_catch_up_burst(
    service, permissions, db
) -> None:
    """A single long outage produces exactly one skip record, never one
    per missed period (Logic Contract §9)."""
    await _grant(permissions)
    schedule = await service.create_schedule(
        name="x",
        kind="interval",
        interval_seconds=60.0,
        steps=[_automation_step("take a screenshot")],
    )
    # A full week overdue on a 60s-interval schedule -- if this
    # produced one skip per missed period, it would be ~10,080 rows.
    await _force_due(db, schedule["id"], seconds_ago=604_800.0)
    await service.tick()

    executions = await service.list_executions(schedule["id"])
    assert len(executions) == 1
    assert executions[0]["status"] == "skipped"

    got = await service.get_schedule(schedule["id"])
    next_fire = datetime.fromisoformat(got["next_fire_at"])
    assert next_fire > datetime.now(UTC) - timedelta(seconds=5)


# --- Restart recovery ----------------------------------------------------------


@pytest.mark.asyncio
async def test_schedule_survives_a_fresh_service_instance(
    db, permissions, settings, automation
) -> None:
    """No in-memory-only state -- a brand new ScheduleService instance
    against the same database (simulating a process restart) sees the
    same schedule and correctly fires it."""
    from jarvis.services.schedule_service import ScheduleService
    from jarvis.services.workflow_execution_service import WorkflowExecutionService

    workflow_executor = WorkflowExecutionService(settings=settings, automation=automation)
    first = ScheduleService(
        database=db, permissions=permissions, settings=settings, workflow_executor=workflow_executor
    )
    await _grant(permissions)
    schedule = await first.create_schedule(
        name="x",
        kind="interval",
        interval_seconds=60.0,
        steps=[_automation_step("take a screenshot")],
    )
    await _force_due(db, schedule["id"])

    second = ScheduleService(
        database=db, permissions=permissions, settings=settings, workflow_executor=workflow_executor
    )
    await second.tick()

    executions = await second.list_executions(schedule["id"])
    assert len(executions) == 1
    assert executions[0]["status"] == "succeeded"


@pytest.mark.asyncio
async def test_disabled_schedule_remains_disabled_after_fresh_instance(
    db, permissions, settings, automation
) -> None:
    from jarvis.services.schedule_service import ScheduleService
    from jarvis.services.workflow_execution_service import WorkflowExecutionService

    workflow_executor = WorkflowExecutionService(settings=settings, automation=automation)
    first = ScheduleService(
        database=db, permissions=permissions, settings=settings, workflow_executor=workflow_executor
    )
    await _grant(permissions)
    schedule = await first.create_schedule(
        name="x", kind="interval", interval_seconds=60.0, steps=[_automation_step("x")]
    )
    await first.disable_schedule(schedule["id"])

    second = ScheduleService(
        database=db, permissions=permissions, settings=settings, workflow_executor=workflow_executor
    )
    got = await second.get_schedule(schedule["id"])
    assert got["enabled"] is False


# --- Cross-cutting scope guards ------------------------------------------------------


def test_schedule_service_module_never_subscribes_to_the_event_bus() -> None:
    """Time-based triggers only (Logic Contract §3) -- no EventBus
    subscription of any kind, confirmed by scanning the raw source."""
    import inspect

    from jarvis.services import schedule_service

    source = inspect.getsource(schedule_service)
    assert "event_bus.subscribe" not in source
    assert ".subscribe(" not in source


def test_schedule_service_never_imports_connector_or_device_state_types() -> None:
    """No device-event/connector coupling -- Scheduler is a pure
    time-based caller of existing execution infrastructure."""
    import inspect

    from jarvis.services import schedule_service

    source = inspect.getsource(schedule_service)
    for forbidden in (
        "ConnectivityService",
        "DeviceState",
        "MqttConnector",
        "HomeAssistantConnector",
    ):
        assert forbidden not in source


def test_schedule_service_never_supplies_a_confirm_callback() -> None:
    """Policy A (Logic Contract §2): no automatic confirmation
    mechanism exists anywhere in this module or the shared
    `WorkflowExecutionService` it delegates to (Home Automation Logic
    Contract §8 -- the `confirm=None` call sites moved there, verbatim,
    during the workflow-execution extraction) -- every authorize()/
    run_command() call site passes no `confirm`, verified directly
    against the raw source rather than only by behavioral test."""
    import inspect

    from jarvis.services import schedule_service, workflow_execution_service

    schedule_source = inspect.getsource(schedule_service)
    executor_source = inspect.getsource(workflow_execution_service)
    assert "confirm=None" in executor_source  # the only form `confirm` ever takes here
    for source in (schedule_source, executor_source):
        assert "_always_allow" not in source
        assert "auto_deny_when_unconfirmable=False" not in source
