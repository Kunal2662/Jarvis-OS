"""Sensor agent tool tests -- Milestone 12 Sensors.

Real ``SensorService`` over real (temp-file) SQLite, a real
``PermissionModel`` and a ``FakeDeviceConnector``, matching
``test_m12_smart_lock_tools.py``'s own fixtures.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("langchain_core")

from jarvis.agents.tools.sensor_tools import build_sensor_tools
from jarvis.core.connectivity.registry import ConnectorFactoryRegistry
from jarvis.core.events.event_bus import EventBus
from jarvis.core.interfaces.connectivity import DeviceState
from jarvis.core.plugins.permissions import PermissionModel
from jarvis.services.connectivity_service import ConnectivityService
from jarvis.services.sensor_service import SENSOR_PRINCIPAL, SMART_HOME_SCOPE, SensorService
from jarvis.services.smart_home_service import SmartHomeService
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
def service(smart_home, connectivity, permissions) -> SensorService:
    return SensorService(smart_home=smart_home, connectivity=connectivity, permissions=permissions)


@pytest.fixture
def tools(service: SensorService):
    return {t.name: t for t in build_sensor_tools(service)}


async def _grant(permissions: PermissionModel) -> None:
    await permissions.grant(SENSOR_PRINCIPAL, SMART_HOME_SCOPE)


async def _register_sensor(smart_home: SmartHomeService, *, device_class: str = "temperature"):
    home = await smart_home.create_home("Primary Residence")
    return await smart_home.register_discovered_device(
        home.id,
        "Living Room Temp",
        device_type="sensor",
        external_id="sensor.living_room_temp",
        metadata={
            "connector_type": "home_assistant",
            "domain": "sensor",
            "device_class": device_class,
        },
    )


# --- Registry registration -----------------------------------------------------


def test_registry_omits_sensor_tools_when_not_wired() -> None:
    from jarvis.agents.tools.registry import build_tool_registry

    assert build_tool_registry() == []


@pytest.mark.asyncio
async def test_registry_includes_sensor_tools_when_service_provided(service: SensorService) -> None:
    from jarvis.agents.tools.registry import build_tool_registry

    tools = build_tool_registry(sensors=service)
    names = {t.name for t in tools}
    assert {"list_sensors", "get_sensor_state", "get_sensor_value", "get_sensor_status"} <= names


# --- Permission enforcement -------------------------------------------------------


@pytest.mark.asyncio
async def test_list_sensors_tool_denied_without_grant(tools) -> None:
    result = await tools["list_sensors"].ainvoke({})
    assert "Couldn't" in result
    assert "permission" in result.lower()


@pytest.mark.asyncio
async def test_get_sensor_state_tool_denied_without_grant(
    tools, smart_home: SmartHomeService
) -> None:
    device = await _register_sensor(smart_home)

    result = await tools["get_sensor_state"].ainvoke({"device_id": device.id})

    assert "Couldn't" in result
    assert "permission" in result.lower()


# --- Basic tool behavior, once granted --------------------------------------------


@pytest.mark.asyncio
async def test_list_sensors_tool_reports_no_sensors(tools, permissions: PermissionModel) -> None:
    await _grant(permissions)
    result = await tools["list_sensors"].ainvoke({})
    assert "No sensors" in result


@pytest.mark.asyncio
async def test_get_sensor_state_tool_full_payload(
    tools,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    device = await _register_sensor(smart_home)
    fake_connector.states["sensor.living_room_temp"] = DeviceState(
        external_id="sensor.living_room_temp",
        status="21.5",
        attributes={"unit_of_measurement": "°C"},
    )

    result = await tools["get_sensor_state"].ainvoke({"device_id": device.id})

    assert '"value": 21.5' in result
    assert '"unit": "\\u00b0c"' in result.lower() or "°c" in result.lower()


@pytest.mark.asyncio
async def test_get_sensor_value_tool_returns_terse_shape(
    tools,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    device = await _register_sensor(smart_home)
    fake_connector.states["sensor.living_room_temp"] = DeviceState(
        external_id="sensor.living_room_temp",
        status="21.5",
        attributes={"unit_of_measurement": "°C"},
    )

    result = await tools["get_sensor_value"].ainvoke({"device_id": device.id})

    assert "device_class" not in result  # terse -- value/unit/state only.
    assert '"value": 21.5' in result


@pytest.mark.asyncio
async def test_get_sensor_status_tool_returns_availability_only(
    tools, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    device = await _register_sensor(smart_home)

    result = await tools["get_sensor_status"].ainvoke({"device_id": device.id})

    assert '"available": false' in result.lower()
    assert "value" not in result


@pytest.mark.asyncio
async def test_get_sensor_state_tool_reports_unknown_device_without_raising(
    tools, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    result = await tools["get_sensor_state"].ainvoke({"device_id": "no-such-device"})
    assert "Couldn't read" in result


@pytest.mark.asyncio
async def test_binary_sensor_tool_reports_friendly_label(
    tools,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Hallway Motion",
        device_type="sensor",
        external_id="binary_sensor.hallway_motion",
        metadata={
            "connector_type": "home_assistant",
            "domain": "binary_sensor",
            "device_class": "motion",
        },
    )
    fake_connector.states["binary_sensor.hallway_motion"] = DeviceState(
        external_id="binary_sensor.hallway_motion", status="on", attributes={}
    )

    result = await tools["get_sensor_state"].ainvoke({"device_id": device.id})

    assert '"state": "detected"' in result
