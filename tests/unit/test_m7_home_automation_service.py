"""HomeAutomationService tests -- M7 (event-based triggers).

Real (temp-file) SQLite throughout, matching every M7/M12 service
test's own pattern -- only ``FakeOSAutomation``/``FakeDeviceConnector``
(the side-effect boundaries) are faked; ``SmartHomeService``,
``ConnectivityService``, ``PermissionModel``, ``WorkflowExecutionService``,
and ``HomeAutomationService`` itself are all real. See
``docs/M7_HOME_AUTOMATION_LOGIC_CONTRACT.md`` §33 for the required test
matrix this file implements.

**Dispatch is a background task** (Logic Contract -- the event handler
never blocks the publisher). Every test that publishes a
``DeviceStateChangedEvent`` and needs to observe the resulting dispatch
calls ``await service.stop()`` afterward -- the same production
shutdown path already drains every pending dispatch task, reused here
rather than adding a test-only hook.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from jarvis.core.events.event_bus import EventBus
from jarvis.core.events.events import DeviceStateChangedEvent
from jarvis.core.exceptions import ServiceError
from jarvis.services.home_automation_service import (
    HOME_AUTOMATION_PRINCIPAL,
    HOME_AUTOMATION_SCOPE,
    AutomationTriggerNotFoundError,
    HomeAutomationPermissionError,
    HomeAutomationService,
)
from jarvis.services.smart_home_service import SmartHomeService
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
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def permissions(tmp_path: Path, bus: EventBus):
    from jarvis.core.plugins.permissions import PermissionModel

    return PermissionModel(bus, store_path=tmp_path / "permissions.json")


@pytest.fixture
def smart_home(db, bus: EventBus) -> SmartHomeService:
    return SmartHomeService(database=db, event_bus=bus)


@pytest.fixture
def workflow_executor(settings) -> WorkflowExecutionService:
    return WorkflowExecutionService(settings=settings)


@pytest.fixture
def service(db, permissions, settings, bus, workflow_executor) -> HomeAutomationService:
    return HomeAutomationService(
        database=db,
        permissions=permissions,
        settings=settings,
        event_bus=bus,
        workflow_executor=workflow_executor,
    )


async def _grant(permissions) -> None:
    await permissions.grant(HOME_AUTOMATION_PRINCIPAL, HOME_AUTOMATION_SCOPE)


def _automation_step() -> list[dict]:
    return [{"kind": "agent_tool", "tool_name": "no_such_tool"}]


# --- Permission --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_denied_without_grant(service: HomeAutomationService) -> None:
    with pytest.raises(HomeAutomationPermissionError):
        await service.create_automation(
            name="x", device_id="light-1", to_status="paired", steps=_automation_step()
        )


@pytest.mark.asyncio
async def test_permission_declared_pending_at_construction(permissions) -> None:
    assert permissions.state(HOME_AUTOMATION_PRINCIPAL, HOME_AUTOMATION_SCOPE).value == "pending"


# --- CRUD ----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_requires_a_non_empty_name(service, permissions) -> None:
    await _grant(permissions)
    with pytest.raises(ServiceError, match="non-empty 'name'"):
        await service.create_automation(
            name="", device_id="light-1", to_status="paired", steps=_automation_step()
        )


@pytest.mark.asyncio
async def test_create_requires_a_non_empty_device_id(service, permissions) -> None:
    await _grant(permissions)
    with pytest.raises(ServiceError, match="non-empty 'device_id'"):
        await service.create_automation(
            name="x", device_id="", to_status="paired", steps=_automation_step()
        )


@pytest.mark.asyncio
async def test_create_requires_a_non_empty_to_status(service, permissions) -> None:
    await _grant(permissions)
    with pytest.raises(ServiceError, match="non-empty 'to_status'"):
        await service.create_automation(
            name="x", device_id="light-1", to_status="", steps=_automation_step()
        )


@pytest.mark.asyncio
async def test_create_requires_at_least_one_step(service, permissions) -> None:
    await _grant(permissions)
    with pytest.raises(ServiceError, match="at least one step"):
        await service.create_automation(name="x", device_id="light-1", to_status="paired", steps=[])


@pytest.mark.asyncio
async def test_create_then_get(service, permissions) -> None:
    await _grant(permissions)
    created = await service.create_automation(
        name="x", device_id="light-1", to_status="paired", steps=_automation_step()
    )
    assert created["device_id"] == "light-1"
    assert created["to_status"] == "paired"
    assert created["from_status"] == ""
    assert created["enabled"] is True

    got = await service.get_automation(created["id"])
    assert got["id"] == created["id"]
    assert "last_execution" not in got


@pytest.mark.asyncio
async def test_get_unknown_automation_raises(service, permissions) -> None:
    await _grant(permissions)
    with pytest.raises(AutomationTriggerNotFoundError):
        await service.get_automation("no-such-id")


@pytest.mark.asyncio
async def test_list_automations_filters_enabled_only(service, permissions) -> None:
    await _grant(permissions)
    a = await service.create_automation(
        name="a", device_id="light-1", to_status="paired", steps=_automation_step()
    )
    await service.create_automation(
        name="b", device_id="light-2", to_status="paired", steps=_automation_step()
    )
    await service.disable_automation(a["id"])

    all_rows = await service.list_automations()
    enabled_rows = await service.list_automations(enabled_only=True)
    assert len(all_rows) == 2
    assert len(enabled_rows) == 1
    assert enabled_rows[0]["name"] == "b"


@pytest.mark.asyncio
async def test_enable_disable_round_trip(service, permissions) -> None:
    await _grant(permissions)
    created = await service.create_automation(
        name="x", device_id="light-1", to_status="paired", steps=_automation_step()
    )
    disabled = await service.disable_automation(created["id"])
    assert disabled["enabled"] is False
    enabled = await service.enable_automation(created["id"])
    assert enabled["enabled"] is True


@pytest.mark.asyncio
async def test_delete_cascades_the_dedicated_workflow(service, permissions, db) -> None:
    await _grant(permissions)
    created = await service.create_automation(
        name="x", device_id="light-1", to_status="paired", steps=_automation_step()
    )
    workflow_id = created["workflow_id"]

    assert await service.delete_automation(created["id"]) is True

    with pytest.raises(AutomationTriggerNotFoundError):
        await service.get_automation(created["id"])

    from jarvis.infrastructure.database.repositories.schedule_repository import WorkflowRepository

    async with db.session() as sess:
        workflow = await WorkflowRepository(sess).get(workflow_id)  # type: ignore[arg-type]
    assert workflow is None


# --- Manual execution ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_automation_reuses_workflow_executor_and_records_manual_source(
    service, permissions
) -> None:
    await _grant(permissions)
    created = await service.create_automation(
        name="x", device_id="light-1", to_status="paired", steps=_automation_step()
    )

    result = await service.run_automation(created["id"])

    assert result["source"] == "manual"
    assert result["status"] == "failed"  # no_such_tool is unregistered
    assert "Unknown tool" in result["step_results"][0]["error"]


@pytest.mark.asyncio
async def test_run_automation_unknown_id_raises(service, permissions) -> None:
    await _grant(permissions)
    with pytest.raises(AutomationTriggerNotFoundError):
        await service.run_automation("no-such-id")


@pytest.mark.asyncio
async def test_run_automation_when_already_running_returns_current_state(
    service, permissions, db
) -> None:
    """Manual run reuses the identical dispatch path, including the
    has_non_terminal duplicate-fire check -- a queued/running execution
    blocks a second manual run from starting a new one."""
    await _grant(permissions)
    created = await service.create_automation(
        name="x", device_id="light-1", to_status="paired", steps=_automation_step()
    )

    from jarvis.infrastructure.database.repositories.automation_repository import (
        AutomationExecutionRepository,
    )

    async with db.session() as sess:
        await AutomationExecutionRepository(sess).add(  # type: ignore[arg-type]
            automation_trigger_id=created["id"], workflow_id=created["workflow_id"], source="manual"
        )

    result = await service.run_automation(created["id"])
    assert result["id"] == created["id"]
    assert "status" not in result or result.get("device_id") == "light-1"


# --- Event matching --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_matching_transition_dispatches_the_automation(
    service, permissions, smart_home, bus
) -> None:
    await _grant(permissions)
    await service.create_automation(
        name="x", device_id="light-1", to_status="paired", steps=_automation_step()
    )
    await service.start()

    await bus.publish(
        DeviceStateChangedEvent(device_id="light-1", previous_status="discovered", status="paired")
    )
    await service.stop()  # drains the background dispatch task

    automations = await service.list_automations()
    executions = await service.list_executions(automations[0]["id"])
    assert len(executions) == 1
    assert executions[0]["source"] == "event"


@pytest.mark.asyncio
async def test_wrong_device_does_not_match(service, permissions, bus) -> None:
    await _grant(permissions)
    created = await service.create_automation(
        name="x", device_id="light-1", to_status="paired", steps=_automation_step()
    )
    await service.start()

    await bus.publish(
        DeviceStateChangedEvent(device_id="light-2", previous_status="discovered", status="paired")
    )
    await service.stop()

    assert await service.list_executions(created["id"]) == []


@pytest.mark.asyncio
async def test_wrong_target_status_does_not_match(service, permissions, bus) -> None:
    await _grant(permissions)
    created = await service.create_automation(
        name="x", device_id="light-1", to_status="paired", steps=_automation_step()
    )
    await service.start()

    await bus.publish(
        DeviceStateChangedEvent(device_id="light-1", previous_status="discovered", status="offline")
    )
    await service.stop()

    assert await service.list_executions(created["id"]) == []


@pytest.mark.asyncio
async def test_wrong_previous_status_does_not_match_when_from_status_is_set(
    service, permissions, bus
) -> None:
    await _grant(permissions)
    created = await service.create_automation(
        name="x",
        device_id="light-1",
        to_status="paired",
        from_status="offline",
        steps=_automation_step(),
    )
    await service.start()

    await bus.publish(
        DeviceStateChangedEvent(device_id="light-1", previous_status="discovered", status="paired")
    )
    await service.stop()

    assert await service.list_executions(created["id"]) == []


@pytest.mark.asyncio
async def test_wildcard_from_status_matches_any_previous_status(service, permissions, bus) -> None:
    await _grant(permissions)
    created = await service.create_automation(
        name="x", device_id="light-1", to_status="paired", steps=_automation_step()
    )  # from_status left blank -- wildcard
    await service.start()

    await bus.publish(
        DeviceStateChangedEvent(device_id="light-1", previous_status="unreachable", status="paired")
    )
    await service.stop()

    assert len(await service.list_executions(created["id"])) == 1


@pytest.mark.asyncio
async def test_disabled_automation_does_not_match(service, permissions, bus) -> None:
    await _grant(permissions)
    created = await service.create_automation(
        name="x", device_id="light-1", to_status="paired", steps=_automation_step()
    )
    await service.disable_automation(created["id"])
    await service.start()

    await bus.publish(
        DeviceStateChangedEvent(device_id="light-1", previous_status="discovered", status="paired")
    )
    await service.stop()

    assert await service.list_executions(created["id"]) == []


@pytest.mark.asyncio
async def test_multiple_matching_automations_each_dispatch(service, permissions, bus) -> None:
    await _grant(permissions)
    first = await service.create_automation(
        name="a", device_id="light-1", to_status="paired", steps=_automation_step()
    )
    second = await service.create_automation(
        name="b", device_id="light-1", to_status="paired", steps=_automation_step()
    )
    await service.start()

    await bus.publish(
        DeviceStateChangedEvent(device_id="light-1", previous_status="discovered", status="paired")
    )
    await service.stop()

    assert len(await service.list_executions(first["id"])) == 1
    assert len(await service.list_executions(second["id"])) == 1


# --- Duplicate-fire / cooldown -----------------------------------------------------------


@pytest.mark.asyncio
async def test_already_running_automation_is_not_dispatched_again(
    service, permissions, bus, db
) -> None:
    await _grant(permissions)
    created = await service.create_automation(
        name="x", device_id="light-1", to_status="paired", steps=_automation_step()
    )

    from jarvis.infrastructure.database.repositories.automation_repository import (
        AutomationExecutionRepository,
    )

    async with db.session() as sess:
        await AutomationExecutionRepository(sess).add(  # type: ignore[arg-type]
            automation_trigger_id=created["id"], workflow_id=created["workflow_id"], source="manual"
        )

    await service.start()
    await bus.publish(
        DeviceStateChangedEvent(device_id="light-1", previous_status="discovered", status="paired")
    )
    await service.stop()

    # Still exactly the one pre-seeded non-terminal execution -- no
    # second row was created (silent skip, matching Scheduler's own
    # has_non_terminal early-return).
    assert len(await service.list_executions(created["id"])) == 1


@pytest.mark.asyncio
async def test_cooldown_prevents_refiring_within_the_window(
    service, permissions, bus, settings, db
) -> None:
    await _grant(permissions)
    created = await service.create_automation(
        name="x", device_id="light-1", to_status="paired", steps=_automation_step()
    )

    from jarvis.infrastructure.database.repositories.automation_repository import (
        AutomationTriggerRepository,
    )

    now = datetime.now(UTC)
    async with db.session() as sess:
        await AutomationTriggerRepository(sess).record_fire(  # type: ignore[arg-type]
            created["id"], last_fired_at=now, last_execution_id=None
        )

    await service.start()
    await bus.publish(
        DeviceStateChangedEvent(device_id="light-1", previous_status="discovered", status="paired")
    )
    await service.stop()

    assert await service.list_executions(created["id"]) == []


@pytest.mark.asyncio
async def test_refires_once_cooldown_has_elapsed(service, permissions, bus, settings, db) -> None:
    await _grant(permissions)
    created = await service.create_automation(
        name="x", device_id="light-1", to_status="paired", steps=_automation_step()
    )

    from jarvis.infrastructure.database.repositories.automation_repository import (
        AutomationTriggerRepository,
    )

    long_ago = datetime.now(UTC) - timedelta(
        seconds=settings.home_automation.min_refire_interval_seconds + 60.0
    )
    async with db.session() as sess:
        await AutomationTriggerRepository(sess).record_fire(  # type: ignore[arg-type]
            created["id"], last_fired_at=long_ago, last_execution_id=None
        )

    await service.start()
    await bus.publish(
        DeviceStateChangedEvent(device_id="light-1", previous_status="discovered", status="paired")
    )
    await service.stop()

    assert len(await service.list_executions(created["id"])) == 1


# --- Permission revocation / security ----------------------------------------------------


@pytest.mark.asyncio
async def test_permission_revoked_after_creation_denies_at_execution(
    service, permissions, bus
) -> None:
    """Automation-creation permission never implies action-execution
    permission -- and here, revoking Home Automation's own CRUD
    permission after creation does not even prevent dispatch (dispatch
    doesn't re-check CRUD permission at all, by design -- only the
    target action's own permission matters). This test instead proves
    the target action's own permission gate (AgentPermissionGate/the
    device-service `_require_permission()`) is what's re-evaluated
    fresh at execution time, not any state cached at creation."""
    await _grant(permissions)
    created = await service.create_automation(
        name="x",
        device_id="light-1",
        to_status="paired",
        steps=[{"kind": "agent_tool", "tool_name": "no_such_tool"}],
    )

    # No device-category service is wired into this fixture's
    # WorkflowExecutionService at all -- so "no_such_tool" is
    # unconditionally unknown regardless of any permission state,
    # proving the executor never trusts anything cached at creation
    # time; it always resolves the live tool registry at dispatch time.
    result = await service.run_automation(created["id"])
    assert result["status"] == "failed"


# --- Lifecycle / subscription safety ------------------------------------------------------


@pytest.mark.asyncio
async def test_start_is_idempotent_no_duplicate_subscription(service, bus) -> None:
    await service.start()
    await service.start()
    assert len(bus._subs.get(DeviceStateChangedEvent, [])) == 1
    await service.stop()


@pytest.mark.asyncio
async def test_stop_unsubscribes_no_leaked_subscription(service, bus) -> None:
    await service.start()
    await service.stop()
    assert len(bus._subs.get(DeviceStateChangedEvent, [])) == 0


@pytest.mark.asyncio
async def test_stop_before_start_is_safe(service) -> None:
    await service.stop()  # must not raise


@pytest.mark.asyncio
async def test_events_after_stop_do_not_dispatch(service, permissions, bus) -> None:
    await _grant(permissions)
    created = await service.create_automation(
        name="x", device_id="light-1", to_status="paired", steps=_automation_step()
    )
    await service.start()
    await service.stop()

    await bus.publish(
        DeviceStateChangedEvent(device_id="light-1", previous_status="discovered", status="paired")
    )

    assert await service.list_executions(created["id"]) == []


# --- Scope guards --------------------------------------------------------------------------


def test_home_automation_service_introduces_no_connector_or_scheduler_coupling() -> None:
    import inspect

    from jarvis.services import home_automation_service

    source = inspect.getsource(home_automation_service)
    for forbidden in (
        "MqttConnector",
        "HomeAssistantConnector",
        "import schedule_service",
        "from jarvis.services.schedule_service",
        "MemoryService",
        "SmartHomeMemoryService",
        "AnalyticsService",
    ):
        assert forbidden not in source


def test_home_automation_service_never_imports_event_viewer() -> None:
    import importlib.util

    for module_name in (
        "jarvis.services.event_viewer_service",
        "jarvis.services.home_automation_analytics_service",
    ):
        assert importlib.util.find_spec(module_name) is None


def test_home_automation_event_is_not_relayed_over_websocket() -> None:
    """No AutomationTriggeredEvent/AutomationExecutedEvent/
    AutomationFailedEvent was fabricated (Logic Contract §25 -- deferred,
    no concrete consumer need demonstrated)."""
    from jarvis.core.lifecycle import runtime_ws_hub

    for name in ("AutomationTriggeredEvent", "AutomationExecutedEvent", "AutomationFailedEvent"):
        assert not hasattr(runtime_ws_hub, name)
