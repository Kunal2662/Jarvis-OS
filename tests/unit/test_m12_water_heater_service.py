"""WaterHeaterService tests -- Milestone 12 Appliance Control (Water
Heater Core Slice).

Real (temp-file) SQLite ``SmartHomeService`` and a real
``PermissionModel`` throughout, matching
``test_m12_media_player_service.py``'s own pattern -- only the
connector itself is faked (``FakeDeviceConnector``).
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
from jarvis.services.water_heater_service import (
    SMART_HOME_SCOPE,
    WATER_HEATER_PRINCIPAL,
    WaterHeaterService,
    _translate_state_home_assistant,
    _translate_state_mqtt,
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
) -> WaterHeaterService:
    return WaterHeaterService(
        smart_home=smart_home, connectivity=connectivity, permissions=permissions
    )


async def _grant(permissions: PermissionModel) -> None:
    await permissions.grant(WATER_HEATER_PRINCIPAL, SMART_HOME_SCOPE)


async def _home_and_water_heater(
    smart_home: SmartHomeService,
    *,
    external_id: str = _EXTERNAL_ID,
    connector_type: str = "home_assistant",
    metadata_key: str = "domain",
):
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Basement Water Heater",
        device_type="appliance",
        external_id=external_id,
        metadata={"connector_type": connector_type, metadata_key: "water_heater"},
    )
    return home, device


def _state(
    *,
    status: str = "eco",
    attributes: dict | None = None,
    external_id: str = _EXTERNAL_ID,
) -> DeviceState:
    return DeviceState(external_id=external_id, status=status, attributes=attributes or {})


# --- Domain discrimination (Logic Contract §2) --------------------------------------


@pytest.mark.asyncio
async def test_domain_key_resolves_via_domain(
    service: WaterHeaterService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_water_heater(smart_home, metadata_key="domain")
    state = await service.get_water_heater_state(device.id)
    assert state["id"] == device.id


@pytest.mark.asyncio
async def test_domain_key_falls_back_to_component(
    service: WaterHeaterService, smart_home: SmartHomeService
) -> None:
    """MQTT HA-Discovery-sourced devices carry metadata["component"],
    not metadata["domain"] -- this must still resolve correctly
    (Logic Contract §2)."""
    _, device = await _home_and_water_heater(
        smart_home, connector_type="mqtt", metadata_key="component"
    )
    state = await service.get_water_heater_state(device.id)
    assert state["id"] == device.id


@pytest.mark.asyncio
async def test_domain_preferred_over_component_when_both_present(
    service: WaterHeaterService, smart_home: SmartHomeService
) -> None:
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Tank",
        device_type="appliance",
        external_id=_EXTERNAL_ID,
        metadata={"domain": "water_heater", "component": "switch"},
    )
    state = await service.get_water_heater_state(device.id)
    assert state["id"] == device.id


@pytest.mark.asyncio
async def test_missing_domain_and_component_is_rejected(
    service: WaterHeaterService, smart_home: SmartHomeService
) -> None:
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id, "Mystery Appliance", device_type="appliance", external_id="appliance.mystery"
    )
    with pytest.raises(ServiceError, match="not a water heater"):
        await service.get_water_heater_state(device.id)


@pytest.mark.asyncio
async def test_wrong_component_is_rejected(
    service: WaterHeaterService, smart_home: SmartHomeService
) -> None:
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Vacuum",
        device_type="appliance",
        external_id="vacuum.x",
        metadata={"component": "vacuum"},
    )
    with pytest.raises(ServiceError, match="not a water heater"):
        await service.get_water_heater_state(device.id)


# --- Device-type safety ----------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "device_type,metadata",
    [
        ("light", {}),
        ("lock", {}),
        ("sensor", {}),
        ("switch", {}),
        ("thermostat", {}),
        ("camera", {}),
        ("other", {}),
        ("appliance", {"domain": "fan"}),
        ("appliance", {"domain": "cover"}),
        ("appliance", {"domain": "vacuum"}),
        ("appliance", {"domain": "humidifier"}),
        ("appliance", {"domain": "media_player"}),
    ],
)
async def test_rejects_every_foreign_type_and_domain(
    service: WaterHeaterService,
    smart_home: SmartHomeService,
    permissions: PermissionModel,
    device_type: str,
    metadata: dict,
) -> None:
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id, "Not A Water Heater", device_type=device_type, external_id="x.y", metadata=metadata
    )
    with pytest.raises(ServiceError, match="not a water heater"):
        await service.get_water_heater_state(device.id)
    with pytest.raises(ServiceError, match="not a water heater"):
        await service.set_water_heater_state(device.id, on=True)


@pytest.mark.asyncio
async def test_unknown_device_raises(
    service: WaterHeaterService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    with pytest.raises(ServiceError):
        await service.get_water_heater_state("no-such-device")


# --- Reads are ungated ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_reads_are_ungated(service: WaterHeaterService, smart_home: SmartHomeService) -> None:
    await _home_and_water_heater(smart_home)
    rows = await service.list_water_heaters()
    assert len(rows) == 1
    state = await service.get_water_heater_state(rows[0]["id"])
    assert state["id"] == rows[0]["id"]


@pytest.mark.asyncio
async def test_permission_declared_pending_at_construction(permissions: PermissionModel) -> None:
    assert permissions.state(WATER_HEATER_PRINCIPAL, SMART_HOME_SCOPE).value == "pending"


@pytest.mark.asyncio
async def test_state_mutation_denied_without_grant(
    service: WaterHeaterService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_water_heater(smart_home)
    with pytest.raises(ServiceError, match="permission"):
        await service.set_water_heater_state(device.id, temperature=55.0)


# --- State normalization ----------------------------------------------------------


@pytest.mark.asyncio
async def test_full_state_normalization(
    service: WaterHeaterService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_water_heater(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(
        status="eco",
        attributes={
            "current_temperature": 48.0,
            "temperature": 55.0,
            "operation_list": ["eco", "electric", "gas", "heat_pump", "high_demand"],
            "min_temp": 43.0,
            "max_temp": 60.0,
        },
    )

    state = await service.get_water_heater_state(device.id)

    assert state["available"] is True
    assert state["state"] == "eco"
    assert state["operation_mode"] == "eco"
    assert state["is_on"] is None  # "eco" isn't a recognized on/off token
    assert state["current_temperature"] == 48.0
    assert state["target_temperature"] == 55.0
    assert state["operation_list"] == ["eco", "electric", "gas", "heat_pump", "high_demand"]
    assert state["min_temp"] == 43.0
    assert state["max_temp"] == 60.0


@pytest.mark.asyncio
@pytest.mark.parametrize("raw_status,expected_is_on", [("on", True), ("off", False)])
async def test_plain_on_off_state_is_inferred(
    service: WaterHeaterService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
    raw_status: str,
    expected_is_on: bool,
) -> None:
    """A device that only supports ON_OFF (no operation modes) reports
    a plain on/off entity state (Logic Contract §7)."""
    await connectivity.connect("home_assistant")
    _, device = await _home_and_water_heater(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(status=raw_status)

    state = await service.get_water_heater_state(device.id)

    assert state["state"] == raw_status
    assert state["is_on"] is expected_is_on
    assert state["operation_mode"] == raw_status


@pytest.mark.asyncio
async def test_unknown_state_string_passes_through(
    service: WaterHeaterService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    """No closed enum -- an unrecognized state string is not rejected
    or coerced (Logic Contract §4/§7)."""
    await connectivity.connect("home_assistant")
    _, device = await _home_and_water_heater(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(status="some_vendor_specific_mode")

    state = await service.get_water_heater_state(device.id)

    assert state["state"] == "some_vendor_specific_mode"
    assert state["operation_mode"] == "some_vendor_specific_mode"
    assert state["is_on"] is None


@pytest.mark.asyncio
async def test_unavailable_reports_none_state_not_the_status_string(
    service: WaterHeaterService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_water_heater(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(status="unavailable")

    state = await service.get_water_heater_state(device.id)

    assert state["available"] is False
    assert state["state"] is None
    assert state["is_on"] is None
    assert state["operation_mode"] is None
    assert state["current_temperature"] is None
    assert state["target_temperature"] is None


@pytest.mark.asyncio
async def test_capability_fields_survive_unavailability(
    service: WaterHeaterService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_water_heater(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(
        status="unavailable",
        attributes={"operation_list": ["eco", "electric"], "min_temp": 43.0, "max_temp": 60.0},
    )

    state = await service.get_water_heater_state(device.id)

    assert state["available"] is False
    assert state["operation_list"] == ["eco", "electric"]
    assert state["min_temp"] == 43.0
    assert state["max_temp"] == 60.0


@pytest.mark.asyncio
async def test_connector_unreachable_falls_back_without_raising(
    service: WaterHeaterService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_water_heater(smart_home)
    state = await service.get_water_heater_state(device.id)
    assert state["available"] is False
    assert state["state"] is None


@pytest.mark.asyncio
async def test_missing_attributes_report_none_not_zero(
    service: WaterHeaterService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_water_heater(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(status="eco")

    state = await service.get_water_heater_state(device.id)

    assert state["current_temperature"] is None
    assert state["target_temperature"] is None
    assert state["operation_list"] == []
    assert state["min_temp"] is None
    assert state["max_temp"] is None


@pytest.mark.asyncio
async def test_malformed_temperature_reports_none_not_zero(
    service: WaterHeaterService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_water_heater(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(status="eco", attributes={"temperature": "n/a"})

    state = await service.get_water_heater_state(device.id)

    assert state["target_temperature"] is None


@pytest.mark.asyncio
async def test_malformed_operation_list_reports_empty_list(
    service: WaterHeaterService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_water_heater(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(status="eco", attributes={"operation_list": "eco"})

    state = await service.get_water_heater_state(device.id)

    assert state["operation_list"] == []


@pytest.mark.asyncio
async def test_list_is_db_only_no_live_read(
    service: WaterHeaterService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _home_and_water_heater(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(status="eco")

    rows = await service.list_water_heaters()

    assert rows[0]["available"] is False
    assert rows[0]["state"] is None


# --- Merged state mutation --------------------------------------------------------


@pytest.mark.asyncio
async def test_temperature_only_mutation(
    service: WaterHeaterService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_water_heater(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(status="eco")

    result = await service.set_water_heater_state(device.id, temperature=55.0)

    assert result["success"] is True
    assert fake_connector.sent_commands == [
        (_EXTERNAL_ID, "set_temperature", {"temperature": 55.0})
    ]


@pytest.mark.asyncio
async def test_operation_mode_only_mutation(
    service: WaterHeaterService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_water_heater(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(
        status="eco", attributes={"operation_list": ["eco", "electric"]}
    )

    result = await service.set_water_heater_state(device.id, operation_mode="electric")

    assert result["success"] is True
    assert fake_connector.sent_commands == [
        (_EXTERNAL_ID, "set_operation_mode", {"operation_mode": "electric"})
    ]


@pytest.mark.asyncio
async def test_on_only_mutation_true(
    service: WaterHeaterService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_water_heater(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(status="off")

    result = await service.set_water_heater_state(device.id, on=True)

    assert result["success"] is True
    assert fake_connector.sent_commands == [(_EXTERNAL_ID, "turn_on", {})]


@pytest.mark.asyncio
async def test_on_only_mutation_false(
    service: WaterHeaterService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_water_heater(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(status="eco")

    result = await service.set_water_heater_state(device.id, on=False)

    assert result["success"] is True
    assert fake_connector.sent_commands == [(_EXTERNAL_ID, "turn_off", {})]


@pytest.mark.asyncio
async def test_all_three_combined_ordering_on_mode_temperature(
    service: WaterHeaterService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_water_heater(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(
        status="eco", attributes={"operation_list": ["eco", "electric"]}
    )

    result = await service.set_water_heater_state(
        device.id, on=True, operation_mode="electric", temperature=55.0
    )

    assert result["success"] is True
    assert fake_connector.sent_commands == [
        (_EXTERNAL_ID, "turn_on", {}),
        (_EXTERNAL_ID, "set_operation_mode", {"operation_mode": "electric"}),
        (_EXTERNAL_ID, "set_temperature", {"temperature": 55.0}),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs,expected_commands",
    [
        ({"on": True, "temperature": 55.0}, ["turn_on", "set_temperature"]),
        ({"operation_mode": "eco", "temperature": 55.0}, ["set_operation_mode", "set_temperature"]),
        ({"on": False, "operation_mode": "eco"}, ["turn_off", "set_operation_mode"]),
    ],
)
async def test_pairwise_combinations_preserve_ordering(
    service: WaterHeaterService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
    kwargs: dict,
    expected_commands: list[str],
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_water_heater(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(
        status="eco", attributes={"operation_list": ["eco", "electric"]}
    )

    result = await service.set_water_heater_state(device.id, **kwargs)

    assert result["success"] is True
    assert [c[1] for c in fake_connector.sent_commands] == expected_commands


@pytest.mark.asyncio
async def test_empty_mutation_rejected(
    service: WaterHeaterService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    _, device = await _home_and_water_heater(smart_home)
    with pytest.raises(ServiceError, match="at least one"):
        await service.set_water_heater_state(device.id)


@pytest.mark.asyncio
async def test_first_operation_fails_reports_no_applied(
    service: WaterHeaterService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_water_heater(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(status="off")
    fake_connector.next_command_succeeds = False

    result = await service.set_water_heater_state(device.id, on=True, temperature=55.0)

    assert result["success"] is False
    assert "already applied" not in result["detail"]


@pytest.mark.asyncio
async def test_second_operation_fails_reports_first_applied(
    service: WaterHeaterService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_water_heater(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(status="off")

    original_send = fake_connector.send_command
    call_count = {"n": 0}

    async def flaky_send(external_id, command, payload):
        call_count["n"] += 1
        fake_connector.next_command_succeeds = call_count["n"] != 2
        return await original_send(external_id, command, payload)

    fake_connector.send_command = flaky_send  # type: ignore[method-assign]

    result = await service.set_water_heater_state(device.id, on=True, temperature=55.0)

    assert result["success"] is False
    assert "turn_on" in result["detail"]
    assert "already applied" in result["detail"]


@pytest.mark.asyncio
async def test_third_operation_fails_reports_first_two_applied(
    service: WaterHeaterService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_water_heater(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(
        status="off", attributes={"operation_list": ["eco"]}
    )

    original_send = fake_connector.send_command
    call_count = {"n": 0}

    async def flaky_send(external_id, command, payload):
        call_count["n"] += 1
        fake_connector.next_command_succeeds = call_count["n"] != 3
        return await original_send(external_id, command, payload)

    fake_connector.send_command = flaky_send  # type: ignore[method-assign]

    result = await service.set_water_heater_state(
        device.id, on=True, operation_mode="eco", temperature=55.0
    )

    assert result["success"] is False
    assert "turn_on" in result["detail"]
    assert "set_operation_mode" in result["detail"]
    assert "already applied" in result["detail"]


def test_state_translators_ordering() -> None:
    assert _translate_state_home_assistant(on=True, operation_mode=None, temperature=None) == [
        ("turn_on", {})
    ]
    assert _translate_state_home_assistant(on=False, operation_mode=None, temperature=None) == [
        ("turn_off", {})
    ]
    assert _translate_state_home_assistant(on=None, operation_mode="eco", temperature=None) == [
        ("set_operation_mode", {"operation_mode": "eco"})
    ]
    assert _translate_state_home_assistant(on=None, operation_mode=None, temperature=55.0) == [
        ("set_temperature", {"temperature": 55.0})
    ]
    assert _translate_state_home_assistant(on=True, operation_mode="eco", temperature=55.0) == [
        ("turn_on", {}),
        ("set_operation_mode", {"operation_mode": "eco"}),
        ("set_temperature", {"temperature": 55.0}),
    ]


def test_mqtt_state_translator_is_always_one_merged_call() -> None:
    assert _translate_state_mqtt(on=True, operation_mode=None, temperature=None) == [
        ("set_state", {"on": True})
    ]
    assert _translate_state_mqtt(on=None, operation_mode="eco", temperature=None) == [
        ("set_state", {"operation_mode": "eco"})
    ]
    assert _translate_state_mqtt(on=None, operation_mode=None, temperature=55.0) == [
        ("set_state", {"temperature": 55.0})
    ]
    assert _translate_state_mqtt(on=True, operation_mode="eco", temperature=55.0) == [
        ("set_state", {"on": True, "operation_mode": "eco", "temperature": 55.0})
    ]


@pytest.mark.asyncio
async def test_mqtt_device_uses_merged_vocabulary(
    smart_home: SmartHomeService, permissions: PermissionModel, bus: EventBus
) -> None:
    mqtt_connector = FakeDeviceConnector()
    mqtt_connector.connector_type = "mqtt"
    reg = ConnectorFactoryRegistry()
    reg.register("mqtt", lambda config: mqtt_connector)
    conn = ConnectivityService(registry=reg, smart_home=smart_home, event_bus=bus)
    svc = WaterHeaterService(smart_home=smart_home, connectivity=conn, permissions=permissions)
    await conn.connect("mqtt")
    await permissions.grant(WATER_HEATER_PRINCIPAL, SMART_HOME_SCOPE)
    _, device = await _home_and_water_heater(smart_home, connector_type="mqtt")
    mqtt_connector.states[_EXTERNAL_ID] = _state(status="eco")

    result = await svc.set_water_heater_state(device.id, on=True, temperature=55.0)

    assert result["success"] is True
    assert mqtt_connector.sent_commands == [
        (_EXTERNAL_ID, "set_state", {"on": True, "temperature": 55.0})
    ]


@pytest.mark.asyncio
async def test_no_recorded_connector_raises(
    service: WaterHeaterService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Orphan",
        device_type="appliance",
        external_id="water_heater.orphan",
        metadata={"domain": "water_heater"},
    )
    with pytest.raises(ServiceError, match="no recorded connector"):
        await service.set_water_heater_state(device.id, on=True)


# --- Temperature validation ---------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [43.0, 60.0, 51.5])
async def test_temperature_boundary_and_normal_values_accepted(
    service: WaterHeaterService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
    value: float,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_water_heater(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(
        status="eco", attributes={"min_temp": 43.0, "max_temp": 60.0}
    )

    result = await service.set_water_heater_state(device.id, temperature=value)

    assert result["success"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [True, False])
async def test_bool_temperature_rejected(
    service: WaterHeaterService,
    smart_home: SmartHomeService,
    permissions: PermissionModel,
    bad: bool,
) -> None:
    await _grant(permissions)
    _, device = await _home_and_water_heater(smart_home)
    with pytest.raises(ServiceError, match="temperature must be a number"):
        await service.set_water_heater_state(device.id, temperature=bad)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
async def test_non_finite_temperature_rejected(
    service: WaterHeaterService,
    smart_home: SmartHomeService,
    permissions: PermissionModel,
    bad: float,
) -> None:
    await _grant(permissions)
    _, device = await _home_and_water_heater(smart_home)
    with pytest.raises(ServiceError, match="finite"):
        await service.set_water_heater_state(device.id, temperature=bad)


@pytest.mark.asyncio
async def test_temperature_below_device_minimum_rejected(
    service: WaterHeaterService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_water_heater(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(
        status="eco", attributes={"min_temp": 43.0, "max_temp": 60.0}
    )

    with pytest.raises(ServiceError, match="below this device's reported minimum"):
        await service.set_water_heater_state(device.id, temperature=30.0)


@pytest.mark.asyncio
async def test_temperature_above_device_maximum_rejected(
    service: WaterHeaterService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_water_heater(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(
        status="eco", attributes={"min_temp": 43.0, "max_temp": 60.0}
    )

    with pytest.raises(ServiceError, match="above this device's reported maximum"):
        await service.set_water_heater_state(device.id, temperature=90.0)


@pytest.mark.asyncio
async def test_temperature_permissive_when_device_reports_no_bounds(
    service: WaterHeaterService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    """No safety limit is invented -- a device that reports no
    min_temp/max_temp accepts any finite temperature (Logic Contract
    §5)."""
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_water_heater(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(status="eco")

    result = await service.set_water_heater_state(device.id, temperature=999.0)

    assert result["success"] is True
    assert fake_connector.sent_commands[0][2] == {"temperature": 999.0}


# --- Operation mode validation -------------------------------------------------------


@pytest.mark.asyncio
async def test_operation_mode_validated_against_device_reported_list(
    service: WaterHeaterService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_water_heater(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(
        status="eco", attributes={"operation_list": ["eco", "electric"]}
    )

    with pytest.raises(ServiceError, match="not supported by this device"):
        await service.set_water_heater_state(device.id, operation_mode="gas")


@pytest.mark.asyncio
async def test_operation_mode_permissive_when_device_reports_no_list(
    service: WaterHeaterService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    """No fixed operation-mode enum is invented -- rejecting a real
    device over a vocabulary gap is the worse failure (Logic Contract
    §6)."""
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_water_heater(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(status="eco")

    result = await service.set_water_heater_state(device.id, operation_mode="some_vendor_mode")

    assert result["success"] is True
    assert fake_connector.sent_commands[0][2] == {"operation_mode": "some_vendor_mode"}


@pytest.mark.asyncio
async def test_operation_mode_case_is_normalized_to_lowercase(
    service: WaterHeaterService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_water_heater(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(
        status="eco", attributes={"operation_list": ["eco"]}
    )

    result = await service.set_water_heater_state(device.id, operation_mode="ECO")

    assert result["success"] is True
    assert fake_connector.sent_commands[0][2] == {"operation_mode": "eco"}


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["", "   "])
async def test_empty_operation_mode_rejected(
    service: WaterHeaterService,
    smart_home: SmartHomeService,
    permissions: PermissionModel,
    bad: str,
) -> None:
    await _grant(permissions)
    _, device = await _home_and_water_heater(smart_home)
    with pytest.raises(ServiceError, match="operation_mode must be a non-empty string"):
        await service.set_water_heater_state(device.id, operation_mode=bad)


# --- On/off validation ---------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["true", 1, 0])
async def test_non_bool_on_rejected(
    service: WaterHeaterService,
    smart_home: SmartHomeService,
    permissions: PermissionModel,
    bad,
) -> None:
    await _grant(permissions)
    _, device = await _home_and_water_heater(smart_home)
    with pytest.raises(ServiceError, match="on must be a boolean"):
        await service.set_water_heater_state(device.id, on=bad)


# --- Cross-cutting invariants --------------------------------------------------------


def test_service_does_not_import_connectors_directly() -> None:
    """Docstrings may *discuss* the connectors -- only an actual import
    statement would be the real violation this test guards against."""
    import inspect

    from jarvis.services import water_heater_service

    import_lines = [
        line
        for line in inspect.getsource(water_heater_service).splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    joined = "\n".join(import_lines)
    assert "HomeAssistantConnector" not in joined
    assert "MqttConnector" not in joined
    assert "gmqtt" not in joined
    assert "connectors" not in joined.lower()


def test_service_publishes_no_events() -> None:
    import inspect

    from jarvis.services import water_heater_service

    source = inspect.getsource(water_heater_service)
    assert "event_bus" not in source
    assert "EventBus" not in source


def test_appliance_service_was_not_extended() -> None:
    """This slice is deliberately its own service -- ApplianceService
    must carry no water-heater *implementation* (Logic Contract §3)."""
    import inspect

    from jarvis.services import appliance_service

    source = inspect.getsource(appliance_service)
    for leaked_symbol in (
        "WaterHeaterCommand",
        "_WATER_HEATER_DOMAIN",
        "set_water_heater_state",
        "set_operation_mode",
        "WaterHeaterService",
    ):
        assert leaked_symbol not in source


def test_no_deferred_functionality_exists() -> None:
    """Away/vacation mode, dual setpoint, scheduling, and every other
    deferred item must not exist anywhere in the implementation (Logic
    Contract §16)."""
    import inspect

    from jarvis.services import water_heater_service

    source = inspect.getsource(water_heater_service).lower()
    for deferred_term in (
        "away_mode",
        "vacation",
        "target_temperature_high",
        "target_temperature_low",
        "schedule",
        "leak",
        "notification",
    ):
        assert deferred_term not in source
