"""Thermostat agent tool tests -- Milestone 12 Appliance Control
(Climate / Thermostat Slice).

Real ``ThermostatService`` over real (temp-file) SQLite, a real
``PermissionModel`` and a ``FakeDeviceConnector``, matching
``test_m12_appliance_tools.py``'s own fixtures.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("langchain_core")

from jarvis.agents.tools.thermostat_tools import build_thermostat_tools
from jarvis.core.connectivity.registry import ConnectorFactoryRegistry
from jarvis.core.events.event_bus import EventBus
from jarvis.core.interfaces.connectivity import DeviceState
from jarvis.core.plugins.permissions import PermissionModel
from jarvis.services.connectivity_service import ConnectivityService
from jarvis.services.smart_home_service import SmartHomeService
from jarvis.services.thermostat_service import (
    SMART_HOME_SCOPE,
    THERMOSTAT_PRINCIPAL,
    ThermostatService,
)
from tests.fakes.fake_device_connector import FakeDeviceConnector

_EXTERNAL_ID = "climate.living_room"


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
def service(smart_home, connectivity, permissions) -> ThermostatService:
    return ThermostatService(
        smart_home=smart_home, connectivity=connectivity, permissions=permissions
    )


@pytest.fixture
def tools(service: ThermostatService):
    return {t.name: t for t in build_thermostat_tools(service)}


async def _grant(permissions: PermissionModel) -> None:
    await permissions.grant(THERMOSTAT_PRINCIPAL, SMART_HOME_SCOPE)


async def _register_thermostat(smart_home: SmartHomeService):
    home = await smart_home.create_home("Primary Residence")
    return await smart_home.register_discovered_device(
        home.id,
        "Living Room AC",
        device_type="thermostat",
        external_id=_EXTERNAL_ID,
        metadata={"connector_type": "home_assistant", "domain": "climate"},
    )


# --- Registry registration -----------------------------------------------------


def test_registry_omits_thermostat_tools_when_not_wired() -> None:
    from jarvis.agents.tools.registry import build_tool_registry

    assert build_tool_registry() == []


@pytest.mark.asyncio
async def test_registry_includes_thermostat_tools_when_service_provided(
    service: ThermostatService,
) -> None:
    from jarvis.agents.tools.registry import build_tool_registry

    tools = build_tool_registry(thermostats=service)
    names = {t.name for t in tools}
    assert names == {"list_thermostats", "get_thermostat_state", "set_thermostat_state"}


# --- Reads (ungated) -------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_thermostats_tool_reports_no_thermostats(tools) -> None:
    result = await tools["list_thermostats"].ainvoke({})
    assert "No thermostats" in result


@pytest.mark.asyncio
async def test_list_and_get_tools_require_no_grant(tools, smart_home: SmartHomeService) -> None:
    device = await _register_thermostat(smart_home)

    listed = await tools["list_thermostats"].ainvoke({})
    got = await tools["get_thermostat_state"].ainvoke({"device_id": device.id})

    assert "Couldn't" not in listed
    assert "Couldn't" not in got


@pytest.mark.asyncio
async def test_get_thermostat_state_tool_full_payload(
    tools,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    device = await _register_thermostat(smart_home)
    fake_connector.states[_EXTERNAL_ID] = DeviceState(
        external_id=_EXTERNAL_ID,
        status="cool",
        attributes={"current_temperature": 24.5, "temperature": 22.0},
    )

    result = await tools["get_thermostat_state"].ainvoke({"device_id": device.id})

    assert '"current_temperature": 24.5' in result
    assert '"hvac_mode": "cool"' in result


@pytest.mark.asyncio
async def test_get_thermostat_state_tool_reports_unknown_device_without_raising(tools) -> None:
    result = await tools["get_thermostat_state"].ainvoke({"device_id": "no-such-device"})
    assert "Couldn't read" in result


# --- Mutation (gated) --------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_thermostat_state_tool_denied_without_grant(
    tools, smart_home: SmartHomeService
) -> None:
    device = await _register_thermostat(smart_home)

    result = await tools["set_thermostat_state"].ainvoke(
        {"device_id": device.id, "temperature": 21.0}
    )

    assert "Couldn't" in result
    assert "permission" in result.lower()


@pytest.mark.asyncio
async def test_set_thermostat_state_tool_temperature_only(
    tools,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    device = await _register_thermostat(smart_home)
    fake_connector.states[_EXTERNAL_ID] = DeviceState(
        external_id=_EXTERNAL_ID, status="cool", attributes={}
    )

    result = await tools["set_thermostat_state"].ainvoke(
        {"device_id": device.id, "temperature": 21.0}
    )

    assert '"success": true' in result.lower()
    assert fake_connector.sent_commands == [
        (_EXTERNAL_ID, "set_temperature", {"temperature": 21.0})
    ]


@pytest.mark.asyncio
async def test_set_thermostat_state_tool_mode_only(
    tools,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    device = await _register_thermostat(smart_home)
    fake_connector.states[_EXTERNAL_ID] = DeviceState(
        external_id=_EXTERNAL_ID, status="cool", attributes={}
    )

    result = await tools["set_thermostat_state"].ainvoke(
        {"device_id": device.id, "hvac_mode": "heat"}
    )

    assert '"success": true' in result.lower()
    assert fake_connector.sent_commands == [(_EXTERNAL_ID, "set_hvac_mode", {"hvac_mode": "heat"})]


@pytest.mark.asyncio
async def test_set_thermostat_state_tool_combined_is_one_merged_intent(
    tools,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    """One tool call, one user intent -- even though HA needs two wire
    calls underneath."""
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    device = await _register_thermostat(smart_home)
    fake_connector.states[_EXTERNAL_ID] = DeviceState(
        external_id=_EXTERNAL_ID, status="cool", attributes={}
    )

    result = await tools["set_thermostat_state"].ainvoke(
        {"device_id": device.id, "temperature": 20.0, "hvac_mode": "cool"}
    )

    assert '"success": true' in result.lower()
    assert len(fake_connector.sent_commands) == 2


@pytest.mark.asyncio
async def test_set_thermostat_state_tool_reports_error_without_raising(
    tools, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    result = await tools["set_thermostat_state"].ainvoke(
        {"device_id": "no-such-device", "temperature": 21.0}
    )
    assert "Couldn't change" in result


# --- No separate single-attribute mutation tools exist -------------------------------


def test_no_separate_temperature_or_mode_tools(service: ThermostatService) -> None:
    names = {t.name for t in build_thermostat_tools(service)}
    assert "set_thermostat_temperature" not in names
    assert "set_thermostat_mode" not in names
