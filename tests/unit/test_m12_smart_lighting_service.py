"""SmartLightingService tests -- Milestone 12 Connectivity REST + Smart
Lighting.

Real (temp-file) SQLite ``SmartHomeService`` and a real ``PermissionModel``
throughout, matching ``test_connectivity_service.py``'s own pattern --
only the connector itself is faked (``FakeDeviceConnector``), never the
service under test or its collaborators.
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
from jarvis.services.smart_lighting_service import (
    SMART_HOME_SCOPE,
    SMART_LIGHTING_PRINCIPAL,
    SmartLightingService,
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
    db,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
) -> SmartLightingService:
    return SmartLightingService(
        database=db, smart_home=smart_home, connectivity=connectivity, permissions=permissions
    )


async def _grant(permissions: PermissionModel) -> None:
    await permissions.grant(SMART_LIGHTING_PRINCIPAL, SMART_HOME_SCOPE)


async def _home_and_light(
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    *,
    connector_type: str = "home_assistant",
):
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Living Room Lamp",
        device_type="light",
        external_id="light.living_room",
        metadata={"connector_type": connector_type},
    )
    return home, device


# --- Permission enforcement --------------------------------------------------


@pytest.mark.asyncio
async def test_set_light_state_denied_by_default(
    service: SmartLightingService, smart_home: SmartHomeService, connectivity: ConnectivityService
) -> None:
    _, device = await _home_and_light(smart_home, connectivity)
    with pytest.raises(ServiceError, match="permission"):
        await service.set_light_state(device.id, on=True)


@pytest.mark.asyncio
async def test_permission_declared_pending_at_construction(permissions: PermissionModel) -> None:
    assert permissions.state(SMART_LIGHTING_PRINCIPAL, SMART_HOME_SCOPE).value == "pending"


@pytest.mark.asyncio
async def test_set_light_state_succeeds_once_granted(
    service: SmartLightingService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_light(smart_home, connectivity)

    result = await service.set_light_state(device.id, on=True)

    assert result["success"] is True
    assert fake_connector.sent_commands == [("light.living_room", "turn_on", {})]


@pytest.mark.asyncio
async def test_read_only_operations_do_not_require_permission(
    service: SmartLightingService, smart_home: SmartHomeService, connectivity: ConnectivityService
) -> None:
    _, device = await _home_and_light(smart_home, connectivity)
    # No grant() call anywhere in this test -- reads must still work.
    lights = await service.list_lights()
    assert len(lights) == 1
    state = await service.get_light_state(device.id)
    assert state["id"] == device.id


# --- Validation ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_light_state_requires_at_least_one_attribute(
    service: SmartLightingService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
) -> None:
    await _grant(permissions)
    _, device = await _home_and_light(smart_home, connectivity)
    with pytest.raises(ServiceError, match="at least one"):
        await service.set_light_state(device.id)


@pytest.mark.asyncio
async def test_set_light_state_rejects_off_combined_with_brightness(
    service: SmartLightingService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
) -> None:
    await _grant(permissions)
    _, device = await _home_and_light(smart_home, connectivity)
    with pytest.raises(ServiceError, match="Cannot combine"):
        await service.set_light_state(device.id, on=False, brightness=50)


@pytest.mark.asyncio
@pytest.mark.parametrize("brightness", [-1, 101, 50.5, True])
async def test_set_light_state_rejects_invalid_brightness(
    service: SmartLightingService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    brightness: object,
) -> None:
    await _grant(permissions)
    _, device = await _home_and_light(smart_home, connectivity)
    with pytest.raises(ServiceError, match="brightness"):
        await service.set_light_state(device.id, brightness=brightness)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_set_light_state_rejects_invalid_color(
    service: SmartLightingService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
) -> None:
    await _grant(permissions)
    _, device = await _home_and_light(smart_home, connectivity)
    with pytest.raises(ServiceError, match="color"):
        await service.set_light_state(device.id, color=(300, 0, 0))


@pytest.mark.asyncio
async def test_set_light_state_rejects_non_light_device(
    service: SmartLightingService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
) -> None:
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    switch = await smart_home.register_discovered_device(
        home.id, "Hallway Switch", device_type="switch", external_id="switch.hallway"
    )
    with pytest.raises(ServiceError, match="not a light"):
        await service.set_light_state(switch.id, on=True)


@pytest.mark.asyncio
async def test_set_light_state_rejects_device_with_no_connector(
    service: SmartLightingService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id, "Orphan Light", device_type="light"
    )
    with pytest.raises(ServiceError, match="no recorded connector"):
        await service.set_light_state(device.id, on=True)


@pytest.mark.asyncio
async def test_set_light_state_rejects_unsupported_connector_type(
    service: SmartLightingService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
) -> None:
    """Fails safely (a real, reportable ServiceError) rather than
    silently no-opping -- see module docstring's `_TRANSLATORS` note."""
    await _grant(permissions)
    _, device = await _home_and_light(smart_home, connectivity, connector_type="zigbee")
    with pytest.raises(ServiceError, match="no command translation"):
        await service.set_light_state(device.id, on=True)


