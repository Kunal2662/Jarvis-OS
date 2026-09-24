"""SensorService tests -- Milestone 12 Sensors.

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
from jarvis.services.sensor_service import (
    SENSOR_PRINCIPAL,
    SMART_HOME_SCOPE,
    SensorPermissionError,
    SensorService,
)
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
) -> SensorService:
    return SensorService(smart_home=smart_home, connectivity=connectivity, permissions=permissions)


async def _grant(permissions: PermissionModel) -> None:
    await permissions.grant(SENSOR_PRINCIPAL, SMART_HOME_SCOPE)


async def _home_and_sensor(
    smart_home: SmartHomeService,
    *,
    domain: str = "sensor",
    domain_key: str = "domain",
    device_class: str | None = None,
    external_id: str = "sensor.living_room_temp",
    connector_type: str = "home_assistant",
):
    home = await smart_home.create_home("Primary Residence")
    metadata: dict[str, str] = {"connector_type": connector_type, domain_key: domain}
    if device_class is not None:
        metadata["device_class"] = device_class
    device = await smart_home.register_discovered_device(
        home.id,
        "Living Room Temp",
        device_type="sensor",
        external_id=external_id,
        metadata=metadata,
    )
    return home, device


# --- Permission enforcement (privacy decision, §20) -----------------------------


@pytest.mark.asyncio
async def test_list_sensors_denied_by_default(service: SensorService) -> None:
    with pytest.raises(SensorPermissionError, match="permission"):
        await service.list_sensors()


@pytest.mark.asyncio
async def test_get_sensor_state_denied_by_default(
    service: SensorService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_sensor(smart_home)
    with pytest.raises(SensorPermissionError, match="permission"):
        await service.get_sensor_state(device.id)


@pytest.mark.asyncio
async def test_permission_declared_pending_at_construction(permissions: PermissionModel) -> None:
    assert permissions.state(SENSOR_PRINCIPAL, SMART_HOME_SCOPE).value == "pending"


@pytest.mark.asyncio
async def test_reads_succeed_once_granted(
    service: SensorService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    _, device = await _home_and_sensor(smart_home)

    rows = await service.list_sensors()
    assert len(rows) == 1

    state = await service.get_sensor_state(device.id)
    assert state["id"] == device.id


def test_sensor_permission_error_is_a_service_error() -> None:
    assert issubclass(SensorPermissionError, ServiceError)


# --- Validation ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_sensor_state_rejects_non_sensor_device(
    service: SensorService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    switch = await smart_home.register_discovered_device(
        home.id, "Hallway Switch", device_type="switch", external_id="switch.hallway"
    )
    with pytest.raises(ServiceError, match="not a sensor"):
        await service.get_sensor_state(switch.id)


@pytest.mark.asyncio
async def test_get_sensor_state_unknown_device_raises(
    service: SensorService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    with pytest.raises(ServiceError):
        await service.get_sensor_state("no-such-device")


# --- List payload (DB-only) -----------------------------------------------------


@pytest.mark.asyncio
async def test_list_sensors_reports_domain_derived_kind_and_device_class(
    service: SensorService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    await _home_and_sensor(
        smart_home,
        domain="binary_sensor",
        device_class="motion",
        external_id="binary_sensor.hallway_motion",
    )
    await _home_and_sensor(
        smart_home,
        domain="sensor",
        device_class="temperature",
        external_id="sensor.living_room_temp2",
    )

    rows = await service.list_sensors()

    motion_row = next(r for r in rows if r["device_class"] == "motion")
    temp_row = next(r for r in rows if r["device_class"] == "temperature")
    assert motion_row["kind"] == "binary"
    assert temp_row["kind"] == "numeric"
    assert "value" not in motion_row  # list is DB-only -- no live fields at all.


@pytest.mark.asyncio
async def test_list_sensors_does_not_make_a_live_connector_read(
    service: SensorService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    await _home_and_sensor(smart_home)
    fake_connector.states["sensor.living_room_temp"] = DeviceState(
        external_id="sensor.living_room_temp", status="21.5", attributes={}
    )

    rows = await service.list_sensors()

    assert len(rows) == 1
    assert "value" not in rows[0]


# --- Binary normalization --------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        ("motion", "on", "detected"),
        ("motion", "off", "clear"),
        ("door", "on", "open"),
        ("door", "off", "closed"),
        ("window", "on", "open"),
        ("moisture", "on", "detected"),  # water leak -- HA's real device_class name.
        ("smoke", "on", "detected"),
        ("gas", "on", "detected"),
        ("vibration", "on", "detected"),
        ("presence", "on", "occupied"),
        ("presence", "off", "unoccupied"),
        ("occupancy", "on", "occupied"),
        ("occupancy", "off", "unoccupied"),
    ],
)
async def test_binary_sensor_friendly_labels(
    service: SensorService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
    case: tuple[str, str, str],
) -> None:
    device_class, raw_status, expected_label = case
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    external_id = f"binary_sensor.{device_class}_1"
    _, device = await _home_and_sensor(
        smart_home, domain="binary_sensor", device_class=device_class, external_id=external_id
    )
    fake_connector.states[external_id] = DeviceState(
        external_id=external_id, status=raw_status, attributes={}
    )

    state = await service.get_sensor_state(device.id)

    assert state["kind"] == "binary"
    assert state["value"] is (raw_status == "on")
    assert state["state"] == expected_label


@pytest.mark.asyncio
async def test_binary_sensor_unrecognized_device_class_falls_back_to_on_off(
    service: SensorService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    """No fabricated label pair for a device_class the Logic Contract's
    §8 table doesn't name."""
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_sensor(
        smart_home, domain="binary_sensor", device_class="cold", external_id="binary_sensor.cold_1"
    )
    fake_connector.states["binary_sensor.cold_1"] = DeviceState(
        external_id="binary_sensor.cold_1", status="on", attributes={}
    )

    state = await service.get_sensor_state(device.id)

    assert state["state"] == "on"


