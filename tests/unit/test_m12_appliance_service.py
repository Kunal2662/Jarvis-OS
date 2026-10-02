"""ApplianceService tests -- Milestone 12 Appliance Control (Core
Appliance Slice: Fans + Covers).

Real (temp-file) SQLite ``SmartHomeService`` and a real ``PermissionModel``
throughout, matching ``test_m12_smart_switch_service.py``'s own pattern --
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
from jarvis.services.appliance_service import (
    APPLIANCE_PRINCIPAL,
    SMART_HOME_SCOPE,
    ApplianceService,
)
from jarvis.services.connectivity_service import ConnectivityService
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
) -> ApplianceService:
    return ApplianceService(
        smart_home=smart_home, connectivity=connectivity, permissions=permissions
    )


async def _grant(permissions: PermissionModel) -> None:
    await permissions.grant(APPLIANCE_PRINCIPAL, SMART_HOME_SCOPE)


async def _home_and_fan(
    smart_home: SmartHomeService,
    connector_type: str = "home_assistant",
    *,
    domain_key: str = "domain",
):
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Living Room Fan",
        device_type="appliance",
        external_id="fan.living_room_fan",
        metadata={"connector_type": connector_type, domain_key: "fan"},
    )
    return home, device


async def _home_and_cover(
    smart_home: SmartHomeService,
    connector_type: str = "home_assistant",
    *,
    domain_key: str = "domain",
):
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Living Room Blind",
        device_type="appliance",
        external_id="cover.living_room_blind",
        metadata={"connector_type": connector_type, domain_key: "cover"},
    )
    return home, device


# --- Permission enforcement --------------------------------------------------


@pytest.mark.asyncio
async def test_fan_on_denied_by_default(
    service: ApplianceService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_fan(smart_home)
    with pytest.raises(ServiceError, match="permission"):
        await service.fan_on(device.id)


@pytest.mark.asyncio
async def test_fan_off_denied_by_default(
    service: ApplianceService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_fan(smart_home)
    with pytest.raises(ServiceError, match="permission"):
        await service.fan_off(device.id)


@pytest.mark.asyncio
async def test_cover_open_denied_by_default(
    service: ApplianceService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_cover(smart_home)
    with pytest.raises(ServiceError, match="permission"):
        await service.cover_open(device.id)


@pytest.mark.asyncio
async def test_cover_close_denied_by_default(
    service: ApplianceService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_cover(smart_home)
    with pytest.raises(ServiceError, match="permission"):
        await service.cover_close(device.id)


@pytest.mark.asyncio
async def test_permission_declared_pending_at_construction(permissions: PermissionModel) -> None:
    assert permissions.state(APPLIANCE_PRINCIPAL, SMART_HOME_SCOPE).value == "pending"


@pytest.mark.asyncio
async def test_reads_do_not_require_permission(
    service: ApplianceService, smart_home: SmartHomeService
) -> None:
    """Fan/cover state carries no comparable privacy weight to sensor
    data -- see Logic Contract §14."""
    _, fan = await _home_and_fan(smart_home)
    fans = await service.list_fans()
    assert len(fans) == 1
    fan_state = await service.get_fan_state(fan.id)
    assert fan_state["id"] == fan.id

    _, cover = await _home_and_cover(smart_home)
    covers = await service.list_covers()
    assert len(covers) == 1
    cover_state = await service.get_cover_state(cover.id)
    assert cover_state["id"] == cover.id


# --- Domain discrimination (fan vs cover, both device_type="appliance") ----------


@pytest.mark.asyncio
async def test_list_fans_excludes_covers(
    service: ApplianceService, smart_home: SmartHomeService
) -> None:
    await _home_and_fan(smart_home)
    await _home_and_cover(smart_home)

    fans = await service.list_fans()
    covers = await service.list_covers()

    assert len(fans) == 1
    assert len(covers) == 1
    assert fans[0]["external_id"] == "fan.living_room_fan"
    assert covers[0]["external_id"] == "cover.living_room_blind"


@pytest.mark.asyncio
async def test_fan_on_rejects_cover_device(
    service: ApplianceService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    _, cover = await _home_and_cover(smart_home)
    with pytest.raises(ServiceError, match="not a fan"):
        await service.fan_on(cover.id)


@pytest.mark.asyncio
async def test_cover_open_rejects_fan_device(
    service: ApplianceService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    _, fan = await _home_and_fan(smart_home)
    with pytest.raises(ServiceError, match="not a cover"):
        await service.cover_open(fan.id)


@pytest.mark.asyncio
async def test_fan_on_rejects_non_appliance_device(
    service: ApplianceService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    lock = await smart_home.register_discovered_device(
        home.id, "Front Door", device_type="lock", external_id="lock.front_door"
    )
    with pytest.raises(ServiceError, match="not a fan"):
        await service.fan_on(lock.id)


# --- MQTT component fallback (M12 Final Exit Assessment, P1-1) -------------------
#
# `MqttConnector._handle_ha_discovery` writes `metadata["component"]`,
# never `metadata["domain"]` -- `_domain_for` must fall back to it, the
# same fallback order every sibling `device_type="appliance"`/`"other"`
# service already established. Regression coverage for the fix.


@pytest.mark.asyncio
async def test_domain_key_identifies_a_fan(
    service: ApplianceService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    """`metadata["domain"]` present -- domain wins, existing Home
    Assistant behavior unchanged."""
    await _grant(permissions)
    _, device = await _home_and_fan(smart_home, domain_key="domain")
    fans = await service.list_fans()
    assert [f["id"] for f in fans] == [device.id]


@pytest.mark.asyncio
async def test_component_key_identifies_a_fan(
    service: ApplianceService, smart_home: SmartHomeService
) -> None:
    """`metadata["domain"]` absent, `metadata["component"]` present --
    component fallback resolves the device (a real, MQTT Discovery-
    sourced fan)."""
    _, device = await _home_and_fan(smart_home, connector_type="mqtt", domain_key="component")
    fans = await service.list_fans()
    assert [f["id"] for f in fans] == [device.id]


@pytest.mark.asyncio
async def test_component_key_identifies_a_cover(
    service: ApplianceService, smart_home: SmartHomeService
) -> None:
    """Same fallback, cover category -- MQTT Discovery-sourced cover."""
    _, device = await _home_and_cover(smart_home, connector_type="mqtt", domain_key="component")
    covers = await service.list_covers()
    assert [c["id"] for c in covers] == [device.id]


@pytest.mark.asyncio
async def test_domain_takes_precedence_over_component(
    service: ApplianceService, smart_home: SmartHomeService
) -> None:
    """Both keys present -- `domain` wins, mirroring every sibling
    service's own identical precedence rule."""
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Ambiguous Fan",
        device_type="appliance",
        external_id="appliance.ambiguous",
        metadata={"connector_type": "home_assistant", "domain": "fan", "component": "cover"},
    )
    fans = await service.list_fans()
    assert [f["id"] for f in fans] == [device.id]


