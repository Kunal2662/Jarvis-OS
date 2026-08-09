"""SmartSwitchService tests -- Milestone 12 Energy Management (Core
Energy Slice).

Real (temp-file) SQLite ``SmartHomeService`` and a real ``PermissionModel``
throughout, matching ``test_m12_smart_lock_service.py``'s own pattern --
only the connector itself is faked (``FakeDeviceConnector``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core.connectivity.registry import ConnectorFactoryRegistry
from jarvis.core.events.event_bus import EventBus
from jarvis.core.exceptions import ServiceError
from jarvis.core.interfaces.connectivity import DeviceState
from jarvis.core.plugins.permissions import PermissionModel
from jarvis.services.connectivity_service import ConnectivityService
from jarvis.services.smart_home_service import SmartHomeService
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
def service(
    smart_home: SmartHomeService, connectivity: ConnectivityService, permissions: PermissionModel
) -> SmartSwitchService:
    return SmartSwitchService(
        smart_home=smart_home, connectivity=connectivity, permissions=permissions
    )


async def _grant(permissions: PermissionModel) -> None:
    await permissions.grant(SMART_SWITCH_PRINCIPAL, SMART_HOME_SCOPE)


async def _home_and_switch(smart_home: SmartHomeService, connector_type: str = "home_assistant"):
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Living Room Plug",
        device_type="switch",
        external_id="switch.living_room_plug",
        metadata={"connector_type": connector_type},
    )
    return home, device


# --- Permission enforcement --------------------------------------------------


@pytest.mark.asyncio
async def test_turn_on_denied_by_default(
    service: SmartSwitchService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_switch(smart_home)
    with pytest.raises(ServiceError, match="permission"):
        await service.turn_on(device.id)


@pytest.mark.asyncio
async def test_turn_off_denied_by_default(
    service: SmartSwitchService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_switch(smart_home)
    with pytest.raises(ServiceError, match="permission"):
        await service.turn_off(device.id)


@pytest.mark.asyncio
async def test_permission_declared_pending_at_construction(permissions: PermissionModel) -> None:
    assert permissions.state(SMART_SWITCH_PRINCIPAL, SMART_HOME_SCOPE).value == "pending"


@pytest.mark.asyncio
async def test_reads_do_not_require_permission(
    service: SmartSwitchService, smart_home: SmartHomeService
) -> None:
    """Deliberate departure from Sensors: a switch's on/off state
    carries no comparable privacy weight -- see Logic Contract §9."""
    _, device = await _home_and_switch(smart_home)
    # No grant() call anywhere in this test -- reads must still work.
    switches = await service.list_switches()
    assert len(switches) == 1
    state = await service.get_switch_state(device.id)
    assert state["id"] == device.id


# --- Validation ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_turn_on_rejects_non_switch_device(
    service: SmartSwitchService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    lock = await smart_home.register_discovered_device(
        home.id, "Front Door", device_type="lock", external_id="lock.front_door"
    )
    with pytest.raises(ServiceError, match="not a switch"):
        await service.turn_on(lock.id)


@pytest.mark.asyncio
async def test_turn_on_rejects_device_with_no_connector(
    service: SmartSwitchService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id, "Orphan Plug", device_type="switch"
    )
    with pytest.raises(ServiceError, match="no recorded connector"):
        await service.turn_on(device.id)


@pytest.mark.asyncio
async def test_turn_on_rejects_unsupported_connector_type(
    service: SmartSwitchService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    _, device = await _home_and_switch(smart_home, connector_type="zigbee")
    with pytest.raises(ServiceError, match="no command translation"):
        await service.turn_on(device.id)


@pytest.mark.asyncio
async def test_get_switch_state_unknown_device_raises(
    service: SmartSwitchService,
) -> None:
    with pytest.raises(ServiceError):
        await service.get_switch_state("no-such-device")


# --- Home Assistant translation ------------------------------------------------


@pytest.mark.asyncio
async def test_ha_turn_on_translation(
    service: SmartSwitchService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_switch(smart_home)

    result = await service.turn_on(device.id)

    assert result["success"] is True
    assert fake_connector.sent_commands == [("switch.living_room_plug", "turn_on", {})]


@pytest.mark.asyncio
async def test_ha_turn_off_translation(
    service: SmartSwitchService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_switch(smart_home)

    result = await service.turn_off(device.id)

    assert result["success"] is True
    assert fake_connector.sent_commands == [("switch.living_room_plug", "turn_off", {})]


# --- MQTT translation -----------------------------------------------------------


@pytest.mark.asyncio
async def test_mqtt_turn_on_and_off_translation(
    smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    mqtt_connector = FakeDeviceConnector()
    mqtt_connector.connector_type = "mqtt"
    registry = ConnectorFactoryRegistry()
    registry.register("mqtt", lambda config: mqtt_connector)
    mqtt_connectivity = ConnectivityService(registry=registry, smart_home=smart_home)
    mqtt_service = SmartSwitchService(
        smart_home=smart_home, connectivity=mqtt_connectivity, permissions=permissions
    )
    await mqtt_connectivity.connect("mqtt")
    await _grant(permissions)
    _, device = await _home_and_switch(smart_home, connector_type="mqtt")

    await mqtt_service.turn_on(device.id)
    await mqtt_service.turn_off(device.id)

    assert mqtt_connector.sent_commands == [
        ("switch.living_room_plug", "turn_on", {}),
        ("switch.living_room_plug", "turn_off", {}),
    ]


# --- Reads: live state merge ---------------------------------------------------


@pytest.mark.asyncio
async def test_get_switch_state_reports_on_true(
    service: SmartSwitchService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_switch(smart_home)
    fake_connector.states["switch.living_room_plug"] = DeviceState(
        external_id="switch.living_room_plug", status="on", attributes={}
    )

    state = await service.get_switch_state(device.id)

    assert state["on"] is True
    assert state["available"] is True


@pytest.mark.asyncio
async def test_get_switch_state_reports_on_false(
    service: SmartSwitchService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_switch(smart_home)
    fake_connector.states["switch.living_room_plug"] = DeviceState(
        external_id="switch.living_room_plug", status="off", attributes={}
    )

    state = await service.get_switch_state(device.id)

    assert state["on"] is False


@pytest.mark.asyncio
async def test_get_switch_state_falls_back_when_connector_unreachable(
    service: SmartSwitchService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_switch(smart_home)

    state = await service.get_switch_state(device.id)

    assert state["id"] == device.id
    assert state["on"] is None
    assert state["available"] is False


@pytest.mark.asyncio
async def test_connector_reported_offline_status_marks_unavailable(
    service: SmartSwitchService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_switch(smart_home)
    fake_connector.states["switch.living_room_plug"] = DeviceState(
        external_id="switch.living_room_plug", status="unavailable", attributes={}
    )

    state = await service.get_switch_state(device.id)

    assert state["available"] is False
    assert state["on"] is None


@pytest.mark.asyncio
async def test_list_switches_does_not_make_a_live_connector_read(
    service: SmartSwitchService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _home_and_switch(smart_home)
    fake_connector.states["switch.living_room_plug"] = DeviceState(
        external_id="switch.living_room_plug", status="on", attributes={}
    )

    rows = await service.list_switches()

    assert len(rows) == 1
    assert rows[0]["on"] is None  # DB-only -- see SmartSwitchService.list_switches docstring.


# --- Failure honesty --------------------------------------------------------------


@pytest.mark.asyncio
async def test_failed_command_reports_failure_not_success(
    service: SmartSwitchService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    fake_connector.next_command_succeeds = False
    _, device = await _home_and_switch(smart_home)

    result = await service.turn_on(device.id)

    assert result["success"] is False
    assert result["detail"]


# --- Energy reuse (no duplicate telemetry) ---------------------------------------


@pytest.mark.asyncio
async def test_switch_service_has_no_energy_reading_methods() -> None:
    """Power/energy readings are the shipped SensorService's job --
    SmartSwitchService must not grow a parallel telemetry surface."""
    public_methods = {
        name
        for name in dir(SmartSwitchService)
        if not name.startswith("_") and callable(getattr(SmartSwitchService, name))
    }
    assert public_methods == {"list_switches", "get_switch_state", "turn_on", "turn_off"}


@pytest.mark.asyncio
async def test_energy_sensor_on_sibling_device_is_read_through_sensor_service_unaffected(
    tmp_path: Path,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    """A real-shaped scenario: a smart plug is a `switch` Device plus a
    sibling `sensor` Device (device_class="power") -- verifies the
    sibling sensor continues to normalize through the existing,
    unmodified SensorService, untouched by anything in this module."""
    from jarvis.core.plugins.permissions import PermissionModel
    from jarvis.services.sensor_service import SENSOR_PRINCIPAL, SensorService
    from jarvis.services.sensor_service import SMART_HOME_SCOPE as SENSOR_SCOPE

    await connectivity.connect("home_assistant")
    home = await smart_home.create_home("Primary Residence")
    await smart_home.register_discovered_device(
        home.id,
        "Living Room Plug",
        device_type="switch",
        external_id="switch.living_room_plug",
        metadata={"connector_type": "home_assistant"},
    )
    power_sensor = await smart_home.register_discovered_device(
        home.id,
        "Living Room Plug Power",
        device_type="sensor",
        external_id="sensor.living_room_plug_power",
        metadata={"connector_type": "home_assistant", "domain": "sensor", "device_class": "power"},
    )
    fake_connector.states["sensor.living_room_plug_power"] = DeviceState(
        external_id="sensor.living_room_plug_power",
        status="42.3",
        attributes={"unit_of_measurement": "W"},
    )

    sensor_permissions = PermissionModel(
        EventBus(), store_path=tmp_path / "sensor_permissions.json"
    )
    sensor_service = SensorService(
        smart_home=smart_home, connectivity=connectivity, permissions=sensor_permissions
    )
    await sensor_permissions.grant(SENSOR_PRINCIPAL, SENSOR_SCOPE)

    reading = await sensor_service.get_sensor_state(power_sensor.id)

    assert reading["kind"] == "numeric"
    assert reading["value"] == 42.3
    assert reading["unit"] == "W"
