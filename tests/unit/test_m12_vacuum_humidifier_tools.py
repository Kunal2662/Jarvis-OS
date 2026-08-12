"""Vacuum + Humidifier agent tool tests -- Milestone 12 Appliance
Control (Vacuum + Humidifier Core Slice).

Real ``VacuumHumidifierService`` over real (temp-file) SQLite, a real
``PermissionModel`` and a ``FakeDeviceConnector``, matching
``test_m12_thermostat_tools.py``'s own fixtures.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("langchain_core")

from jarvis.agents.tools.vacuum_humidifier_tools import build_vacuum_humidifier_tools
from jarvis.core.connectivity.registry import ConnectorFactoryRegistry
from jarvis.core.events.event_bus import EventBus
from jarvis.core.interfaces.connectivity import DeviceState
from jarvis.core.plugins.permissions import PermissionModel
from jarvis.services.connectivity_service import ConnectivityService
from jarvis.services.smart_home_service import SmartHomeService
from jarvis.services.vacuum_humidifier_service import (
    SMART_HOME_SCOPE,
    VACUUM_HUMIDIFIER_PRINCIPAL,
    VacuumHumidifierService,
)
from tests.fakes.fake_device_connector import FakeDeviceConnector

_VACUUM_EXTERNAL_ID = "vacuum.living_room"
_HUMIDIFIER_EXTERNAL_ID = "humidifier.bedroom"


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
def fake_connector() -> FakeDeviceConnector:
    return FakeDeviceConnector()


@pytest.fixture
def smart_home(db) -> SmartHomeService:
    return SmartHomeService(database=db, event_bus=EventBus())


@pytest.fixture
def connectivity(
    fake_connector: FakeDeviceConnector, smart_home: SmartHomeService
) -> ConnectivityService:
    registry = ConnectorFactoryRegistry()
    registry.register("home_assistant", lambda config: fake_connector)
    return ConnectivityService(registry=registry, smart_home=smart_home)


@pytest.fixture
def permissions(tmp_path: Path) -> PermissionModel:
    return PermissionModel(EventBus(), store_path=tmp_path / "permissions.json")


@pytest.fixture
def service(smart_home, connectivity, permissions) -> VacuumHumidifierService:
    return VacuumHumidifierService(
        smart_home=smart_home, connectivity=connectivity, permissions=permissions
    )


@pytest.fixture
def tools(service: VacuumHumidifierService):
    return {t.name: t for t in build_vacuum_humidifier_tools(service)}


async def _grant(permissions: PermissionModel) -> None:
    await permissions.grant(VACUUM_HUMIDIFIER_PRINCIPAL, SMART_HOME_SCOPE)


async def _register_vacuum(smart_home: SmartHomeService):
    home = await smart_home.create_home("Primary Residence")
    return await smart_home.register_discovered_device(
        home.id,
        "Robot Vacuum",
        device_type="appliance",
        external_id=_VACUUM_EXTERNAL_ID,
        metadata={"connector_type": "home_assistant", "domain": "vacuum"},
    )


async def _register_humidifier(smart_home: SmartHomeService):
    home = await smart_home.create_home("Primary Residence")
    return await smart_home.register_discovered_device(
        home.id,
        "Bedroom Humidifier",
        device_type="appliance",
        external_id=_HUMIDIFIER_EXTERNAL_ID,
        metadata={"connector_type": "home_assistant", "domain": "humidifier"},
    )


# --- Registry registration -----------------------------------------------------


def test_registry_omits_tools_when_not_wired() -> None:
    from jarvis.agents.tools.registry import build_tool_registry

    assert build_tool_registry() == []


@pytest.mark.asyncio
async def test_registry_includes_all_nine_tools_when_service_provided(
    service: VacuumHumidifierService,
) -> None:
    from jarvis.agents.tools.registry import build_tool_registry

    tools = build_tool_registry(vacuum_humidifier=service)
    names = {t.name for t in tools}
    assert {
        "list_vacuums",
        "get_vacuum_state",
        "vacuum_start",
        "vacuum_stop",
        "vacuum_pause",
        "vacuum_dock",
        "list_humidifiers",
        "get_humidifier_state",
        "set_humidifier_state",
    } <= names


def test_exactly_nine_tools_are_built(service: VacuumHumidifierService) -> None:
    built = {t.name for t in build_vacuum_humidifier_tools(service)}
    assert built == {
        "list_vacuums",
        "get_vacuum_state",
        "vacuum_start",
        "vacuum_stop",
        "vacuum_pause",
        "vacuum_dock",
        "list_humidifiers",
        "get_humidifier_state",
        "set_humidifier_state",
    }


# --- Vacuum tools ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_vacuums_tool_reports_none(tools) -> None:
    result = await tools["list_vacuums"].ainvoke({})
    assert "No vacuums" in result


@pytest.mark.asyncio
async def test_get_vacuum_state_tool(
    tools,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    device = await _register_vacuum(smart_home)
    fake_connector.states[_VACUUM_EXTERNAL_ID] = DeviceState(
        external_id=_VACUUM_EXTERNAL_ID, status="cleaning", attributes={"battery_level": 55}
    )

    result = await tools["get_vacuum_state"].ainvoke({"device_id": device.id})

    assert '"state": "cleaning"' in result
    assert '"battery_level": 55.0' in result


@pytest.mark.asyncio
async def test_vacuum_start_tool_denied_without_grant(tools, smart_home: SmartHomeService) -> None:
    device = await _register_vacuum(smart_home)
    result = await tools["vacuum_start"].ainvoke({"device_id": device.id})
    assert "Couldn't" in result
    assert "permission" in result.lower()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_name,wire_command",
    [
        ("vacuum_start", "start"),
        ("vacuum_stop", "stop"),
        ("vacuum_pause", "pause"),
        ("vacuum_dock", "return_to_base"),
    ],
)
async def test_vacuum_command_tools_succeed_after_grant(
    tools,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
    tool_name: str,
    wire_command: str,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    device = await _register_vacuum(smart_home)
    fake_connector.states[_VACUUM_EXTERNAL_ID] = DeviceState(
        external_id=_VACUUM_EXTERNAL_ID, status="docked", attributes={}
    )

    result = await tools[tool_name].ainvoke({"device_id": device.id})

    assert '"success": true' in result.lower()
    assert fake_connector.sent_commands == [(_VACUUM_EXTERNAL_ID, wire_command, {})]


@pytest.mark.asyncio
async def test_vacuum_tool_reports_unknown_device_without_raising(
    tools, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    result = await tools["vacuum_start"].ainvoke({"device_id": "no-such-device"})
    assert "Couldn't" in result


# --- Humidifier tools -------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_humidifiers_tool_reports_none(tools) -> None:
    result = await tools["list_humidifiers"].ainvoke({})
    assert "No humidifiers" in result


@pytest.mark.asyncio
async def test_get_humidifier_state_tool(
    tools,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    device = await _register_humidifier(smart_home)
    fake_connector.states[_HUMIDIFIER_EXTERNAL_ID] = DeviceState(
        external_id=_HUMIDIFIER_EXTERNAL_ID,
        status="on",
        attributes={"current_humidity": 40.0, "humidity": 50.0, "mode": "auto"},
    )

    result = await tools["get_humidifier_state"].ainvoke({"device_id": device.id})

    assert '"on": true' in result.lower()
    assert '"target_humidity": 50.0' in result
    assert '"mode": "auto"' in result


@pytest.mark.asyncio
async def test_set_humidifier_state_tool_denied_without_grant(
    tools, smart_home: SmartHomeService
) -> None:
    device = await _register_humidifier(smart_home)
    result = await tools["set_humidifier_state"].ainvoke({"device_id": device.id, "on": True})
    assert "Couldn't" in result
    assert "permission" in result.lower()


@pytest.mark.asyncio
async def test_set_humidifier_state_tool_combined_mutation(
    tools,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    device = await _register_humidifier(smart_home)
    fake_connector.states[_HUMIDIFIER_EXTERNAL_ID] = DeviceState(
        external_id=_HUMIDIFIER_EXTERNAL_ID, status="off", attributes={}
    )

    result = await tools["set_humidifier_state"].ainvoke(
        {"device_id": device.id, "on": True, "target_humidity": 45.0}
    )

    assert '"success": true' in result.lower()
    assert fake_connector.sent_commands == [
        (_HUMIDIFIER_EXTERNAL_ID, "turn_on", {}),
        (_HUMIDIFIER_EXTERNAL_ID, "set_humidity", {"humidity": 45.0}),
    ]


@pytest.mark.asyncio
async def test_set_humidifier_state_tool_reports_error_without_raising(tools) -> None:
    result = await tools["set_humidifier_state"].ainvoke({"device_id": "no-such-device"})
    assert isinstance(result, str)


def test_set_humidifier_state_tool_has_no_mode_parameter(tools) -> None:
    schema_fields = tools["set_humidifier_state"].args_schema.model_fields
    assert "mode" not in schema_fields