@pytest.mark.asyncio
async def test_empty_domain_falls_back_to_component(
    service: ApplianceService, smart_home: SmartHomeService
) -> None:
    """An empty-string `domain` is falsy -- falls through to
    `component`, never treated as "domain present but blank"."""
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Blank Domain Fan",
        device_type="appliance",
        external_id="appliance.blank_domain",
        metadata={"connector_type": "mqtt", "domain": "", "component": "fan"},
    )
    fans = await service.list_fans()
    assert [f["id"] for f in fans] == [device.id]


@pytest.mark.asyncio
async def test_neither_domain_nor_component_is_rejected(
    service: ApplianceService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    """Neither key present -- resolves to `None`, correctly rejected as
    "not a fan", never falsely matched."""
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "No Metadata",
        device_type="appliance",
        external_id="appliance.no_metadata",
        metadata={"connector_type": "home_assistant"},
    )
    with pytest.raises(ServiceError, match="not a fan"):
        await service.fan_on(device.id)


@pytest.mark.asyncio
async def test_mqtt_discovered_fan_can_be_commanded(
    service: ApplianceService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
) -> None:
    """End-to-end: an MQTT-discovered fan (`component`-only metadata,
    no `domain`) now resolves and can actually be commanded -- the
    exact defect this fix closes."""
    mqtt_connector = FakeDeviceConnector()
    mqtt_connector.connector_type = "mqtt"
    registry = ConnectorFactoryRegistry()
    registry.register("mqtt", lambda config: mqtt_connector)
    mqtt_connectivity = ConnectivityService(registry=registry, smart_home=smart_home)
    mqtt_service = ApplianceService(
        smart_home=smart_home, connectivity=mqtt_connectivity, permissions=permissions
    )
    await mqtt_connectivity.connect("mqtt")
    await _grant(permissions)
    _, device = await _home_and_fan(smart_home, connector_type="mqtt", domain_key="component")

    result = await mqtt_service.fan_on(device.id)

    assert result["success"] is True
    assert mqtt_connector.sent_commands == [("fan.living_room_fan", "turn_on", {})]