# --- Home Assistant translation ------------------------------------------------


@pytest.mark.asyncio
async def test_ha_translation_turn_off(
    service: SmartLightingService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_light(smart_home, connectivity)

    await service.set_light_state(device.id, on=False)

    assert fake_connector.sent_commands == [("light.living_room", "turn_off", {})]


@pytest.mark.asyncio
async def test_ha_translation_merges_attributes_into_one_turn_on_call(
    service: SmartLightingService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_light(smart_home, connectivity)

    await service.set_light_state(
        device.id, brightness=80, color_temp_kelvin=4000, color=(10, 20, 30)
    )

    assert len(fake_connector.sent_commands) == 1
    external_id, command, payload = fake_connector.sent_commands[0]
    assert external_id == "light.living_room"
    assert command == "turn_on"
    assert payload == {
        "brightness_pct": 80,
        "color_temp_kelvin": 4000,
        "rgb_color": [10, 20, 30],
    }


# --- MQTT translation -----------------------------------------------------------


@pytest.mark.asyncio
async def test_mqtt_translation_turn_off(
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    db,
) -> None:
    mqtt_connector = FakeDeviceConnector()
    mqtt_connector.connector_type = "mqtt"
    registry = ConnectorFactoryRegistry()
    registry.register("mqtt", lambda config: mqtt_connector)
    mqtt_connectivity = ConnectivityService(registry=registry, smart_home=smart_home)
    mqtt_service = SmartLightingService(
        database=db, smart_home=smart_home, connectivity=mqtt_connectivity, permissions=permissions
    )
    await mqtt_connectivity.connect("mqtt")
    await _grant(permissions)
    _, device = await _home_and_light(smart_home, mqtt_connectivity, connector_type="mqtt")

    await mqtt_service.set_light_state(device.id, on=False)

    assert mqtt_connector.sent_commands == [("light.living_room", "turn_off", {})]


@pytest.mark.asyncio
async def test_mqtt_translation_merges_attributes_into_one_set_state_call(
    smart_home: SmartHomeService, permissions: PermissionModel, db
) -> None:
    mqtt_connector = FakeDeviceConnector()
    mqtt_connector.connector_type = "mqtt"
    registry = ConnectorFactoryRegistry()
    registry.register("mqtt", lambda config: mqtt_connector)
    mqtt_connectivity = ConnectivityService(registry=registry, smart_home=smart_home)
    mqtt_service = SmartLightingService(
        database=db, smart_home=smart_home, connectivity=mqtt_connectivity, permissions=permissions
    )
    await mqtt_connectivity.connect("mqtt")
    await _grant(permissions)
    _, device = await _home_and_light(smart_home, mqtt_connectivity, connector_type="mqtt")

    await mqtt_service.set_light_state(device.id, on=True, brightness=42, color=(1, 2, 3))

    assert len(mqtt_connector.sent_commands) == 1
    external_id, command, payload = mqtt_connector.sent_commands[0]
    assert external_id == "light.living_room"
    assert command == "set_state"
    assert payload == {"on": True, "brightness": 42, "color": [1, 2, 3]}


# --- Reads: live state merge ---------------------------------------------------


@pytest.mark.asyncio
async def test_get_light_state_merges_live_connector_attributes(
    service: SmartLightingService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_light(smart_home, connectivity)
    fake_connector.states["light.living_room"] = DeviceState(
        external_id="light.living_room",
        status="on",
        attributes={"brightness": 128, "rgb_color": [5, 6, 7]},
    )

    state = await service.get_light_state(device.id)

    assert state["on"] is True
    assert state["brightness"] == 128
    assert state["color"] == [5, 6, 7]


@pytest.mark.asyncio
async def test_get_light_state_falls_back_when_connector_unreachable(
    service: SmartLightingService, smart_home: SmartHomeService, connectivity: ConnectivityService
) -> None:
    """Connector never connected -- a real, expected outcome; the read
    must not fail, just report last-known DB state with unknown
    attributes (module docstring's "fail safely" framing)."""
    _, device = await _home_and_light(smart_home, connectivity)

    state = await service.get_light_state(device.id)

    assert state["id"] == device.id
    assert state["on"] is None
    assert state["brightness"] is None


@pytest.mark.asyncio
async def test_list_lights_does_not_make_a_live_connector_read(
    service: SmartLightingService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _home_and_light(smart_home, connectivity)
    fake_connector.states["light.living_room"] = DeviceState(
        external_id="light.living_room", status="on", attributes={"brightness": 99}
    )

    rows = await service.list_lights()

    assert len(rows) == 1
    assert rows[0]["on"] is None  # DB-only -- see SmartLightingService.list_lights docstring.


# --- Room / group fan-out -------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_room_controls_every_light_in_the_room(
    service: SmartLightingService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    room = await smart_home.create_room(home.id, "Living Room")
    lamp = await smart_home.register_discovered_device(
        home.id,
        "Lamp",
        device_type="light",
        room_id=room.id,
        external_id="light.lamp",
        metadata={"connector_type": "home_assistant"},
    )
    ceiling = await smart_home.register_discovered_device(
        home.id,
        "Ceiling Light",
        device_type="light",
        room_id=room.id,
        external_id="light.ceiling",
        metadata={"connector_type": "home_assistant"},
    )

    results = await service.apply_room(room.id, on=True)

    assert {r["device_id"] for r in results} == {lamp.id, ceiling.id}
    assert all(r["success"] for r in results)
    assert {c[0] for c in fake_connector.sent_commands} == {"light.lamp", "light.ceiling"}


@pytest.mark.asyncio
async def test_apply_room_isolates_a_per_device_fault(
    service: SmartLightingService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    """One light with no usable connector must not abort the rest of
    the room -- see module docstring's fan-out fault-isolation note."""
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    room = await smart_home.create_room(home.id, "Living Room")
    good = await smart_home.register_discovered_device(
        home.id,
        "Good Light",
        device_type="light",
        room_id=room.id,
        external_id="light.good",
        metadata={"connector_type": "home_assistant"},
    )
    broken = await smart_home.register_discovered_device(
        home.id, "Broken Light", device_type="light", room_id=room.id
    )  # no connector metadata

    results = await service.apply_room(room.id, on=True)

    by_id = {r["device_id"]: r for r in results}
    assert by_id[good.id]["success"] is True
    assert by_id[broken.id]["success"] is False


@pytest.mark.asyncio
async def test_apply_room_denied_without_permission_does_not_touch_any_light(
    service: SmartLightingService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    home = await smart_home.create_home("Primary Residence")
    room = await smart_home.create_room(home.id, "Living Room")
    await smart_home.register_discovered_device(
        home.id,
        "Lamp",
        device_type="light",
        room_id=room.id,
        external_id="light.lamp",
        metadata={"connector_type": "home_assistant"},
    )

    with pytest.raises(ServiceError, match="permission"):
        await service.apply_room(room.id, on=True)
    assert fake_connector.sent_commands == []


@pytest.mark.asyncio
async def test_apply_group_only_controls_light_members(
    service: SmartLightingService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    group = await smart_home.create_device_group(home.id, "Movie Night")
    light = await smart_home.register_discovered_device(
        home.id,
        "Lamp",
        device_type="light",
        external_id="light.lamp",
        metadata={"connector_type": "home_assistant"},
    )
    switch = await smart_home.register_discovered_device(
        home.id, "Projector Switch", device_type="switch", external_id="switch.projector"
    )
    await smart_home.add_device_to_group(group.id, light.id)
    await smart_home.add_device_to_group(group.id, switch.id)

    results = await service.apply_group(group.id, on=True)

    assert [r["device_id"] for r in results] == [light.id]


# --- Scenes ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_scene_requires_permission(
    service: SmartLightingService, smart_home: SmartHomeService
) -> None:
    home = await smart_home.create_home("Primary Residence")
    with pytest.raises(ServiceError, match="permission"):
        await service.create_scene(home.id, "Movie Night", [{"device_id": "x", "on": True}])


@pytest.mark.asyncio
async def test_create_scene_rejects_empty_targets(
    service: SmartLightingService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    with pytest.raises(ServiceError, match="at least one target"):
        await service.create_scene(home.id, "Movie Night", [])


@pytest.mark.asyncio
async def test_create_scene_rejects_target_with_no_attributes(
    service: SmartLightingService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    with pytest.raises(ServiceError, match="sets none of"):
        await service.create_scene(home.id, "Movie Night", [{"device_id": "light-1"}])


@pytest.mark.asyncio
async def test_scene_round_trip_and_apply(
    service: SmartLightingService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    home, device = await _home_and_light(smart_home, connectivity)

    scene = await service.create_scene(
        home.id, "Movie Night", [{"device_id": device.id, "on": True, "brightness": 20}]
    )
    assert scene["name"] == "Movie Night"
    assert scene["targets"] == [{"device_id": device.id, "on": True, "brightness": 20}]

    fetched = await service.get_scene(scene["id"])
    assert fetched is not None
    assert fetched["id"] == scene["id"]

    listed = await service.list_scenes(home_id=home.id)
    assert [s["id"] for s in listed] == [scene["id"]]

    results = await service.apply_scene(scene["id"])
    assert results == [{"device_id": device.id, "success": True, "detail": ""}]
    assert fake_connector.sent_commands == [
        ("light.living_room", "turn_on", {"brightness_pct": 20})
    ]

    assert await service.delete_scene(scene["id"]) is True
    assert await service.get_scene(scene["id"]) is None


@pytest.mark.asyncio
async def test_apply_unknown_scene_raises(
    service: SmartLightingService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    with pytest.raises(ServiceError, match="does not exist"):
        await service.apply_scene("no-such-scene")


# --- Cross-cutting invariants ----------------------------------------------------


def test_domain_layer_has_no_vendor_wire_format_leakage() -> None:
    """Home Assistant/MQTT field names (brightness_pct, rgb_color,
    color_temp_kelvin, set_state, ...) must live only in
    SmartLightingService's own translators -- never in the Smart Home
    domain layer this module reuses, per the Logic Contract's explicit
    "no vendor-specific wire-format logic in the domain model" rule."""
    import inspect

    from jarvis.domain.smart_home import models as domain_models
    from jarvis.services import smart_home_service

    source = inspect.getsource(domain_models) + inspect.getsource(smart_home_service)
    for leaked_term in ("brightness_pct", "rgb_color", "color_temp_kelvin", "set_state"):
        assert leaked_term not in source
