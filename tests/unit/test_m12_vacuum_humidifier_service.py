"""VacuumHumidifierService tests -- Milestone 12 Appliance Control
(Vacuum + Humidifier Core Slice).

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
from jarvis.services.vacuum_humidifier_service import (
    SMART_HOME_SCOPE,
    VACUUM_HUMIDIFIER_PRINCIPAL,
    VacuumHumidifierService,
    _translate_humidifier_home_assistant,
    _translate_humidifier_mqtt,
    _translate_vacuum_home_assistant,
    _translate_vacuum_mqtt,
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
) -> VacuumHumidifierService:
    return VacuumHumidifierService(
        smart_home=smart_home, connectivity=connectivity, permissions=permissions
    )


async def _grant(permissions: PermissionModel) -> None:
    await permissions.grant(VACUUM_HUMIDIFIER_PRINCIPAL, SMART_HOME_SCOPE)


async def _home_and_vacuum(
    smart_home: SmartHomeService,
    *,
    external_id: str = _VACUUM_EXTERNAL_ID,
    connector_type: str = "home_assistant",
    metadata_key: str = "domain",
):
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Robot Vacuum",
        device_type="appliance",
        external_id=external_id,
        metadata={"connector_type": connector_type, metadata_key: "vacuum"},
    )
    return home, device


async def _home_and_humidifier(
    smart_home: SmartHomeService,
    *,
    external_id: str = _HUMIDIFIER_EXTERNAL_ID,
    connector_type: str = "home_assistant",
    metadata_key: str = "domain",
):
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Bedroom Humidifier",
        device_type="appliance",
        external_id=external_id,
        metadata={"connector_type": connector_type, metadata_key: "humidifier"},
    )
    return home, device


def _state(
    status: str = "on", attributes: dict | None = None, external_id: str = "x"
) -> DeviceState:
    return DeviceState(external_id=external_id, status=status, attributes=attributes or {})


# --- Domain discrimination (Logic Contract §3/§14) ---------------------------------


@pytest.mark.asyncio
async def test_domain_key_resolves_via_domain(
    service: VacuumHumidifierService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    _, device = await _home_and_vacuum(smart_home, metadata_key="domain")
    state = await service.get_vacuum_state(device.id)
    assert state["id"] == device.id


@pytest.mark.asyncio
async def test_domain_key_falls_back_to_component(
    service: VacuumHumidifierService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    """The §3 fix: MQTT HA-Discovery-sourced devices carry
    metadata["component"], not metadata["domain"] -- this must still
    resolve correctly."""
    await _grant(permissions)
    _, device = await _home_and_vacuum(smart_home, connector_type="mqtt", metadata_key="component")
    state = await service.get_vacuum_state(device.id)
    assert state["id"] == device.id


@pytest.mark.asyncio
async def test_neither_domain_nor_component_is_rejected(
    service: VacuumHumidifierService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id, "Mystery Appliance", device_type="appliance", external_id="appliance.mystery"
    )
    with pytest.raises(ServiceError, match="not a vacuum"):
        await service.get_vacuum_state(device.id)


# --- Device-type / domain safety ----------------------------------------------------


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
    ],
)
async def test_vacuum_rejects_every_foreign_type_and_domain(
    service: VacuumHumidifierService,
    smart_home: SmartHomeService,
    permissions: PermissionModel,
    device_type: str,
    metadata: dict,
) -> None:
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id, "Not A Vacuum", device_type=device_type, external_id="x.y", metadata=metadata
    )
    with pytest.raises(ServiceError, match="not a vacuum"):
        await service.get_vacuum_state(device.id)
    with pytest.raises(ServiceError, match="not a vacuum"):
        await service.start(device.id)


@pytest.mark.asyncio
async def test_humidifier_rejects_vacuum_domain(
    service: VacuumHumidifierService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    _, device = await _home_and_vacuum(smart_home)
    with pytest.raises(ServiceError, match="not a humidifier"):
        await service.get_humidifier_state(device.id)
    with pytest.raises(ServiceError, match="not a humidifier"):
        await service.set_humidifier_state(device.id, on=True)


@pytest.mark.asyncio
async def test_vacuum_rejects_humidifier_domain(
    service: VacuumHumidifierService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    _, device = await _home_and_humidifier(smart_home)
    with pytest.raises(ServiceError, match="not a vacuum"):
        await service.get_vacuum_state(device.id)


@pytest.mark.asyncio
async def test_unknown_device_raises(
    service: VacuumHumidifierService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    with pytest.raises(ServiceError):
        await service.get_vacuum_state("no-such-device")


# --- Reads are ungated ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_vacuum_reads_are_ungated(
    service: VacuumHumidifierService, smart_home: SmartHomeService
) -> None:
    await _home_and_vacuum(smart_home)
    rows = await service.list_vacuums()
    assert len(rows) == 1
    _, device = await _home_and_vacuum(smart_home, external_id="vacuum.2")
    state = await service.get_vacuum_state(device.id)
    assert state["id"] == device.id


@pytest.mark.asyncio
async def test_humidifier_reads_are_ungated(
    service: VacuumHumidifierService, smart_home: SmartHomeService
) -> None:
    await _home_and_humidifier(smart_home)
    rows = await service.list_humidifiers()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_permission_declared_pending_at_construction(permissions: PermissionModel) -> None:
    assert permissions.state(VACUUM_HUMIDIFIER_PRINCIPAL, SMART_HOME_SCOPE).value == "pending"


@pytest.mark.asyncio
async def test_vacuum_mutation_denied_without_grant(
    service: VacuumHumidifierService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_vacuum(smart_home)
    with pytest.raises(ServiceError, match="permission"):
        await service.start(device.id)


@pytest.mark.asyncio
async def test_humidifier_mutation_denied_without_grant(
    service: VacuumHumidifierService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_humidifier(smart_home)
    with pytest.raises(ServiceError, match="permission"):
        await service.set_humidifier_state(device.id, on=True)


# --- Vacuum state normalization -------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw_status", ["docked", "cleaning", "paused", "returning", "error", "idle"]
)
async def test_vacuum_state_is_open_pass_through(
    service: VacuumHumidifierService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
    raw_status: str,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_vacuum(smart_home)
    fake_connector.states[_VACUUM_EXTERNAL_ID] = _state(
        status=raw_status, external_id=_VACUUM_EXTERNAL_ID
    )

    state = await service.get_vacuum_state(device.id)

    assert state["state"] == raw_status
    assert state["available"] is True


@pytest.mark.asyncio
async def test_vacuum_unavailable_reports_none_state_not_the_status_string(
    service: VacuumHumidifierService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_vacuum(smart_home)
    fake_connector.states[_VACUUM_EXTERNAL_ID] = _state(
        status="unavailable", external_id=_VACUUM_EXTERNAL_ID
    )

    state = await service.get_vacuum_state(device.id)

    assert state["available"] is False
    assert state["state"] is None


@pytest.mark.asyncio
async def test_vacuum_battery_level_reported(
    service: VacuumHumidifierService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_vacuum(smart_home)
    fake_connector.states[_VACUUM_EXTERNAL_ID] = _state(
        status="docked", attributes={"battery_level": 87}, external_id=_VACUUM_EXTERNAL_ID
    )

    state = await service.get_vacuum_state(device.id)

    assert state["battery_level"] == 87.0


@pytest.mark.asyncio
async def test_vacuum_missing_battery_level_is_none_not_zero(
    service: VacuumHumidifierService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_vacuum(smart_home)
    fake_connector.states[_VACUUM_EXTERNAL_ID] = _state(
        status="docked", external_id=_VACUUM_EXTERNAL_ID
    )

    state = await service.get_vacuum_state(device.id)

    assert state["battery_level"] is None


@pytest.mark.asyncio
async def test_vacuum_malformed_battery_level_is_none(
    service: VacuumHumidifierService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_vacuum(smart_home)
    fake_connector.states[_VACUUM_EXTERNAL_ID] = _state(
        status="docked", attributes={"battery_level": "n/a"}, external_id=_VACUUM_EXTERNAL_ID
    )

    state = await service.get_vacuum_state(device.id)

    assert state["battery_level"] is None


@pytest.mark.asyncio
async def test_vacuum_connector_unreachable_falls_back(
    service: VacuumHumidifierService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_vacuum(smart_home)
    state = await service.get_vacuum_state(device.id)
    assert state["available"] is False
    assert state["state"] is None


@pytest.mark.asyncio
async def test_vacuum_list_is_db_only_no_live_read(
    service: VacuumHumidifierService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _home_and_vacuum(smart_home)
    fake_connector.states[_VACUUM_EXTERNAL_ID] = _state(
        status="cleaning", external_id=_VACUUM_EXTERNAL_ID
    )

    rows = await service.list_vacuums()

    assert rows[0]["available"] is False
    assert rows[0]["state"] is None


# --- Vacuum commands -------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method_name,wire_command",
    [
        ("start", "start"),
        ("stop", "stop"),
        ("pause", "pause"),
        ("return_to_base", "return_to_base"),
    ],
)
async def test_vacuum_command_sends_zero_payload_ha_call(
    service: VacuumHumidifierService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
    method_name: str,
    wire_command: str,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_vacuum(smart_home)
    fake_connector.states[_VACUUM_EXTERNAL_ID] = _state(
        status="docked", external_id=_VACUUM_EXTERNAL_ID
    )

    result = await getattr(service, method_name)(device.id)

    assert result["success"] is True
    assert fake_connector.sent_commands == [(_VACUUM_EXTERNAL_ID, wire_command, {})]


@pytest.mark.asyncio
async def test_vacuum_command_failure_surfaced_not_raised(
    service: VacuumHumidifierService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_vacuum(smart_home)
    fake_connector.states[_VACUUM_EXTERNAL_ID] = _state(
        status="docked", external_id=_VACUUM_EXTERNAL_ID
    )
    fake_connector.next_command_succeeds = False

    result = await service.start(device.id)

    assert result["success"] is False
    assert "fake rejection" in result["detail"]


@pytest.mark.asyncio
async def test_vacuum_no_recorded_connector_raises(
    service: VacuumHumidifierService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Orphan",
        device_type="appliance",
        external_id="vacuum.orphan",
        metadata={"domain": "vacuum"},
    )
    with pytest.raises(ServiceError, match="no recorded connector"):
        await service.start(device.id)


# --- Vacuum translators (unit-level) --------------------------------------------------


def test_vacuum_ha_translator_zero_payload() -> None:
    from jarvis.services.vacuum_humidifier_service import VacuumCommand

    for command in VacuumCommand:
        assert _translate_vacuum_home_assistant(command) == (command.value, {})


def test_vacuum_mqtt_translator_zero_payload() -> None:
    from jarvis.services.vacuum_humidifier_service import VacuumCommand

    for command in VacuumCommand:
        assert _translate_vacuum_mqtt(command) == (command.value, {})


@pytest.mark.asyncio
async def test_vacuum_mqtt_device_uses_defined_vocabulary(
    smart_home: SmartHomeService, permissions: PermissionModel, bus: EventBus
) -> None:
    mqtt_connector = FakeDeviceConnector()
    mqtt_connector.connector_type = "mqtt"
    reg = ConnectorFactoryRegistry()
    reg.register("mqtt", lambda config: mqtt_connector)
    conn = ConnectivityService(registry=reg, smart_home=smart_home, event_bus=bus)
    svc = VacuumHumidifierService(smart_home=smart_home, connectivity=conn, permissions=permissions)
    await conn.connect("mqtt")
    await permissions.grant(VACUUM_HUMIDIFIER_PRINCIPAL, SMART_HOME_SCOPE)
    _, device = await _home_and_vacuum(smart_home, connector_type="mqtt")
    mqtt_connector.states[_VACUUM_EXTERNAL_ID] = _state(
        status="docked", external_id=_VACUUM_EXTERNAL_ID
    )

    result = await svc.start(device.id)

    assert result["success"] is True
    assert mqtt_connector.sent_commands == [(_VACUUM_EXTERNAL_ID, "start", {})]


# --- Humidifier state normalization ---------------------------------------------------


@pytest.mark.asyncio
async def test_humidifier_full_state_normalization(
    service: VacuumHumidifierService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_humidifier(smart_home)
    fake_connector.states[_HUMIDIFIER_EXTERNAL_ID] = _state(
        status="on",
        attributes={
            "current_humidity": 38.0,
            "humidity": 45.0,
            "mode": "auto",
            "min_humidity": 30.0,
            "max_humidity": 80.0,
        },
        external_id=_HUMIDIFIER_EXTERNAL_ID,
    )

    state = await service.get_humidifier_state(device.id)

    assert state["available"] is True
    assert state["on"] is True
    assert state["current_humidity"] == 38.0
    assert state["target_humidity"] == 45.0
    assert state["mode"] == "auto"
    assert state["min_humidity"] == 30.0
    assert state["max_humidity"] == 80.0


@pytest.mark.asyncio
async def test_humidifier_unavailable_reports_none_live_fields(
    service: VacuumHumidifierService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_humidifier(smart_home)
    fake_connector.states[_HUMIDIFIER_EXTERNAL_ID] = _state(
        status="unavailable", external_id=_HUMIDIFIER_EXTERNAL_ID
    )

    state = await service.get_humidifier_state(device.id)

    assert state["available"] is False
    assert state["on"] is None
    assert state["current_humidity"] is None
    assert state["target_humidity"] is None


@pytest.mark.asyncio
async def test_humidifier_capability_fields_survive_unavailability(
    service: VacuumHumidifierService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_humidifier(smart_home)
    fake_connector.states[_HUMIDIFIER_EXTERNAL_ID] = _state(
        status="unavailable",
        attributes={"mode": "sleep", "min_humidity": 30.0, "max_humidity": 80.0},
        external_id=_HUMIDIFIER_EXTERNAL_ID,
    )

    state = await service.get_humidifier_state(device.id)

    assert state["available"] is False
    assert state["mode"] == "sleep"
    assert state["min_humidity"] == 30.0
    assert state["max_humidity"] == 80.0


@pytest.mark.asyncio
async def test_humidifier_missing_attributes_report_none_not_zero(
    service: VacuumHumidifierService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_humidifier(smart_home)
    fake_connector.states[_HUMIDIFIER_EXTERNAL_ID] = _state(
        status="on", external_id=_HUMIDIFIER_EXTERNAL_ID
    )

    state = await service.get_humidifier_state(device.id)

    assert state["current_humidity"] is None
    assert state["target_humidity"] is None
    assert state["mode"] is None
    assert state["min_humidity"] is None
    assert state["max_humidity"] is None


@pytest.mark.asyncio
async def test_humidifier_malformed_humidity_reports_none_not_zero(
    service: VacuumHumidifierService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_humidifier(smart_home)
    fake_connector.states[_HUMIDIFIER_EXTERNAL_ID] = _state(
        status="on",
        attributes={"current_humidity": "n/a", "humidity": None},
        external_id=_HUMIDIFIER_EXTERNAL_ID,
    )

    state = await service.get_humidifier_state(device.id)

    assert state["current_humidity"] is None
    assert state["target_humidity"] is None


@pytest.mark.asyncio
async def test_humidifier_list_is_db_only_no_live_read(
    service: VacuumHumidifierService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _home_and_humidifier(smart_home)
    fake_connector.states[_HUMIDIFIER_EXTERNAL_ID] = _state(
        status="on", attributes={"humidity": 50.0}, external_id=_HUMIDIFIER_EXTERNAL_ID
    )

    rows = await service.list_humidifiers()

    assert rows[0]["available"] is False
    assert rows[0]["target_humidity"] is None


# --- Humidifier mutations --------------------------------------------------------------


@pytest.mark.asyncio
async def test_humidifier_on_off_only_mutation(
    service: VacuumHumidifierService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_humidifier(smart_home)
    fake_connector.states[_HUMIDIFIER_EXTERNAL_ID] = _state(
        status="off", external_id=_HUMIDIFIER_EXTERNAL_ID
    )

    result = await service.set_humidifier_state(device.id, on=True)

    assert result["success"] is True
    assert fake_connector.sent_commands == [(_HUMIDIFIER_EXTERNAL_ID, "turn_on", {})]


@pytest.mark.asyncio
async def test_humidifier_humidity_only_mutation(
    service: VacuumHumidifierService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_humidifier(smart_home)
    fake_connector.states[_HUMIDIFIER_EXTERNAL_ID] = _state(
        status="on", external_id=_HUMIDIFIER_EXTERNAL_ID
    )

    result = await service.set_humidifier_state(device.id, target_humidity=50.0)

    assert result["success"] is True
    assert fake_connector.sent_commands == [
        (_HUMIDIFIER_EXTERNAL_ID, "set_humidity", {"humidity": 50.0})
    ]


@pytest.mark.asyncio
async def test_humidifier_combined_mutation_sends_on_off_first_then_humidity(
    service: VacuumHumidifierService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    """Logic Contract §9's documented ordering -- the opposite of
    Thermostat's mode-first ordering, and deliberately so."""
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_humidifier(smart_home)
    fake_connector.states[_HUMIDIFIER_EXTERNAL_ID] = _state(
        status="off", external_id=_HUMIDIFIER_EXTERNAL_ID
    )

    result = await service.set_humidifier_state(device.id, on=True, target_humidity=45.0)

    assert result["success"] is True
    assert fake_connector.sent_commands == [
        (_HUMIDIFIER_EXTERNAL_ID, "turn_on", {}),
        (_HUMIDIFIER_EXTERNAL_ID, "set_humidity", {"humidity": 45.0}),
    ]