@pytest.mark.asyncio
async def test_mqtt_discovered_cover_can_be_commanded(
    service: ApplianceService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
) -> None:
    mqtt_connector = FakeDeviceConnector()
    mqtt_connector.connector_type = "mqtt"
    registry = ConnectorFactoryRegistry()
    registry.register("mqtt", lambda config: mqtt_connector)
    mqtt_connectivity = ConnectivityService(registry=registry, smart_home=smart_home)
    mqtt_service = ApplianceService(
        smart_home=smart_home, connectivity=mqtt_connectivity, permissions=permissions
    )
    await mqtt_connectivity.connect("mqtt")
    await _grant(permissions)
    _, device = await _home_and_cover(smart_home, connector_type="mqtt", domain_key="component")

    result = await mqtt_service.cover_open(device.id)

    assert result["success"] is True
    assert mqtt_connector.sent_commands == [("cover.living_room_blind", "open_cover", {})]


@pytest.mark.asyncio
async def test_wrong_component_is_still_rejected(
    service: ApplianceService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    """A device whose `component` names an unrelated category is still
    correctly rejected -- the fallback does not weaken discrimination."""
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "MQTT Siren",
        device_type="appliance",
        external_id="appliance.mqtt_siren",
        metadata={"connector_type": "mqtt", "component": "siren"},
    )
    with pytest.raises(ServiceError, match="not a fan"):
        await service.fan_on(device.id)


# --- Validation ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_fan_on_rejects_device_with_no_connector(
    service: ApplianceService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id, "Orphan Fan", device_type="appliance", metadata={"domain": "fan"}
    )
    with pytest.raises(ServiceError, match="no recorded connector"):
        await service.fan_on(device.id)