# --- Numeric normalization -------------------------------------------------------


@pytest.mark.asyncio
async def test_numeric_sensor_reports_value_and_unit(
    service: SensorService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_sensor(smart_home, domain="sensor", device_class="temperature")
    fake_connector.states["sensor.living_room_temp"] = DeviceState(
        external_id="sensor.living_room_temp",
        status="21.5",
        attributes={"unit_of_measurement": "°C"},
    )

    state = await service.get_sensor_state(device.id)

    assert state["kind"] == "numeric"
    assert state["value"] == 21.5
    assert state["unit"] == "°C"
    assert state["state"] == "21.5°C"


@pytest.mark.asyncio
async def test_numeric_sensor_without_unit_formats_bare_value(
    service: SensorService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_sensor(smart_home, domain="sensor", device_class="aqi")
    fake_connector.states["sensor.living_room_temp"] = DeviceState(
        external_id="sensor.living_room_temp", status="42", attributes={}
    )

    state = await service.get_sensor_state(device.id)

    assert state["value"] == 42.0
    assert state["unit"] is None
    assert state["state"] == "42.0"


@pytest.mark.asyncio
async def test_numeric_sensor_malformed_value_reports_none_not_zero(
    service: SensorService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    """A malformed connector state (e.g. HA's own "unknown" sentinel)
    must never silently become 0.0."""
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_sensor(smart_home, domain="sensor", device_class="temperature")
    fake_connector.states["sensor.living_room_temp"] = DeviceState(
        external_id="sensor.living_room_temp", status="unknown", attributes={}
    )

    state = await service.get_sensor_state(device.id)

    assert state["value"] is None
    assert state["state"] is None
    assert state["available"] is True  # "unknown" isn't offline/unavailable -- just unparseable.


# --- Availability + timestamp -----------------------------------------------------


@pytest.mark.asyncio
async def test_get_sensor_state_falls_back_when_connector_unreachable(
    service: SensorService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    _, device = await _home_and_sensor(smart_home)

    state = await service.get_sensor_state(device.id)

    assert state["available"] is False
    assert state["value"] is None
    assert state["timestamp"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("offline_status", ["offline", "unavailable", "OFFLINE", "Unavailable"])
async def test_connector_reported_offline_status_marks_unavailable(
    service: SensorService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
    offline_status: str,
) -> None:
    """A real, connector-sourced 'down' signal (MQTT's own
    `read_state()` already returns `status="offline"`; HA reports
    `"unavailable"`), not the generic 'read raised an exception' case."""
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_sensor(smart_home)
    fake_connector.states["sensor.living_room_temp"] = DeviceState(
        external_id="sensor.living_room_temp", status=offline_status, attributes={}
    )

    state = await service.get_sensor_state(device.id)

    assert state["available"] is False
    assert state["value"] is None


@pytest.mark.asyncio
async def test_timestamp_reported_even_when_unavailable(
    service: SensorService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    """'Last observed at' stays honest even when the device is
    currently offline -- unlike value/state, which are suppressed."""
    from datetime import UTC, datetime

    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_sensor(smart_home)
    observed_at = datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC)
    fake_connector.states["sensor.living_room_temp"] = DeviceState(
        external_id="sensor.living_room_temp",
        status="offline",
        attributes={},
        observed_at=observed_at,
    )

    state = await service.get_sensor_state(device.id)

    assert state["available"] is False
    assert state["timestamp"] == observed_at.isoformat()


@pytest.mark.asyncio
async def test_device_with_no_recorded_domain_defaults_to_numeric(
    service: SensorService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    """A hand-registered sensor with no connector metadata -- 'detect
    at use, not fabricate' default (Logic Contract §4)."""
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id, "Mystery Sensor", device_type="sensor"
    )

    state = await service.get_sensor_state(device.id)

    assert state["kind"] == "numeric"
    assert state["value"] is None


# --- MQTT component fallback (M0-M12 Structured Rework Audit, P1-2) --------------
#
# `MqttConnector._handle_ha_discovery` writes `metadata["component"]`,
# never `metadata["domain"]` -- `_kind_for` must fall back to it, the
# same fallback order every other `device_type="appliance"`/`"other"`
# service already established (and `ApplianceService` restored, P1-1).
# Regression coverage for the fix.


@pytest.mark.asyncio
async def test_component_only_binary_sensor_is_classified_binary(
    service: SensorService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    """`metadata["domain"]` absent, `metadata["component"]` present --
    component fallback resolves the kind (a real, MQTT Discovery-sourced
    binary sensor), and a full read parses/labels it correctly."""
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_sensor(
        smart_home,
        domain="binary_sensor",
        domain_key="component",
        device_class="motion",
        external_id="binary_sensor.mqtt_motion",
    )
    fake_connector.states["binary_sensor.mqtt_motion"] = DeviceState(
        external_id="binary_sensor.mqtt_motion", status="on", attributes={}
    )

    state = await service.get_sensor_state(device.id)

    assert state["kind"] == "binary"
    assert state["value"] is True
    assert state["state"] == "detected"


@pytest.mark.asyncio
async def test_component_only_non_binary_sensor_is_classified_numeric(
    service: SensorService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    """`metadata["domain"]` absent, `metadata["component"]="sensor"` --
    still correctly numeric, not accidentally binary."""
    await _grant(permissions)
    _, device = await _home_and_sensor(smart_home, domain="sensor", domain_key="component")

    state = await service.get_sensor_state(device.id)

    assert state["kind"] == "numeric"


@pytest.mark.asyncio
async def test_domain_takes_precedence_over_component(
    service: SensorService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    """Both keys present -- `domain` wins, mirroring every sibling
    service's own identical precedence rule."""
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Ambiguous Sensor",
        device_type="sensor",
        external_id="sensor.ambiguous",
        metadata={
            "connector_type": "home_assistant",
            "domain": "binary_sensor",
            "component": "sensor",
        },
    )

    state = await service.get_sensor_state(device.id)

    assert state["kind"] == "binary"


@pytest.mark.asyncio
async def test_empty_domain_falls_back_to_component(
    service: SensorService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    """An empty-string `domain` is falsy -- falls through to
    `component`, never treated as "domain present but blank"."""
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Blank Domain Sensor",
        device_type="sensor",
        external_id="sensor.blank_domain",
        metadata={"connector_type": "mqtt", "domain": "", "component": "binary_sensor"},
    )

    state = await service.get_sensor_state(device.id)

    assert state["kind"] == "binary"


@pytest.mark.asyncio
async def test_neither_domain_nor_component_defaults_to_numeric(
    service: SensorService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    """Neither key present -- preserves the existing "detect at use,
    not fabricate" default, never falsely classified binary."""
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "No Metadata Sensor",
        device_type="sensor",
        external_id="sensor.no_metadata",
        metadata={"connector_type": "home_assistant"},
    )

    state = await service.get_sensor_state(device.id)

    assert state["kind"] == "numeric"


@pytest.mark.asyncio
async def test_mqtt_discovered_binary_sensor_reads_correctly_end_to_end(
    smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    """End-to-end: an MQTT-discovered binary sensor (`component`-only
    metadata, no `domain`) now classifies and reads correctly -- the
    exact defect this fix closes."""
    mqtt_connector = FakeDeviceConnector()
    mqtt_connector.connector_type = "mqtt"
    registry = ConnectorFactoryRegistry()
    registry.register("mqtt", lambda config: mqtt_connector)
    mqtt_connectivity = ConnectivityService(registry=registry, smart_home=smart_home)
    mqtt_service = SensorService(
        smart_home=smart_home, connectivity=mqtt_connectivity, permissions=permissions
    )
    await mqtt_connectivity.connect("mqtt")
    await _grant(permissions)
    _, device = await _home_and_sensor(
        smart_home,
        domain="binary_sensor",
        domain_key="component",
        device_class="door",
        connector_type="mqtt",
        external_id="binary_sensor.mqtt_door",
    )
    mqtt_connector.states["binary_sensor.mqtt_door"] = DeviceState(
        external_id="binary_sensor.mqtt_door", status="on", attributes={}
    )

    state = await mqtt_service.get_sensor_state(device.id)

    assert state["kind"] == "binary"
    assert state["state"] == "open"


@pytest.mark.asyncio
async def test_unrelated_component_value_is_not_misclassified_binary(
    service: SensorService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    """A `component` naming an unrelated domain is still correctly
    numeric -- the fallback does not weaken discrimination to a loose
    substring/prefix match."""
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "MQTT Switch-Backed Sensor",
        device_type="sensor",
        external_id="sensor.mqtt_switch_backed",
        metadata={"connector_type": "mqtt", "component": "switch"},
    )

    state = await service.get_sensor_state(device.id)

    assert state["kind"] == "numeric"


# --- Cross-cutting invariant ------------------------------------------------------


def test_domain_layer_has_no_vendor_wire_format_leakage() -> None:
    import inspect

    from jarvis.domain.smart_home import models as domain_models
    from jarvis.services import smart_home_service

    source = inspect.getsource(domain_models) + inspect.getsource(smart_home_service)
    for leaked_term in ("device_class", "unit_of_measurement", "binary_sensor"):
        assert leaked_term not in source
