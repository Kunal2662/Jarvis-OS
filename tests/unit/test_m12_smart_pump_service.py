"""SmartPumpService tests -- Milestone 12 Smart Pumps (Switch-Backed
Device Slice).

Real (temp-file) SQLite ``SmartHomeService``, a real ``PermissionModel``
and a real ``SmartSwitchService`` underneath throughout, matching
``test_m12_smart_switch_service.py``'s own pattern -- only the connector
itself is faked (``FakeDeviceConnector``). The final section reuses
M7's own scheduler fixtures shape (``ScheduleService`` +
``WorkflowExecutionService`` over the same temp-file SQLite) to prove a
scheduled workflow executes a switch-backed pump through the existing
``switch_on`` AGENT_TOOL path -- no pump-specific scheduling machinery
exists or was added.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from jarvis.core.connectivity.registry import ConnectorFactoryRegistry
from jarvis.core.events.event_bus import EventBus
from jarvis.core.exceptions import ServiceError
from jarvis.core.interfaces.connectivity import DeviceState
from jarvis.core.plugins.permissions import PermissionModel
from jarvis.services.connectivity_service import ConnectivityService
from jarvis.services.smart_home_service import SmartHomeService
from jarvis.services.smart_pump_service import SmartPumpService
from jarvis.services.smart_switch_service import (
    SMART_HOME_SCOPE,
    SMART_SWITCH_PRINCIPAL,
    SmartSwitchService,
)
from tests.fakes.fake_device_connector import FakeDeviceConnector


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
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def smart_home(db, bus: EventBus) -> SmartHomeService:
    return SmartHomeService(database=db, event_bus=bus)


@pytest.fixture
def fake_connector() -> FakeDeviceConnector:
    return FakeDeviceConnector()


@pytest.fixture
def registry(fake_connector: FakeDeviceConnector) -> ConnectorFactoryRegistry:
    reg = ConnectorFactoryRegistry()
    reg.register("home_assistant", lambda config: fake_connector)
    return reg


@pytest.fixture
def connectivity(
    registry: ConnectorFactoryRegistry, smart_home: SmartHomeService, bus: EventBus
) -> ConnectivityService:
    return ConnectivityService(registry=registry, smart_home=smart_home, event_bus=bus)


@pytest.fixture
def permissions(tmp_path: Path, bus: EventBus) -> PermissionModel:
    return PermissionModel(bus, store_path=tmp_path / "permissions.json")


@pytest.fixture
def switch_service(
    smart_home: SmartHomeService, connectivity: ConnectivityService, permissions: PermissionModel
) -> SmartSwitchService:
    return SmartSwitchService(
        smart_home=smart_home, connectivity=connectivity, permissions=permissions
    )


@pytest.fixture
def service(switch_service: SmartSwitchService, smart_home: SmartHomeService) -> SmartPumpService:
    """Pure composition over the switch service -- the same instance the
    REST route and the agent tools resolve through the container."""
    return SmartPumpService(switches=switch_service, smart_home=smart_home)


async def _grant(permissions: PermissionModel) -> None:
    """The pump service declares no principal of its own -- the switch
    service's existing grant is the one and only grant it needs."""
    await permissions.grant(SMART_SWITCH_PRINCIPAL, SMART_HOME_SCOPE)


async def _home_and_pump(smart_home: SmartHomeService, connector_type: str = "home_assistant"):
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Water Pump",
        device_type="switch",
        external_id="switch.water_pump",
        metadata={"connector_type": connector_type},
    )
    return home, device


# --- Permission enforcement (inherited, never re-declared) ---------------------