@pytest.mark.asyncio
async def test_humidifier_turn_off_combined_with_humidity(
    service: VacuumHumidifierService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_humidifier(smart_home)
    fake_connector.states[_HUMIDIFIER_EXTERNAL_ID] = _state(
        status="on", external_id=_HUMIDIFIER_EXTERNAL_ID
    )

    result = await service.set_humidifier_state(device.id, on=False, target_humidity=40.0)

    assert result["success"] is True
    assert fake_connector.sent_commands == [
        (_HUMIDIFIER_EXTERNAL_ID, "turn_off", {}),
        (_HUMIDIFIER_EXTERNAL_ID, "set_humidity", {"humidity": 40.0}),
    ]


@pytest.mark.asyncio
async def test_humidifier_empty_mutation_rejected(
    service: VacuumHumidifierService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    _, device = await _home_and_humidifier(smart_home)
    with pytest.raises(ServiceError, match="at least one"):
        await service.set_humidifier_state(device.id)


@pytest.mark.asyncio
async def test_humidifier_partial_failure_reported_honestly(
    service: VacuumHumidifierService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_humidifier(smart_home)
    fake_connector.states[_HUMIDIFIER_EXTERNAL_ID] = _state(
        status="off", external_id=_HUMIDIFIER_EXTERNAL_ID
    )
    fake_connector.next_command_succeeds = False

    result = await service.set_humidifier_state(device.id, on=True, target_humidity=45.0)

    assert result["success"] is False


# --- Humidifier mode is read-only ------------------------------------------------------


def test_humidifier_mode_not_in_mutation_signature() -> None:
    import inspect

    sig = inspect.signature(VacuumHumidifierService.set_humidifier_state)
    assert "mode" not in sig.parameters


# --- Humidity validation ----------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [True, False])
async def test_bool_target_humidity_rejected(
    service: VacuumHumidifierService,
    smart_home: SmartHomeService,
    permissions: PermissionModel,
    bad: bool,
) -> None:
    await _grant(permissions)
    _, device = await _home_and_humidifier(smart_home)
    with pytest.raises(ServiceError, match="target_humidity must be a number"):
        await service.set_humidifier_state(device.id, target_humidity=bad)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
async def test_non_finite_target_humidity_rejected(
    service: VacuumHumidifierService,
    smart_home: SmartHomeService,
    permissions: PermissionModel,
    bad: float,
) -> None:
    await _grant(permissions)
    _, device = await _home_and_humidifier(smart_home)
    with pytest.raises(ServiceError, match="finite"):
        await service.set_humidifier_state(device.id, target_humidity=bad)


@pytest.mark.asyncio
async def test_target_humidity_below_device_reported_minimum_rejected(
    service: VacuumHumidifierService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_humidifier(smart_home)
    fake_connector.states[_HUMIDIFIER_EXTERNAL_ID] = _state(
        status="on",
        attributes={"min_humidity": 30.0, "max_humidity": 80.0},
        external_id=_HUMIDIFIER_EXTERNAL_ID,
    )

    with pytest.raises(ServiceError, match="below this device's reported minimum"):
        await service.set_humidifier_state(device.id, target_humidity=10.0)


@pytest.mark.asyncio
async def test_target_humidity_above_device_reported_maximum_rejected(
    service: VacuumHumidifierService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_humidifier(smart_home)
    fake_connector.states[_HUMIDIFIER_EXTERNAL_ID] = _state(
        status="on",
        attributes={"min_humidity": 30.0, "max_humidity": 80.0},
        external_id=_HUMIDIFIER_EXTERNAL_ID,
    )

    with pytest.raises(ServiceError, match="above this device's reported maximum"):
        await service.set_humidifier_state(device.id, target_humidity=99.0)


@pytest.mark.asyncio
async def test_no_bound_enforced_when_device_reports_none(
    service: VacuumHumidifierService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    """No invented safety limits -- a device that declares no min/max
    gets whatever the caller asked for (Logic Contract §8/§22)."""
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_humidifier(smart_home)
    fake_connector.states[_HUMIDIFIER_EXTERNAL_ID] = _state(
        status="on", external_id=_HUMIDIFIER_EXTERNAL_ID
    )

    result = await service.set_humidifier_state(device.id, target_humidity=5.0)

    assert result["success"] is True


# --- Humidifier translators (unit-level) -----------------------------------------------


def test_humidifier_ha_translator_on_only() -> None:
    assert _translate_humidifier_home_assistant(on=True, target_humidity=None) == [("turn_on", {})]


def test_humidifier_ha_translator_off_only() -> None:
    assert _translate_humidifier_home_assistant(on=False, target_humidity=None) == [
        ("turn_off", {})
    ]


def test_humidifier_ha_translator_humidity_only() -> None:
    assert _translate_humidifier_home_assistant(on=None, target_humidity=45.0) == [
        ("set_humidity", {"humidity": 45.0})
    ]


def test_humidifier_ha_translator_combined_is_two_calls_on_off_first() -> None:
    assert _translate_humidifier_home_assistant(on=True, target_humidity=45.0) == [
        ("turn_on", {}),
        ("set_humidity", {"humidity": 45.0}),
    ]


def test_humidifier_mqtt_translator_is_always_one_merged_call() -> None:
    assert _translate_humidifier_mqtt(on=True, target_humidity=None) == [
        ("set_state", {"on": True})
    ]
    assert _translate_humidifier_mqtt(on=None, target_humidity=45.0) == [
        ("set_state", {"target_humidity": 45.0})
    ]
    assert _translate_humidifier_mqtt(on=True, target_humidity=45.0) == [
        ("set_state", {"on": True, "target_humidity": 45.0})
    ]


# --- Cross-cutting invariants ------------------------------------------------------------


def test_service_does_not_import_connectors_directly() -> None:
    """Docstrings may *discuss* the connectors (they explain why zero
    connector changes were needed) -- only an actual import statement
    would be the real violation this test guards against."""
    import inspect

    from jarvis.services import vacuum_humidifier_service

    import_lines = [
        line
        for line in inspect.getsource(vacuum_humidifier_service).splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    joined = "\n".join(import_lines)
    assert "HomeAssistantConnector" not in joined
    assert "MqttConnector" not in joined
    assert "gmqtt" not in joined
    assert "connectors" not in joined.lower()


def test_service_publishes_no_events() -> None:
    import inspect

    from jarvis.services import vacuum_humidifier_service

    source = inspect.getsource(vacuum_humidifier_service)
    assert "event_bus" not in source
    assert "EventBus" not in source


def test_appliance_service_was_not_extended() -> None:
    """This slice is deliberately its own service -- ApplianceService
    must carry no vacuum/humidifier *implementation* (Logic Contract
    §14). Its own module docstring already, legitimately, names
    "vacuum"/"humidifier" in prose as future deferred categories
    (unchanged since Task Group G) -- this test checks for actual
    functional additions, not that pre-existing sentence."""
    import inspect

    from jarvis.services import appliance_service

    source = inspect.getsource(appliance_service)
    for leaked_symbol in (
        "VacuumCommand",
        "_VACUUM_DOMAIN",
        "_HUMIDIFIER_DOMAIN",
        "set_humidifier_state",
        "vacuum_start",
        "return_to_base",
    ):
        assert leaked_symbol not in source
