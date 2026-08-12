"""Water Heater agent tool tests -- Milestone 12 Appliance Control
(Water Heater Core Slice).

Real ``WaterHeaterService`` over real (temp-file) SQLite, a real
``PermissionModel`` and a ``FakeDeviceConnector``, matching
``test_m12_thermostat_tools.py``'s/``test_m12_media_player_tools.py``'s
own fixtures.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("langchain_core")

from jarvis.agents.tools.water_heater_tools import build_water_heater_tools
from jarvis.core.connectivity.registry import ConnectorFactoryRegistry
from jarvis.core.events.event_bus import EventBus
from jarvis.core.interfaces.connectivity import DeviceState
from jarvis.core.plugins.permissions import PermissionModel
from jarvis.services.connectivity_service import ConnectivityService
from jarvis.services.smart_home_service import SmartHomeService
from jarvis.services.water_heater_service import (
    SMART_HOME_SCOPE,
    WATER_HEATER_PRINCIPAL,
    WaterHeaterService,
)
from tests.fakes.fake_device_connector import FakeDeviceConnector

_EXTERNAL_ID = "water_heater.tank"


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
def service(smart_home, connectivity, permissions) -> WaterHeaterService:
    return WaterHeaterService(
        smart_home=smart_home, connectivity=connectivity, permissions=permissions
    )


@pytest.fixture
def tools(service: WaterHeaterService):
    return {t.name: t for t in build_water_heater_tools(service)}


async def _grant(permissions: PermissionModel) -> None:
    await permissions.grant(WATER_HEATER_PRINCIPAL, SMART_HOME_SCOPE)


async def _register_water_heater(smart_home: SmartHomeService):
    home = await smart_home.create_home("Primary Residence")
    return await smart_home.register_discovered_device(
        home.id,
        "Basement Water Heater",
        device_type="appliance",
        external_id=_EXTERNAL_ID,
        metadata={"connector_type": "home_assistant", "domain": "water_heater"},
    )


# --- Registry registration -----------------------------------------------------


def test_registry_omits_tools_when_not_wired() -> None:
    from jarvis.agents.tools.registry import build_tool_registry

    assert build_tool_registry() == []


@pytest.mark.asyncio
async def test_registry_includes_all_three_tools_when_service_provided(
    service: WaterHeaterService,
) -> None:
    from jarvis.agents.tools.registry import build_tool_registry

    tools = build_tool_registry(water_heaters=service)
    names = {t.name for t in tools}
    assert {
        "list_water_heaters",
        "get_water_heater_state",
        "set_water_heater_state",
    } <= names


def test_exactly_three_tools_are_built(service: WaterHeaterService) -> None:
    built = {t.name for t in build_water_heater_tools(service)}
    assert built == {
        "list_water_heaters",
        "get_water_heater_state",
        "set_water_heater_state",
    }


def test_no_per_attribute_tools_exist(service: WaterHeaterService) -> None:
    built = {t.name for t in build_water_heater_tools(service)}
    assert "turn_on" not in built
    assert "turn_off" not in built
    assert "set_temperature" not in built
    assert "set_operation_mode" not in built


# --- Read tools -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_water_heaters_tool_reports_none(tools) -> None:
    result = await tools["list_water_heaters"].ainvoke({})
    assert "No water heaters" in result


@pytest.mark.asyncio
async def test_get_water_heater_state_tool(
    tools,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    device = await _register_water_heater(smart_home)
    fake_connector.states[_EXTERNAL_ID] = DeviceState(
        external_id=_EXTERNAL_ID,
        status="eco",
        attributes={"temperature": 55.0, "current_temperature": 48.0},
    )

    result = await tools["get_water_heater_state"].ainvoke({"device_id": device.id})

    assert '"state": "eco"' in result
    assert '"target_temperature": 55.0' in result
    assert '"current_temperature": 48.0' in result


@pytest.mark.asyncio
async def test_get_water_heater_state_tool_reports_error_without_raising(tools) -> None:
    result = await tools["get_water_heater_state"].ainvoke({"device_id": "no-such-device"})
    assert "Couldn't" in result


# --- Merged state tool --------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_water_heater_state_tool_denied_without_grant(
    tools, smart_home: SmartHomeService
) -> None:
    device = await _register_water_heater(smart_home)
    result = await tools["set_water_heater_state"].ainvoke(
        {"device_id": device.id, "temperature": 55.0}
    )
    assert "Couldn't" in result
    assert "permission" in result.lower()


@pytest.mark.asyncio
async def test_set_water_heater_state_tool_combined_mutation(
    tools,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    device = await _register_water_heater(smart_home)
    fake_connector.states[_EXTERNAL_ID] = DeviceState(
        external_id=_EXTERNAL_ID, status="off", attributes={"operation_list": ["eco", "electric"]}
    )

    result = await tools["set_water_heater_state"].ainvoke(
        {"device_id": device.id, "on": True, "operation_mode": "electric", "temperature": 55.0}
    )

    assert '"success": true' in result.lower()
    assert fake_connector.sent_commands == [
        (_EXTERNAL_ID, "turn_on", {}),
        (_EXTERNAL_ID, "set_operation_mode", {"operation_mode": "electric"}),
        (_EXTERNAL_ID, "set_temperature", {"temperature": 55.0}),
    ]


@pytest.mark.asyncio
async def test_set_water_heater_state_tool_reports_error_without_raising(tools) -> None:
    result = await tools["set_water_heater_state"].ainvoke(
        {"device_id": "no-such-device", "temperature": 55.0}
    )
    assert isinstance(result, str)
    assert "Couldn't" in result


# --- Confirmation metadata (Logic Contract §11/§13) ---------------------------------


def test_set_water_heater_state_not_in_confirm_required_tools() -> None:
    """The Logic Contract evaluated and rejected gating this tool
    behind interactive confirmation -- pinned here so a future change
    cannot silently add it without deliberately touching this test."""
    from jarvis.core.config.settings import AgentSettings

    assert "set_water_heater_state" not in AgentSettings().confirm_required_tools
