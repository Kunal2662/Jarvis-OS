"""ThermostatService tests -- Milestone 12 Appliance Control (Climate /
Thermostat Slice).

Real (temp-file) SQLite ``SmartHomeService`` and a real
``PermissionModel`` throughout, matching
``test_m12_appliance_service.py``'s own pattern -- only the connector
itself is faked (``FakeDeviceConnector``).
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
from jarvis.services.thermostat_service import (
    SMART_HOME_SCOPE,
    THERMOSTAT_PRINCIPAL,
    ThermostatService,
    _translate_home_assistant,
    _translate_mqtt,
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
) -> ThermostatService:
    return ThermostatService(
        smart_home=smart_home, connectivity=connectivity, permissions=permissions
    )


async def _grant(permissions: PermissionModel) -> None:
    await permissions.grant(THERMOSTAT_PRINCIPAL, SMART_HOME_SCOPE)


async def _home_and_thermostat(
    smart_home: SmartHomeService,
    *,
    external_id: str = _EXTERNAL_ID,
    connector_type: str = "home_assistant",
):
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Living Room AC",
        device_type="thermostat",
        external_id=external_id,
        metadata={"connector_type": connector_type, "domain": "climate"},
    )
    return home, device


def _climate_state(
    *,
    status: str = "cool",
    current: float | None = 24.5,
    target: float | None = 22.0,
    modes: list[str] | None = None,
    min_temp: float | None = None,
    max_temp: float | None = None,
) -> DeviceState:
    attributes: dict = {}
    if current is not None:
        attributes["current_temperature"] = current
    if target is not None:
        attributes["temperature"] = target
    if modes is not None:
        attributes["hvac_modes"] = modes
    if min_temp is not None:
        attributes["min_temp"] = min_temp
    if max_temp is not None:
        attributes["max_temp"] = max_temp
    return DeviceState(external_id=_EXTERNAL_ID, status=status, attributes=attributes)


# --- Reads are ungated (Logic Contract §10) --------------------------------------


@pytest.mark.asyncio
async def test_list_thermostats_is_ungated(
    service: ThermostatService, smart_home: SmartHomeService
) -> None:
    await _home_and_thermostat(smart_home)
    rows = await service.list_thermostats()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_get_thermostat_state_is_ungated(
    service: ThermostatService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_thermostat(smart_home)
    state = await service.get_thermostat_state(device.id)
    assert state["id"] == device.id


@pytest.mark.asyncio
async def test_permission_declared_pending_at_construction(permissions: PermissionModel) -> None:
    assert permissions.state(THERMOSTAT_PRINCIPAL, SMART_HOME_SCOPE).value == "pending"


@pytest.mark.asyncio
async def test_mutation_denied_without_grant(
    service: ThermostatService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_thermostat(smart_home)
    with pytest.raises(ServiceError, match="permission"):
        await service.set_thermostat_state(device.id, temperature=21.0)


# --- Device-type safety ----------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "device_type", ["light", "lock", "sensor", "switch", "appliance", "camera", "other"]
)
async def test_rejects_every_foreign_device_type(
    service: ThermostatService,
    smart_home: SmartHomeService,
    permissions: PermissionModel,
    device_type: str,
) -> None:
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id, "Not A Thermostat", device_type=device_type, external_id=f"{device_type}.x"
    )

    with pytest.raises(ServiceError, match="not a thermostat"):
        await service.get_thermostat_state(device.id)
    with pytest.raises(ServiceError, match="not a thermostat"):
        await service.set_thermostat_state(device.id, temperature=21.0)


@pytest.mark.asyncio
async def test_unknown_device_raises(
    service: ThermostatService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    with pytest.raises(ServiceError):
        await service.get_thermostat_state("no-such-device")


# --- State normalization ----------------------------------------------------------


@pytest.mark.asyncio
async def test_full_state_normalization(
    service: ThermostatService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_thermostat(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _climate_state(
        status="cool",
        current=24.5,
        target=22.0,
        modes=["off", "cool", "heat"],
        min_temp=16.0,
        max_temp=30.0,
    )

    state = await service.get_thermostat_state(device.id)

    assert state["available"] is True
    assert state["current_temperature"] == 24.5
    assert state["target_temperature"] == 22.0
    assert state["hvac_mode"] == "cool"
    assert state["hvac_modes"] == ["off", "cool", "heat"]
    assert state["min_temp"] == 16.0
    assert state["max_temp"] == 30.0


@pytest.mark.asyncio
async def test_ha_entity_state_is_the_hvac_mode(
    service: ThermostatService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    """For an HA climate entity the entity's own state string *is* the
    HVAC mode -- not an on/off value like every prior M12 module."""
    await connectivity.connect("home_assistant")
    _, device = await _home_and_thermostat(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _climate_state(status="heat_cool")

    state = await service.get_thermostat_state(device.id)

    assert state["hvac_mode"] == "heat_cool"


@pytest.mark.asyncio
@pytest.mark.parametrize("offline_status", ["offline", "unavailable", "OFFLINE", "Unavailable"])
async def test_unavailable_device_reports_none_mode_not_the_status_string(
    service: ThermostatService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
    offline_status: str,
) -> None:
    """The thermostat-specific trap: because state *is* the mode, an
    unavailable device must never record "unavailable" as its
    hvac_mode (Logic Contract §9)."""
    await connectivity.connect("home_assistant")
    _, device = await _home_and_thermostat(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _climate_state(status=offline_status)

    state = await service.get_thermostat_state(device.id)

    assert state["available"] is False
    assert state["hvac_mode"] is None
    assert state["current_temperature"] is None
    assert state["target_temperature"] is None


@pytest.mark.asyncio
async def test_capability_fields_survive_unavailability(
    service: ThermostatService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    """A device's declared range/modes remain true regardless of
    reachability, unlike its live readings."""
    await connectivity.connect("home_assistant")
    _, device = await _home_and_thermostat(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _climate_state(
        status="unavailable", modes=["off", "heat"], min_temp=7.0, max_temp=35.0
    )

    state = await service.get_thermostat_state(device.id)

    assert state["available"] is False
    assert state["hvac_modes"] == ["off", "heat"]
    assert state["min_temp"] == 7.0
    assert state["max_temp"] == 35.0


@pytest.mark.asyncio
async def test_connector_unreachable_falls_back_without_raising(
    service: ThermostatService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_thermostat(smart_home)

    state = await service.get_thermostat_state(device.id)

    assert state["available"] is False
    assert state["hvac_mode"] is None
    assert state["hvac_modes"] == []


@pytest.mark.asyncio
async def test_missing_attributes_report_none_not_zero(
    service: ThermostatService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_thermostat(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _climate_state(current=None, target=None)

    state = await service.get_thermostat_state(device.id)

    assert state["current_temperature"] is None
    assert state["target_temperature"] is None
    assert state["hvac_modes"] == []
    assert state["min_temp"] is None


@pytest.mark.asyncio
async def test_malformed_temperature_reports_none_not_zero(
    service: ThermostatService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_thermostat(smart_home)
    fake_connector.states[_EXTERNAL_ID] = DeviceState(
        external_id=_EXTERNAL_ID,
        status="cool",
        attributes={"current_temperature": "not-a-number", "temperature": None},
    )

    state = await service.get_thermostat_state(device.id)

    assert state["current_temperature"] is None
    assert state["target_temperature"] is None


@pytest.mark.asyncio
async def test_malformed_hvac_modes_reports_empty_list(
    service: ThermostatService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_thermostat(smart_home)
    fake_connector.states[_EXTERNAL_ID] = DeviceState(
        external_id=_EXTERNAL_ID, status="cool", attributes={"hvac_modes": "cool"}
    )

    state = await service.get_thermostat_state(device.id)

    assert state["hvac_modes"] == []


@pytest.mark.asyncio
async def test_list_is_db_only_with_no_live_read(
    service: ThermostatService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _home_and_thermostat(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _climate_state()

    rows = await service.list_thermostats()

    assert rows[0]["available"] is False
    assert rows[0]["hvac_mode"] is None
    assert rows[0]["current_temperature"] is None


# --- Mutations --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_temperature_only_mutation_sends_one_call(
    service: ThermostatService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_thermostat(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _climate_state()

    result = await service.set_thermostat_state(device.id, temperature=21.5)

    assert result["success"] is True
    assert fake_connector.sent_commands == [
        (_EXTERNAL_ID, "set_temperature", {"temperature": 21.5})
    ]


@pytest.mark.asyncio
async def test_mode_only_mutation_sends_one_call(
    service: ThermostatService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_thermostat(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _climate_state()

    result = await service.set_thermostat_state(device.id, hvac_mode="heat")

    assert result["success"] is True
    assert fake_connector.sent_commands == [(_EXTERNAL_ID, "set_hvac_mode", {"hvac_mode": "heat"})]


@pytest.mark.asyncio
async def test_combined_mutation_sends_mode_first_then_temperature(
    service: ThermostatService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    """HA models climate as two services, so a combined update is two
    sequential calls -- mode first so the setpoint applies to the
    intended mode (Logic Contract §8b fallback)."""
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_thermostat(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _climate_state()

    result = await service.set_thermostat_state(device.id, temperature=20.0, hvac_mode="cool")

    assert result["success"] is True
    assert fake_connector.sent_commands == [
        (_EXTERNAL_ID, "set_hvac_mode", {"hvac_mode": "cool"}),
        (_EXTERNAL_ID, "set_temperature", {"temperature": 20.0}),
    ]


@pytest.mark.asyncio
async def test_empty_mutation_rejected(
    service: ThermostatService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    _, device = await _home_and_thermostat(smart_home)
    with pytest.raises(ServiceError, match="at least one"):
        await service.set_thermostat_state(device.id)


@pytest.mark.asyncio
async def test_partial_failure_reported_honestly(
    service: ThermostatService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    """Mode applied, temperature rejected -> success=False naming what
    already applied. Never a full success (Logic Contract §11)."""
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_thermostat(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _climate_state()
    fake_connector.next_command_succeeds = False

    result = await service.set_thermostat_state(device.id, temperature=20.0, hvac_mode="cool")

    assert result["success"] is False


@pytest.mark.asyncio
async def test_command_failure_surfaced_not_raised(
    service: ThermostatService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_thermostat(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _climate_state()
    fake_connector.next_command_succeeds = False

    result = await service.set_thermostat_state(device.id, temperature=21.0)

    assert result["success"] is False
    assert "fake rejection" in result["detail"]


@pytest.mark.asyncio
async def test_no_recorded_connector_raises(
    service: ThermostatService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id, "Orphan", device_type="thermostat", external_id="climate.orphan"
    )
    with pytest.raises(ServiceError, match="no recorded connector"):
        await service.set_thermostat_state(device.id, temperature=21.0)


# --- Temperature validation --------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["21", None, [21], {}])
async def test_non_numeric_temperature_rejected(
    service: ThermostatService,
    smart_home: SmartHomeService,
    permissions: PermissionModel,
    bad,
) -> None:
    await _grant(permissions)
    _, device = await _home_and_thermostat(smart_home)
    # `None` means "not supplied", so pair it with a mode to reach validation.
    if bad is None:
        return
    with pytest.raises(ServiceError, match="temperature must be a number"):
        await service.set_thermostat_state(device.id, temperature=bad)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [True, False])
async def test_bool_temperature_rejected(
    service: ThermostatService,
    smart_home: SmartHomeService,
    permissions: PermissionModel,
    bad: bool,
) -> None:
    """`bool` is an `int` subclass -- a bare float() would silently turn
    True into 1.0."""
    await _grant(permissions)
    _, device = await _home_and_thermostat(smart_home)
    with pytest.raises(ServiceError, match="temperature must be a number"):
        await service.set_thermostat_state(device.id, temperature=bad)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
async def test_non_finite_temperature_rejected(
    service: ThermostatService,
    smart_home: SmartHomeService,
    permissions: PermissionModel,
    bad: float,
) -> None:
    await _grant(permissions)
    _, device = await _home_and_thermostat(smart_home)
    with pytest.raises(ServiceError, match="finite"):
        await service.set_thermostat_state(device.id, temperature=bad)


@pytest.mark.asyncio
async def test_integer_temperature_accepted(
    service: ThermostatService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_thermostat(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _climate_state()

    result = await service.set_thermostat_state(device.id, temperature=21)

    assert result["success"] is True
    assert fake_connector.sent_commands[0][2] == {"temperature": 21.0}


# --- Device-reported bounds (and the absence of invented ones) ----------------------


@pytest.mark.asyncio
async def test_temperature_below_device_reported_minimum_rejected(
    service: ThermostatService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_thermostat(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _climate_state(min_temp=16.0, max_temp=30.0)

    with pytest.raises(ServiceError, match="below this device's reported minimum"):
        await service.set_thermostat_state(device.id, temperature=5.0)


@pytest.mark.asyncio
async def test_temperature_above_device_reported_maximum_rejected(
    service: ThermostatService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_thermostat(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _climate_state(min_temp=16.0, max_temp=30.0)

    with pytest.raises(ServiceError, match="above this device's reported maximum"):
        await service.set_thermostat_state(device.id, temperature=99.0)


@pytest.mark.asyncio
@pytest.mark.parametrize("extreme", [-40.0, 250.0])
async def test_no_bound_enforced_when_device_reports_none(
    service: ThermostatService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
    extreme: float,
) -> None:
    """This module invents NO safety limits -- a device that declares no
    min/max gets whatever the caller asked for (Logic Contract §7)."""
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_thermostat(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _climate_state(min_temp=None, max_temp=None)

    result = await service.set_thermostat_state(device.id, temperature=extreme)

    assert result["success"] is True


@pytest.mark.asyncio
async def test_boundary_values_are_inclusive(
    service: ThermostatService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_thermostat(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _climate_state(min_temp=16.0, max_temp=30.0)

    assert (await service.set_thermostat_state(device.id, temperature=16.0))["success"] is True
    assert (await service.set_thermostat_state(device.id, temperature=30.0))["success"] is True


# --- HVAC mode validation -----------------------------------------------------------


@pytest.mark.asyncio
async def test_mode_validated_against_device_reported_modes(
    service: ThermostatService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_thermostat(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _climate_state(modes=["off", "cool"])

    with pytest.raises(ServiceError, match="not supported by this device"):
        await service.set_thermostat_state(device.id, hvac_mode="heat")


@pytest.mark.asyncio
async def test_mode_permissive_when_device_reports_no_modes(
    service: ThermostatService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    """No fixed HVAC enum is invented -- rejecting a real device over a
    vocabulary gap is the worse failure (Logic Contract §6)."""
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_thermostat(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _climate_state(modes=None)

    result = await service.set_thermostat_state(device.id, hvac_mode="some_vendor_mode")

    assert result["success"] is True
    assert fake_connector.sent_commands[0][2] == {"hvac_mode": "some_vendor_mode"}


@pytest.mark.asyncio
async def test_mode_case_is_normalized(
    service: ThermostatService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_thermostat(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _climate_state(modes=["off", "cool"])

    result = await service.set_thermostat_state(device.id, hvac_mode="  COOL  ")

    assert result["success"] is True
    assert fake_connector.sent_commands[0][2] == {"hvac_mode": "cool"}


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["", "   ", 5, True])
async def test_invalid_mode_rejected(
    service: ThermostatService,
    smart_home: SmartHomeService,
    permissions: PermissionModel,
    bad,
) -> None:
    await _grant(permissions)
    _, device = await _home_and_thermostat(smart_home)
    with pytest.raises(ServiceError, match="hvac_mode must be a non-empty string"):
        await service.set_thermostat_state(device.id, hvac_mode=bad)


# --- Translators (unit-level, both connectors) --------------------------------------


def test_ha_translator_temperature_only() -> None:
    assert _translate_home_assistant(temperature=21.0, hvac_mode=None) == [
        ("set_temperature", {"temperature": 21.0})
    ]


def test_ha_translator_mode_only() -> None:
    assert _translate_home_assistant(temperature=None, hvac_mode="cool") == [
        ("set_hvac_mode", {"hvac_mode": "cool"})
    ]


def test_ha_translator_combined_is_two_calls_mode_first() -> None:
    assert _translate_home_assistant(temperature=21.0, hvac_mode="cool") == [
        ("set_hvac_mode", {"hvac_mode": "cool"}),
        ("set_temperature", {"temperature": 21.0}),
    ]


def test_mqtt_translator_is_always_one_merged_call() -> None:
    """MQTT deliberately does NOT copy HA's two-service split -- its
    envelope has no such constraint (Logic Contract §8c)."""
    assert _translate_mqtt(temperature=21.0, hvac_mode=None) == [
        ("set_state", {"temperature": 21.0})
    ]
    assert _translate_mqtt(temperature=None, hvac_mode="cool") == [
        ("set_state", {"hvac_mode": "cool"})
    ]
    assert _translate_mqtt(temperature=21.0, hvac_mode="cool") == [
        ("set_state", {"temperature": 21.0, "hvac_mode": "cool"})
    ]


@pytest.mark.asyncio
async def test_mqtt_device_uses_merged_set_state(
    smart_home: SmartHomeService,
    permissions: PermissionModel,
    bus: EventBus,
) -> None:
    """End-to-end over an mqtt-typed device: one merged call, not two."""
    mqtt_connector = FakeDeviceConnector()
    mqtt_connector.connector_type = "mqtt"
    reg = ConnectorFactoryRegistry()
    reg.register("mqtt", lambda config: mqtt_connector)
    conn = ConnectivityService(registry=reg, smart_home=smart_home, event_bus=bus)
    svc = ThermostatService(smart_home=smart_home, connectivity=conn, permissions=permissions)
    await conn.connect("mqtt")
    await permissions.grant(THERMOSTAT_PRINCIPAL, SMART_HOME_SCOPE)
    _, device = await _home_and_thermostat(smart_home, connector_type="mqtt")
    mqtt_connector.states[_EXTERNAL_ID] = _climate_state()

    result = await svc.set_thermostat_state(device.id, temperature=20.0, hvac_mode="cool")

    assert result["success"] is True
    assert mqtt_connector.sent_commands == [
        (_EXTERNAL_ID, "set_state", {"temperature": 20.0, "hvac_mode": "cool"})
    ]


# --- Cross-cutting invariants --------------------------------------------------------


def test_service_does_not_import_connectors_directly() -> None:
    """Docstrings may *discuss* the connectors (they explain why zero
    connector changes were needed) -- only an actual import statement
    would be the real violation this test guards against."""
    import inspect

    from jarvis.services import thermostat_service

    import_lines = [
        line
        for line in inspect.getsource(thermostat_service).splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    joined = "\n".join(import_lines)
    assert "HomeAssistantConnector" not in joined
    assert "MqttConnector" not in joined
    assert "gmqtt" not in joined
    assert "connectors" not in joined.lower()


def test_service_publishes_no_events() -> None:
    import inspect

    from jarvis.services import thermostat_service

    source = inspect.getsource(thermostat_service)
    assert "event_bus" not in source
    assert "EventBus" not in source


def test_appliance_service_was_not_extended() -> None:
    """This slice is its own device_type and its own service --
    ApplianceService must carry no thermostat/climate handling."""
    import inspect

    from jarvis.services import appliance_service

    source = inspect.getsource(appliance_service).lower()
    assert "thermostat" not in source
    assert "hvac" not in source