@pytest.mark.asyncio
async def test_turn_on_denied_by_default(
    service: SmartPumpService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_pump(smart_home)
    with pytest.raises(ServiceError, match="permission"):
        await service.turn_on(device.id)


@pytest.mark.asyncio
async def test_turn_off_denied_by_default(
    service: SmartPumpService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_pump(smart_home)
    with pytest.raises(ServiceError, match="permission"):
        await service.turn_off(device.id)


@pytest.mark.asyncio
async def test_reads_do_not_require_permission(
    service: SmartPumpService, smart_home: SmartHomeService
) -> None:
    """Inherited switch read precedent -- a pump's on/off state carries
    no comparable privacy weight to sensor data."""
    _, device = await _home_and_pump(smart_home)
    # No grant() call anywhere in this test -- reads must still work.
    state = await service.get_state(device.id)
    assert state["id"] == device.id


@pytest.mark.asyncio
async def test_mutations_inherit_the_switch_grant_with_no_pump_principal(
    service: SmartPumpService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    """Granting only ``core:smart_switch`` is sufficient -- proves no
    second (pump-specific) principal is required anywhere in the path."""
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_pump(smart_home)

    result = await service.turn_on(device.id)

    assert result["success"] is True
    # No pump principal was ever declared or granted in this test.
    assert permissions.state("core:smart_pump", SMART_HOME_SCOPE).value == "pending"


# --- Validation / pump identity -------------------------------------------------


@pytest.mark.asyncio
async def test_turn_on_rejects_non_switch_device(
    service: SmartPumpService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    lock = await smart_home.register_discovered_device(
        home.id, "Front Door", device_type="lock", external_id="lock.front_door"
    )
    with pytest.raises(ServiceError, match="not a pump"):
        await service.turn_on(lock.id)


@pytest.mark.asyncio
async def test_get_state_rejects_non_switch_device(
    service: SmartPumpService, smart_home: SmartHomeService
) -> None:
    home = await smart_home.create_home("Primary Residence")
    light = await smart_home.register_discovered_device(
        home.id, "Ceiling Light", device_type="light", external_id="light.ceiling"
    )
    with pytest.raises(ServiceError, match="not a pump"):
        await service.get_state(light.id)


@pytest.mark.asyncio
async def test_get_state_unknown_device_raises(service: SmartPumpService) -> None:
    with pytest.raises(ServiceError):
        await service.get_state("no-such-device")


@pytest.mark.asyncio
async def test_turn_on_rejects_device_with_no_connector(
    service: SmartPumpService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    """Delegated validation -- the pump service never reaches a
    connector itself, so the switch service's own errors propagate."""
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id, "Orphan Pump", device_type="switch"
    )
    with pytest.raises(ServiceError, match="no recorded connector"):
        await service.turn_on(device.id)


@pytest.mark.asyncio
async def test_turn_on_rejects_unsupported_connector_type(
    service: SmartPumpService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    _, device = await _home_and_pump(smart_home, connector_type="zigbee")
    with pytest.raises(ServiceError, match="no command translation"):
        await service.turn_on(device.id)


# --- Delegation: one chokepoint, never a second command path --------------------


@pytest.mark.asyncio
async def test_ha_turn_on_reaches_the_switch_chokepoint_once(
    service: SmartPumpService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_pump(smart_home)

    result = await service.turn_on(device.id)

    assert result["success"] is True
    assert result["kind"] == "pump"
    assert fake_connector.sent_commands == [("switch.water_pump", "turn_on", {})]


@pytest.mark.asyncio
async def test_ha_turn_off_reaches_the_switch_chokepoint_once(
    service: SmartPumpService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_pump(smart_home)

    result = await service.turn_off(device.id)

    assert result["success"] is True
    assert result["kind"] == "pump"
    assert fake_connector.sent_commands == [("switch.water_pump", "turn_off", {})]


@pytest.mark.asyncio
async def test_turn_on_and_off_together_send_exactly_two_commands(
    service: SmartPumpService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    """No duplicate execution: the pump service's own identity check
    never reaches the connector, so exactly one wire command leaves per
    call through the delegated switch service."""
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_pump(smart_home)

    await service.turn_on(device.id)
    await service.turn_off(device.id)

    assert fake_connector.sent_commands == [
        ("switch.water_pump", "turn_on", {}),
        ("switch.water_pump", "turn_off", {}),
    ]


# --- Reads: live state merge, pump-flavored --------------------------------------


@pytest.mark.asyncio
async def test_get_state_reports_on_true_with_pump_kind(
    service: SmartPumpService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_pump(smart_home)
    fake_connector.states["switch.water_pump"] = DeviceState(
        external_id="switch.water_pump", status="on", attributes={}
    )

    state = await service.get_state(device.id)

    assert state["on"] is True
    assert state["available"] is True
    assert state["kind"] == "pump"


@pytest.mark.asyncio
async def test_get_state_reports_on_false(
    service: SmartPumpService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_pump(smart_home)
    fake_connector.states["switch.water_pump"] = DeviceState(
        external_id="switch.water_pump", status="off", attributes={}
    )

    state = await service.get_state(device.id)

    assert state["on"] is False
    assert state["kind"] == "pump"


@pytest.mark.asyncio
async def test_get_state_falls_back_when_connector_unreachable(
    service: SmartPumpService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_pump(smart_home)

    state = await service.get_state(device.id)

    assert state["id"] == device.id
    assert state["on"] is None
    assert state["available"] is False
    assert state["kind"] == "pump"


# --- Failure honesty --------------------------------------------------------------


@pytest.mark.asyncio
async def test_failed_command_reports_failure_not_success(
    service: SmartPumpService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    fake_connector.next_command_succeeds = False
    _, device = await _home_and_pump(smart_home)

    result = await service.turn_on(device.id)

    assert result["success"] is False
    assert result["detail"]
    assert result["kind"] == "pump"


# --- Public surface (smallest abstraction, no duplicates) --------------------------


@pytest.mark.asyncio
async def test_pump_service_public_surface_is_on_off_state_only() -> None:
    """No ``list_pumps`` (``list_switches`` already enumerates every
    pump-controllable device), no energy/telemetry methods (the shipped
    SensorService owns those), no parallel command path."""
    public_methods = {
        name
        for name in dir(SmartPumpService)
        if not name.startswith("_") and callable(getattr(SmartPumpService, name))
    }
    assert public_methods == {"turn_on", "turn_off", "get_state"}


@pytest.mark.asyncio
async def test_pump_service_does_not_reach_the_connector_directly(
    service: SmartPumpService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    """Composition shape: the pump service holds no connectivity /
    permissions references of its own -- every command must flow
    through the composed switch service."""
    assert not hasattr(service, "_connectivity")
    assert not hasattr(service, "_permissions")
    assert not hasattr(service, "_connector")


# --- Scheduling: existing scheduler, existing switch_on/switch_off steps -----------
#
# The scheduler needs no pump-specific integration: a pump IS a
# switch-backed device, so an AGENT_TOOL step calling `switch_on`/
# `switch_off` already drives it. `pump_on`/`pump_off` are
# confirm-required, and a scheduled workflow hardcodes confirm=None
# (Policy A), so those steps are denied there -- deliberately, never
# silently allowed.


@pytest.fixture
def automation(settings, db):
    from jarvis.services.automation_service import AutomationService
    from tests.fakes.fake_os_automation import FakeOSAutomation

    return AutomationService(FakeOSAutomation(), settings, database=db)


@pytest.fixture
def workflow_executor(settings, automation, switch_service, service):
    from jarvis.services.workflow_execution_service import WorkflowExecutionService

    return WorkflowExecutionService(
        settings=settings,
        automation=automation,
        smart_switch=switch_service,
        pumps=service,
    )


@pytest.fixture
def scheduler(db, permissions, settings, workflow_executor):
    from jarvis.services.schedule_service import ScheduleService

    return ScheduleService(
        database=db,
        permissions=permissions,
        settings=settings,
        workflow_executor=workflow_executor,
    )


def _agent_tool_step(tool_name: str, tool_args: dict | None = None) -> dict:
    return {"kind": "agent_tool", "tool_name": tool_name, "tool_args": tool_args or {}}


async def _force_due(db, schedule_id: str, *, seconds_ago: float = 1.0) -> None:
    from jarvis.infrastructure.database.repositories.schedule_repository import ScheduleRepository

    async with db.session() as sess:
        repo = ScheduleRepository(sess)
        row = await repo.get(schedule_id)
        row.next_fire_at = datetime.now(UTC) - timedelta(seconds=seconds_ago)
        await sess.flush()


async def _grant_scheduler(permissions: PermissionModel) -> None:
    from jarvis.services.schedule_service import SCHEDULER_PRINCIPAL, SCHEDULER_SCOPE

    await permissions.grant(SCHEDULER_PRINCIPAL, SCHEDULER_SCOPE)


@pytest.mark.asyncio
async def test_scheduled_workflow_executes_pump_via_existing_switch_on_step(
    scheduler,
    permissions,
    db,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    """A scheduled workflow drives a switch-backed pump through the
    already-shipped ``switch_on`` AGENT_TOOL step -- the scheduler
    itself is untouched by this slice."""
    await _grant_scheduler(permissions)
    await _grant(permissions)
    await connectivity.connect("home_assistant")
    _, device = await _home_and_pump(smart_home)

    schedule = await scheduler.create_schedule(
        name="morning pump",
        kind="interval",
        interval_seconds=60.0,
        steps=[_agent_tool_step("switch_on", {"device_id": device.id})],
    )
    # switch_on is deliberately NOT confirm-required, so the schedule
    # carries no confirmation flag at all.
    assert schedule["contains_confirm_required_steps"] is False

    await _force_due(db, schedule["id"])
    await scheduler.tick()

    executions = await scheduler.list_executions(schedule["id"])
    assert len(executions) == 1
    assert executions[0]["status"] == "succeeded"
    assert fake_connector.sent_commands == [("switch.water_pump", "turn_on", {})]


@pytest.mark.asyncio
async def test_scheduled_workflow_executes_pump_off_via_existing_switch_off_step(
    scheduler,
    permissions,
    db,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await _grant_scheduler(permissions)
    await _grant(permissions)
    await connectivity.connect("home_assistant")
    _, device = await _home_and_pump(smart_home)

    schedule = await scheduler.create_schedule(
        name="evening pump stop",
        kind="interval",
        interval_seconds=60.0,
        steps=[_agent_tool_step("switch_off", {"device_id": device.id})],
    )
    await _force_due(db, schedule["id"])
    await scheduler.tick()

    executions = await scheduler.list_executions(schedule["id"])
    assert executions[0]["status"] == "succeeded"
    assert fake_connector.sent_commands == [("switch.water_pump", "turn_off", {})]


@pytest.mark.asyncio
async def test_scheduled_pump_on_step_is_flagged_and_denied_by_confirmation_policy(
    scheduler,
    permissions,
    db,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    """Confirm-required pump tools cannot ride the scheduler: the
    creation scan flags the step, and Policy A (``confirm=None``)
    denies it at execution -- never a silent run, never a crash."""
    await _grant_scheduler(permissions)
    await _grant(permissions)
    await connectivity.connect("home_assistant")
    _, device = await _home_and_pump(smart_home)

    schedule = await scheduler.create_schedule(
        name="pump via gated tool",
        kind="interval",
        interval_seconds=60.0,
        steps=[_agent_tool_step("pump_on", {"device_id": device.id})],
    )
    assert schedule["contains_confirm_required_steps"] is True

    await _force_due(db, schedule["id"])
    await scheduler.tick()

    executions = await scheduler.list_executions(schedule["id"])
    assert executions[0]["status"] == "denied"
    assert executions[0]["error"] == "Every step in this workflow was denied."
    # The confirmation detail lives at the step level ...
    step = executions[0]["step_results"][0]
    assert step["status"] == "denied"
    assert "requires confirmation" in step["error"]
    # Denial means no wire command ever left -- the pump never moved.
    assert fake_connector.sent_commands == []