@pytest.mark.asyncio
async def test_fan_on_rejects_unsupported_connector_type(
    service: ApplianceService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    _, device = await _home_and_fan(smart_home, connector_type="zigbee")
    with pytest.raises(ServiceError, match="no command translation"):
        await service.fan_on(device.id)


@pytest.mark.asyncio
async def test_cover_open_rejects_unsupported_connector_type(
    service: ApplianceService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    _, device = await _home_and_cover(smart_home, connector_type="zigbee")
    with pytest.raises(ServiceError, match="no command translation"):
        await service.cover_open(device.id)


@pytest.mark.asyncio
async def test_get_fan_state_unknown_device_raises(service: ApplianceService) -> None:
    with pytest.raises(ServiceError):
        await service.get_fan_state("no-such-device")


@pytest.mark.asyncio
async def test_get_cover_state_unknown_device_raises(service: ApplianceService) -> None:
    with pytest.raises(ServiceError):
        await service.get_cover_state("no-such-device")


# --- Home Assistant translation ------------------------------------------------


@pytest.mark.asyncio
async def test_ha_fan_on_translation(
    service: ApplianceService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_fan(smart_home)

    result = await service.fan_on(device.id)

    assert result["success"] is True
    assert fake_connector.sent_commands == [("fan.living_room_fan", "turn_on", {})]


@pytest.mark.asyncio
async def test_ha_fan_off_translation(
    service: ApplianceService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_fan(smart_home)

    result = await service.fan_off(device.id)

    assert result["success"] is True
    assert fake_connector.sent_commands == [("fan.living_room_fan", "turn_off", {})]


@pytest.mark.asyncio
async def test_ha_cover_open_translation(
    service: ApplianceService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_cover(smart_home)

    result = await service.cover_open(device.id)

    assert result["success"] is True
    assert fake_connector.sent_commands == [("cover.living_room_blind", "open_cover", {})]


@pytest.mark.asyncio
async def test_ha_cover_close_translation(
    service: ApplianceService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_cover(smart_home)

    result = await service.cover_close(device.id)

    assert result["success"] is True
    assert fake_connector.sent_commands == [("cover.living_room_blind", "close_cover", {})]


# --- MQTT translation -----------------------------------------------------------


@pytest.mark.asyncio
async def test_mqtt_fan_on_and_off_translation(
    smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    mqtt_connector = FakeDeviceConnector()
    mqtt_connector.connector_type = "mqtt"
    registry = ConnectorFactoryRegistry()
    registry.register("mqtt", lambda config: mqtt_connector)
    mqtt_connectivity = ConnectivityService(registry=registry, smart_home=smart_home)
    mqtt_service = ApplianceService(
        smart_home=smart_home, connectivity=mqtt_connectivity, permissions=permissions
    )
    await mqtt_connectivity.connect("mqtt")
    await _grant(permissions)
    _, device = await _home_and_fan(smart_home, connector_type="mqtt")

    await mqtt_service.fan_on(device.id)
    await mqtt_service.fan_off(device.id)

    assert mqtt_connector.sent_commands == [
        ("fan.living_room_fan", "turn_on", {}),
        ("fan.living_room_fan", "turn_off", {}),
    ]


@pytest.mark.asyncio
async def test_mqtt_cover_open_and_close_translation(
    smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    mqtt_connector = FakeDeviceConnector()
    mqtt_connector.connector_type = "mqtt"
    registry = ConnectorFactoryRegistry()
    registry.register("mqtt", lambda config: mqtt_connector)
    mqtt_connectivity = ConnectivityService(registry=registry, smart_home=smart_home)
    mqtt_service = ApplianceService(
        smart_home=smart_home, connectivity=mqtt_connectivity, permissions=permissions
    )
    await mqtt_connectivity.connect("mqtt")
    await _grant(permissions)
    _, device = await _home_and_cover(smart_home, connector_type="mqtt")

    await mqtt_service.cover_open(device.id)
    await mqtt_service.cover_close(device.id)

    assert mqtt_connector.sent_commands == [
        ("cover.living_room_blind", "open_cover", {}),
        ("cover.living_room_blind", "close_cover", {}),
    ]


# --- Reads: live state merge (fan) ----------------------------------------------


@pytest.mark.asyncio
async def test_get_fan_state_reports_on_true(
    service: ApplianceService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_fan(smart_home)
    fake_connector.states["fan.living_room_fan"] = DeviceState(
        external_id="fan.living_room_fan", status="on", attributes={}
    )

    state = await service.get_fan_state(device.id)

    assert state["on"] is True
    assert state["available"] is True


@pytest.mark.asyncio
async def test_get_fan_state_reports_on_false(
    service: ApplianceService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_fan(smart_home)
    fake_connector.states["fan.living_room_fan"] = DeviceState(
        external_id="fan.living_room_fan", status="off", attributes={}
    )

    state = await service.get_fan_state(device.id)

    assert state["on"] is False


@pytest.mark.asyncio
async def test_get_fan_state_falls_back_when_connector_unreachable(
    service: ApplianceService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_fan(smart_home)

    state = await service.get_fan_state(device.id)

    assert state["id"] == device.id
    assert state["on"] is None
    assert state["available"] is False


@pytest.mark.asyncio
async def test_fan_connector_reported_offline_status_marks_unavailable(
    service: ApplianceService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_fan(smart_home)
    fake_connector.states["fan.living_room_fan"] = DeviceState(
        external_id="fan.living_room_fan", status="unavailable", attributes={}
    )

    state = await service.get_fan_state(device.id)

    assert state["available"] is False
    assert state["on"] is None


@pytest.mark.asyncio
async def test_list_fans_does_not_make_a_live_connector_read(
    service: ApplianceService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _home_and_fan(smart_home)
    fake_connector.states["fan.living_room_fan"] = DeviceState(
        external_id="fan.living_room_fan", status="on", attributes={}
    )

    rows = await service.list_fans()

    assert len(rows) == 1
    assert rows[0]["on"] is None  # DB-only -- see ApplianceService.list_fans docstring.


# --- Reads: live state merge (cover) ---------------------------------------------


@pytest.mark.asyncio
async def test_get_cover_state_reports_open(
    service: ApplianceService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_cover(smart_home)
    fake_connector.states["cover.living_room_blind"] = DeviceState(
        external_id="cover.living_room_blind", status="open", attributes={}
    )

    state = await service.get_cover_state(device.id)

    assert state["state"] == "open"
    assert state["available"] is True


@pytest.mark.asyncio
async def test_get_cover_state_reports_closed(
    service: ApplianceService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_cover(smart_home)
    fake_connector.states["cover.living_room_blind"] = DeviceState(
        external_id="cover.living_room_blind", status="closed", attributes={}
    )

    state = await service.get_cover_state(device.id)

    assert state["state"] == "closed"


@pytest.mark.asyncio
async def test_get_cover_state_reports_opening_and_closing(
    service: ApplianceService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_cover(smart_home)

    fake_connector.states["cover.living_room_blind"] = DeviceState(
        external_id="cover.living_room_blind", status="opening", attributes={}
    )
    assert (await service.get_cover_state(device.id))["state"] == "opening"

    fake_connector.states["cover.living_room_blind"] = DeviceState(
        external_id="cover.living_room_blind", status="closing", attributes={}
    )
    assert (await service.get_cover_state(device.id))["state"] == "closing"


@pytest.mark.asyncio
async def test_get_cover_state_unrecognized_status_reports_none(
    service: ApplianceService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    """Never fabricates a state the connector layer does not itself
    represent -- see Logic Contract §6."""
    await connectivity.connect("home_assistant")
    _, device = await _home_and_cover(smart_home)
    fake_connector.states["cover.living_room_blind"] = DeviceState(
        external_id="cover.living_room_blind", status="stopped", attributes={}
    )

    state = await service.get_cover_state(device.id)

    assert state["state"] is None
    assert state["available"] is True


@pytest.mark.asyncio
async def test_get_cover_state_falls_back_when_connector_unreachable(
    service: ApplianceService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_cover(smart_home)

    state = await service.get_cover_state(device.id)

    assert state["id"] == device.id
    assert state["state"] is None
    assert state["available"] is False


@pytest.mark.asyncio
async def test_cover_connector_reported_offline_status_marks_unavailable(
    service: ApplianceService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_cover(smart_home)
    fake_connector.states["cover.living_room_blind"] = DeviceState(
        external_id="cover.living_room_blind", status="unavailable", attributes={}
    )

    state = await service.get_cover_state(device.id)

    assert state["available"] is False
    assert state["state"] is None


@pytest.mark.asyncio
async def test_list_covers_does_not_make_a_live_connector_read(
    service: ApplianceService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _home_and_cover(smart_home)
    fake_connector.states["cover.living_room_blind"] = DeviceState(
        external_id="cover.living_room_blind", status="open", attributes={}
    )

    rows = await service.list_covers()

    assert len(rows) == 1
    assert rows[0]["state"] is None  # DB-only -- see ApplianceService.list_covers docstring.


# --- Failure honesty --------------------------------------------------------------


@pytest.mark.asyncio
async def test_fan_failed_command_reports_failure_not_success(
    service: ApplianceService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    fake_connector.next_command_succeeds = False
    _, device = await _home_and_fan(smart_home)

    result = await service.fan_on(device.id)

    assert result["success"] is False
    assert result["detail"]


@pytest.mark.asyncio
async def test_cover_failed_command_reports_failure_not_success(
    service: ApplianceService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    fake_connector.next_command_succeeds = False
    _, device = await _home_and_cover(smart_home)

    result = await service.cover_open(device.id)

    assert result["success"] is False
    assert result["detail"]


# --- Scope discipline: exactly the approved public surface -----------------------


@pytest.mark.asyncio
async def test_appliance_service_has_exactly_the_approved_public_methods() -> None:
    """Fan percentage and cover position are now shipped (Task Group T,
    Fan Percentage + Cover Position Logic Contract) -- this pins the
    exact public surface so a future change cannot silently grow it
    further without deliberately touching this test."""
    public_methods = {
        name
        for name in dir(ApplianceService)
        if not name.startswith("_") and callable(getattr(ApplianceService, name))
    }
    assert public_methods == {
        "list_fans",
        "get_fan_state",
        "fan_on",
        "fan_off",
        "set_fan_percentage",
        "list_covers",
        "get_cover_state",
        "cover_open",
        "cover_close",
        "set_cover_position",
    }


# --- Fan percentage (Fan Percentage + Cover Position Logic Contract §4) ----------


@pytest.mark.asyncio
async def test_set_fan_percentage_denied_by_default(
    service: ApplianceService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_fan(smart_home)
    with pytest.raises(ServiceError, match="permission"):
        await service.set_fan_percentage(device.id, 50)


@pytest.mark.asyncio
async def test_set_fan_percentage_rejects_cover_device(
    service: ApplianceService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    _, cover = await _home_and_cover(smart_home)
    with pytest.raises(ServiceError, match="not a fan"):
        await service.set_fan_percentage(cover.id, 50)


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [0, 1, 50, 99, 100])
async def test_set_fan_percentage_accepts_valid_range(
    service: ApplianceService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
    value: int,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_fan(smart_home)

    result = await service.set_fan_percentage(device.id, value)

    assert result["success"] is True
    assert fake_connector.sent_commands == [
        ("fan.living_room_fan", "set_percentage", {"percentage": value})
    ]


@pytest.mark.asyncio
async def test_set_fan_percentage_zero_is_sent_literally_not_turn_off(
    service: ApplianceService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    """0 is a valid, literal percentage value -- externally verified
    HA behavior is device-dependent, so this module never substitutes
    or additionally sends `turn_off` (Logic Contract §4)."""
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_fan(smart_home)

    await service.set_fan_percentage(device.id, 0)

    assert fake_connector.sent_commands == [
        ("fan.living_room_fan", "set_percentage", {"percentage": 0})
    ]
    assert ("fan.living_room_fan", "turn_off", {}) not in fake_connector.sent_commands


@pytest.mark.asyncio
async def test_set_fan_percentage_never_implies_turn_on(
    service: ApplianceService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_fan(smart_home)

    await service.set_fan_percentage(device.id, 75)

    assert fake_connector.sent_commands == [
        ("fan.living_room_fan", "set_percentage", {"percentage": 75})
    ]
    assert ("fan.living_room_fan", "turn_on", {}) not in fake_connector.sent_commands


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [-1, 101, 1000, -100])
async def test_set_fan_percentage_rejects_out_of_range(
    service: ApplianceService,
    smart_home: SmartHomeService,
    permissions: PermissionModel,
    value: int,
) -> None:
    await _grant(permissions)
    _, device = await _home_and_fan(smart_home)
    with pytest.raises(ServiceError, match="0-100"):
        await service.set_fan_percentage(device.id, value)


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [50.5, "50", None, True, False])
async def test_set_fan_percentage_rejects_non_integer(
    service: ApplianceService,
    smart_home: SmartHomeService,
    permissions: PermissionModel,
    value,
) -> None:
    await _grant(permissions)
    _, device = await _home_and_fan(smart_home)
    with pytest.raises(ServiceError, match="0-100"):
        await service.set_fan_percentage(device.id, value)


@pytest.mark.asyncio
async def test_set_fan_percentage_reports_failure_not_success(
    service: ApplianceService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    fake_connector.next_command_succeeds = False
    _, device = await _home_and_fan(smart_home)

    result = await service.set_fan_percentage(device.id, 50)

    assert result["success"] is False
    assert result["detail"]


@pytest.mark.asyncio
async def test_mqtt_set_fan_percentage_translation(
    smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    mqtt_connector = FakeDeviceConnector()
    mqtt_connector.connector_type = "mqtt"
    registry = ConnectorFactoryRegistry()
    registry.register("mqtt", lambda config: mqtt_connector)
    mqtt_connectivity = ConnectivityService(registry=registry, smart_home=smart_home)
    mqtt_service = ApplianceService(
        smart_home=smart_home, connectivity=mqtt_connectivity, permissions=permissions
    )
    await mqtt_connectivity.connect("mqtt")
    await _grant(permissions)
    _, device = await _home_and_fan(smart_home, connector_type="mqtt")

    await mqtt_service.set_fan_percentage(device.id, 60)

    assert mqtt_connector.sent_commands == [
        ("fan.living_room_fan", "set_percentage", {"percentage": 60})
    ]


@pytest.mark.asyncio
async def test_get_fan_state_reports_percentage(
    service: ApplianceService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_fan(smart_home)
    fake_connector.states["fan.living_room_fan"] = DeviceState(
        external_id="fan.living_room_fan", status="on", attributes={"percentage": 42}
    )

    state = await service.get_fan_state(device.id)

    assert state["percentage"] == 42


@pytest.mark.asyncio
async def test_get_fan_state_percentage_none_when_unreported(
    service: ApplianceService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    """A fan without `FanEntityFeature.SET_SPEED` simply never reports
    a `percentage` attribute -- never fabricated (Logic Contract §4)."""
    await connectivity.connect("home_assistant")
    _, device = await _home_and_fan(smart_home)
    fake_connector.states["fan.living_room_fan"] = DeviceState(
        external_id="fan.living_room_fan", status="on", attributes={}
    )

    state = await service.get_fan_state(device.id)

    assert state["percentage"] is None


@pytest.mark.asyncio
async def test_get_fan_state_percentage_none_when_unavailable(
    service: ApplianceService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_fan(smart_home)

    state = await service.get_fan_state(device.id)

    assert state["percentage"] is None
    assert state["available"] is False


# --- Cover position (Fan Percentage + Cover Position Logic Contract §5) ----------


@pytest.mark.asyncio
async def test_set_cover_position_denied_by_default(
    service: ApplianceService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_cover(smart_home)
    with pytest.raises(ServiceError, match="permission"):
        await service.set_cover_position(device.id, 50)


@pytest.mark.asyncio
async def test_set_cover_position_rejects_fan_device(
    service: ApplianceService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    _, fan = await _home_and_fan(smart_home)
    with pytest.raises(ServiceError, match="not a cover"):
        await service.set_cover_position(fan.id, 50)


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [0, 1, 50, 99, 100])
async def test_set_cover_position_accepts_valid_range(
    service: ApplianceService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
    value: int,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_cover(smart_home)

    result = await service.set_cover_position(device.id, value)

    assert result["success"] is True
    assert fake_connector.sent_commands == [
        ("cover.living_room_blind", "set_cover_position", {"position": value})
    ]


@pytest.mark.asyncio
async def test_set_cover_position_never_implies_open_or_close(
    service: ApplianceService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_cover(smart_home)

    await service.set_cover_position(device.id, 50)

    assert fake_connector.sent_commands == [
        ("cover.living_room_blind", "set_cover_position", {"position": 50})
    ]
    assert ("cover.living_room_blind", "open_cover", {}) not in fake_connector.sent_commands
    assert ("cover.living_room_blind", "close_cover", {}) not in fake_connector.sent_commands


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [-1, 101, 1000, -100])
async def test_set_cover_position_rejects_out_of_range(
    service: ApplianceService,
    smart_home: SmartHomeService,
    permissions: PermissionModel,
    value: int,
) -> None:
    await _grant(permissions)
    _, device = await _home_and_cover(smart_home)
    with pytest.raises(ServiceError, match="0-100"):
        await service.set_cover_position(device.id, value)


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [50.5, "50", None, True, False])
async def test_set_cover_position_rejects_non_integer(
    service: ApplianceService,
    smart_home: SmartHomeService,
    permissions: PermissionModel,
    value,
) -> None:
    await _grant(permissions)
    _, device = await _home_and_cover(smart_home)
    with pytest.raises(ServiceError, match="0-100"):
        await service.set_cover_position(device.id, value)


@pytest.mark.asyncio
async def test_set_cover_position_reports_failure_not_success(
    service: ApplianceService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    fake_connector.next_command_succeeds = False
    _, device = await _home_and_cover(smart_home)

    result = await service.set_cover_position(device.id, 50)

    assert result["success"] is False
    assert result["detail"]


@pytest.mark.asyncio
async def test_mqtt_set_cover_position_translation(
    smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    mqtt_connector = FakeDeviceConnector()
    mqtt_connector.connector_type = "mqtt"
    registry = ConnectorFactoryRegistry()
    registry.register("mqtt", lambda config: mqtt_connector)
    mqtt_connectivity = ConnectivityService(registry=registry, smart_home=smart_home)
    mqtt_service = ApplianceService(
        smart_home=smart_home, connectivity=mqtt_connectivity, permissions=permissions
    )
    await mqtt_connectivity.connect("mqtt")
    await _grant(permissions)
    _, device = await _home_and_cover(smart_home, connector_type="mqtt")

    await mqtt_service.set_cover_position(device.id, 30)

    assert mqtt_connector.sent_commands == [
        ("cover.living_room_blind", "set_cover_position", {"position": 30})
    ]


@pytest.mark.asyncio
async def test_get_cover_state_reports_position_from_current_cover_position(
    service: ApplianceService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    """Read attribute is `current_cover_position` -- deliberately NOT
    `position` (the write parameter name); verified externally against
    Home Assistant's own developer docs (Logic Contract §8)."""
    await connectivity.connect("home_assistant")
    _, device = await _home_and_cover(smart_home)
    fake_connector.states["cover.living_room_blind"] = DeviceState(
        external_id="cover.living_room_blind",
        status="open",
        attributes={"current_cover_position": 77},
    )

    state = await service.get_cover_state(device.id)

    assert state["position"] == 77


@pytest.mark.asyncio
async def test_get_cover_state_ignores_bare_position_attribute(
    service: ApplianceService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    """A stray `position` attribute (the write-side name) must not be
    misread as the current position -- only `current_cover_position`
    is the real read attribute."""
    await connectivity.connect("home_assistant")
    _, device = await _home_and_cover(smart_home)
    fake_connector.states["cover.living_room_blind"] = DeviceState(
        external_id="cover.living_room_blind", status="open", attributes={"position": 77}
    )

    state = await service.get_cover_state(device.id)

    assert state["position"] is None


@pytest.mark.asyncio
async def test_get_cover_state_position_none_when_unreported(
    service: ApplianceService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_cover(smart_home)
    fake_connector.states["cover.living_room_blind"] = DeviceState(
        external_id="cover.living_room_blind", status="open", attributes={}
    )

    state = await service.get_cover_state(device.id)

    assert state["position"] is None


@pytest.mark.asyncio
async def test_get_cover_state_position_none_when_unavailable(
    service: ApplianceService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_cover(smart_home)

    state = await service.get_cover_state(device.id)

    assert state["position"] is None
    assert state["available"] is False


# --- Backward compatibility (Logic Contract §15) ----------------------------------


@pytest.mark.asyncio
async def test_fan_on_off_unaffected_by_percentage_addition(
    service: ApplianceService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_fan(smart_home)

    await service.fan_on(device.id)
    await service.fan_off(device.id)

    assert fake_connector.sent_commands == [
        ("fan.living_room_fan", "turn_on", {}),
        ("fan.living_room_fan", "turn_off", {}),
    ]


@pytest.mark.asyncio
async def test_cover_open_close_unaffected_by_position_addition(
    service: ApplianceService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_cover(smart_home)

    await service.cover_open(device.id)
    await service.cover_close(device.id)

    assert fake_connector.sent_commands == [
        ("cover.living_room_blind", "open_cover", {}),
        ("cover.living_room_blind", "close_cover", {}),
    ]


# --- Cross-cutting invariants (Fan Percentage + Cover Position Logic Contract §16-19) --
#
# These guards scan the module's *code*, not its docstrings -- the
# module docstring itself explains, in prose, why percentage/position
# are never merged into turn_on/open_cover, which would otherwise
# collide with a naive whole-source scan. `_code_without_docstrings`
# strips every module/function/class docstring via an AST transform
# before re-serializing, so these tests check actual code, never
# explanatory prose.


def _code_without_docstrings(source: str) -> str:
    import ast

    tree = ast.parse(source)
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            node.body.pop(0)
            if not node.body:
                node.body.append(ast.Pass())
    return ast.unparse(tree)


def _service_code() -> str:
    import inspect

    from jarvis.services import appliance_service

    return _code_without_docstrings(inspect.getsource(appliance_service))


def test_service_has_no_eventbus_reference() -> None:
    source = _service_code()
    assert "event_bus" not in source
    assert "EventBus" not in source


def test_service_has_no_scheduler_reference() -> None:
    source = _service_code()
    assert "Scheduler" not in source
    assert "schedule" not in source.lower()


def test_service_has_no_analytics_or_memory_reference() -> None:
    source = _service_code()
    assert "Analytics" not in source
    assert "trend" not in source.lower()
    assert "MemoryService" not in source
    assert "SmartHomeMemoryService" not in source


def test_service_does_not_import_connectors_directly() -> None:
    import inspect

    from jarvis.services import appliance_service

    import_lines = [
        line
        for line in inspect.getsource(appliance_service).splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    joined = "\n".join(import_lines)
    assert "HomeAssistantConnector" not in joined
    assert "MqttConnector" not in joined
