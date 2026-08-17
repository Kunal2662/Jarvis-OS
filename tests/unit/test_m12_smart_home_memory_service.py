"""SmartHomeMemoryService tests -- Milestone 12 Smart Home Memory
(Manual/On-Demand Device Snapshot Slice).

Real (temp-file) SQLite ``SmartHomeService``, real
``SmartLightingService``/``SmartSwitchService``/``ThermostatService``,
a real ``MemoryService`` (with ``FakeLLM``/``FakeVectorStore`` in place
of network-backed embedding/vector infrastructure), and a real
``PermissionModel`` throughout -- only the device connector itself is
faked (``FakeDeviceConnector``), matching every prior M12 service
test's own pattern.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core.connectivity.registry import ConnectorFactoryRegistry
from jarvis.core.events.event_bus import EventBus
from jarvis.core.exceptions import ServiceError
from jarvis.core.interfaces.connectivity import DeviceState
from jarvis.core.plugins.permissions import PermissionModel
from jarvis.services.appliance_service import ApplianceService
from jarvis.services.connectivity_service import ConnectivityService
from jarvis.services.media_player_service import MediaPlayerService
from jarvis.services.memory_service import MemoryService
from jarvis.services.smart_home_memory_service import (
    SMART_HOME_MEMORY_PRINCIPAL,
    SMART_HOME_SCOPE,
    SNAPSHOT_MEMORY_TYPE,
    SmartHomeMemoryPermissionError,
    SmartHomeMemoryService,
    SnapshotNotFoundError,
    UnsupportedSnapshotCategoryError,
)
from jarvis.services.smart_home_service import SmartHomeService
from jarvis.services.smart_lighting_service import SmartLightingService
from jarvis.services.smart_switch_service import SmartSwitchService
from jarvis.services.thermostat_service import ThermostatService
from jarvis.services.vacuum_humidifier_service import VacuumHumidifierService
from jarvis.services.water_heater_service import WaterHeaterService
from tests.fakes.fake_device_connector import FakeDeviceConnector
from tests.fakes.fake_llm import FakeLLM
from tests.fakes.fake_vector_store import FakeVectorStore

_LIGHT_EXTERNAL_ID = "light.living_room"
_SWITCH_EXTERNAL_ID = "switch.kitchen"
_THERMOSTAT_EXTERNAL_ID = "climate.hallway"
_FAN_EXTERNAL_ID = "fan.bedroom"
_COVER_EXTERNAL_ID = "cover.garage"
_VACUUM_EXTERNAL_ID = "vacuum.living_room"
_HUMIDIFIER_EXTERNAL_ID = "humidifier.nursery"
_MEDIA_PLAYER_EXTERNAL_ID = "media_player.living_room"
_WATER_HEATER_EXTERNAL_ID = "water_heater.basement"


def _settings(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JARVIS_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'jarvis.db'}")
    monkeypatch.setenv("JARVIS_OPENAI_ENABLED", "false")
    monkeypatch.setenv("JARVIS_OLLAMA_ENABLED", "true")

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
        yield database, settings
    finally:
        await database.dispose()


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def smart_home(db, bus: EventBus) -> SmartHomeService:
    database, _ = db
    return SmartHomeService(database=database, event_bus=bus)


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
def smart_lighting(
    db,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
) -> SmartLightingService:
    database, _ = db
    return SmartLightingService(
        database=database,
        smart_home=smart_home,
        connectivity=connectivity,
        permissions=permissions,
    )


@pytest.fixture
def smart_switch(
    smart_home: SmartHomeService, connectivity: ConnectivityService, permissions: PermissionModel
) -> SmartSwitchService:
    return SmartSwitchService(
        smart_home=smart_home, connectivity=connectivity, permissions=permissions
    )


@pytest.fixture
def thermostats(
    smart_home: SmartHomeService, connectivity: ConnectivityService, permissions: PermissionModel
) -> ThermostatService:
    return ThermostatService(
        smart_home=smart_home, connectivity=connectivity, permissions=permissions
    )


@pytest.fixture
def appliances(
    smart_home: SmartHomeService, connectivity: ConnectivityService, permissions: PermissionModel
) -> ApplianceService:
    return ApplianceService(
        smart_home=smart_home, connectivity=connectivity, permissions=permissions
    )


@pytest.fixture
def vacuum_humidifier(
    smart_home: SmartHomeService, connectivity: ConnectivityService, permissions: PermissionModel
) -> VacuumHumidifierService:
    return VacuumHumidifierService(
        smart_home=smart_home, connectivity=connectivity, permissions=permissions
    )


@pytest.fixture
def media_players(
    smart_home: SmartHomeService, connectivity: ConnectivityService, permissions: PermissionModel
) -> MediaPlayerService:
    return MediaPlayerService(
        smart_home=smart_home, connectivity=connectivity, permissions=permissions
    )


@pytest.fixture
def water_heaters(
    smart_home: SmartHomeService, connectivity: ConnectivityService, permissions: PermissionModel
) -> WaterHeaterService:
    return WaterHeaterService(
        smart_home=smart_home, connectivity=connectivity, permissions=permissions
    )


@pytest.fixture
def memory(db) -> MemoryService:
    database, settings = db
    return MemoryService(
        database=database, vector_store=FakeVectorStore(), llm=FakeLLM(), settings=settings
    )


@pytest.fixture
def service(
    smart_home: SmartHomeService,
    smart_lighting: SmartLightingService,
    smart_switch: SmartSwitchService,
    thermostats: ThermostatService,
    appliances: ApplianceService,
    vacuum_humidifier: VacuumHumidifierService,
    media_players: MediaPlayerService,
    water_heaters: WaterHeaterService,
    memory: MemoryService,
    permissions: PermissionModel,
) -> SmartHomeMemoryService:
    return SmartHomeMemoryService(
        smart_home=smart_home,
        smart_lighting=smart_lighting,
        smart_switch=smart_switch,
        thermostats=thermostats,
        appliances=appliances,
        vacuum_humidifier=vacuum_humidifier,
        media_players=media_players,
        water_heaters=water_heaters,
        memory=memory,
        permissions=permissions,
    )


async def _grant(permissions: PermissionModel) -> None:
    await permissions.grant(SMART_HOME_MEMORY_PRINCIPAL, SMART_HOME_SCOPE)


async def _light(smart_home: SmartHomeService, *, room_id: str | None = None):
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Living Room Light",
        device_type="light",
        room_id=room_id,
        external_id=_LIGHT_EXTERNAL_ID,
        metadata={"connector_type": "home_assistant", "secret_token": "sh-abc123"},
    )
    return home, device


async def _switch(smart_home: SmartHomeService):
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Kitchen Switch",
        device_type="switch",
        external_id=_SWITCH_EXTERNAL_ID,
        metadata={"connector_type": "home_assistant"},
    )
    return home, device


async def _thermostat(smart_home: SmartHomeService):
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Hallway Thermostat",
        device_type="thermostat",
        external_id=_THERMOSTAT_EXTERNAL_ID,
        metadata={"connector_type": "home_assistant"},
    )
    return home, device


async def _appliance(
    smart_home: SmartHomeService,
    *,
    domain: str,
    external_id: str,
    name: str = "Appliance",
    home_id: str | None = None,
):
    """Registers one `device_type="appliance"` device carrying
    *domain* in its metadata -- the Tier-2 dispatch discriminator
    (Expansion Logic Contract §7)."""
    if home_id is None:
        home = await smart_home.create_home("Primary Residence")
        home_id = home.id
    return await smart_home.register_discovered_device(
        home_id,
        name,
        device_type="appliance",
        external_id=external_id,
        metadata={"connector_type": "home_assistant", "domain": domain},
    )


# --- Permission (Logic Contract §10) ------------------------------------------------


@pytest.mark.asyncio
async def test_permission_declared_pending_at_construction(permissions: PermissionModel) -> None:
    assert permissions.state(SMART_HOME_MEMORY_PRINCIPAL, SMART_HOME_SCOPE).value == "pending"


@pytest.mark.asyncio
async def test_snapshot_denied_without_grant(
    service: SmartHomeMemoryService, smart_home: SmartHomeService
) -> None:
    _, device = await _light(smart_home)
    with pytest.raises(SmartHomeMemoryPermissionError):
        await service.snapshot_device(device.id)


@pytest.mark.asyncio
async def test_list_snapshots_denied_without_grant(service: SmartHomeMemoryService) -> None:
    """Retrieval is gated too -- a deliberate departure from most M12
    modules' "reads ungated" precedent (Logic Contract §10)."""
    with pytest.raises(SmartHomeMemoryPermissionError):
        await service.list_snapshots()


@pytest.mark.asyncio
async def test_permission_checked_before_device_lookup(
    service: SmartHomeMemoryService, permissions: PermissionModel
) -> None:
    """Permission denied -> before any device lookup (Logic Contract
    §18) -- an unknown device id must not leak past an ungranted
    permission check as a different error."""
    with pytest.raises(SmartHomeMemoryPermissionError):
        await service.snapshot_device("no-such-device")


# --- Device-category scope (Logic Contract §5) ---------------------------------------


@pytest.mark.asyncio
async def test_unknown_device_raises_plain_service_error(
    service: SmartHomeMemoryService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    with pytest.raises(ServiceError) as exc_info:
        await service.snapshot_device("no-such-device")
    assert not isinstance(exc_info.value, UnsupportedSnapshotCategoryError)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "device_type,metadata",
    [
        ("sensor", {}),
        ("lock", {}),
        ("camera", {}),
        ("other", {}),
        # Siren lives in the shared "other" bucket, domain="siren" --
        # simply out of this task group's named scope (Expansion Logic
        # Contract §8), not privacy-excluded like sensor/lock.
        ("other", {"domain": "siren"}),
        # An "appliance"-typed device whose domain is NOT one of the
        # six supported categories must still be rejected -- proves
        # the Tier-2 cascade doesn't fall through to a false match.
        ("appliance", {"domain": "unknown_appliance_domain"}),
        ("appliance", {}),
    ],
)
async def test_unsupported_category_is_a_distinct_error(
    service: SmartHomeMemoryService,
    smart_home: SmartHomeService,
    permissions: PermissionModel,
    device_type: str,
    metadata: dict,
) -> None:
    """Sensors/Locks are excluded permanently on privacy/security
    grounds (Expansion Logic Contract §6); Siren/Camera are simply out
    of this task group's scope; an "appliance"-typed device with no
    matching domain is rejected, never falsely matched. All raise the
    same distinct `UnsupportedSnapshotCategoryError`, never a plain
    unknown-device `ServiceError`."""
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id, "Unsupported Device", device_type=device_type, external_id="x.y", metadata=metadata
    )
    with pytest.raises(UnsupportedSnapshotCategoryError, match="only supported for"):
        await service.snapshot_device(device.id)


# --- Snapshot creation: light / switch / thermostat -----------------------------------


@pytest.mark.asyncio
async def test_snapshot_light_captures_verbatim_state(
    service: SmartHomeMemoryService,
    smart_home: SmartHomeService,
    smart_lighting: SmartLightingService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _light(smart_home)
    fake_connector.states[_LIGHT_EXTERNAL_ID] = DeviceState(
        external_id=_LIGHT_EXTERNAL_ID,
        status="on",
        attributes={"brightness": 80, "color_temp_kelvin": 3000},
    )
    expected_state = await smart_lighting.get_light_state(device.id)

    result = await service.snapshot_device(device.id)

    assert result["device_id"] == device.id
    assert result["device_type"] == "light"
    assert result["memory_id"]
    assert result["snapshot_at"]

    rows = await service.list_snapshots(device_id=device.id)
    assert len(rows) == 1
    assert rows[0]["state"] == expected_state
    assert rows[0]["device_type"] == "light"
    assert rows[0]["home_id"] == device.home_id


@pytest.mark.asyncio
async def test_snapshot_switch_captures_verbatim_state(
    service: SmartHomeMemoryService,
    smart_home: SmartHomeService,
    smart_switch: SmartSwitchService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _switch(smart_home)
    fake_connector.states[_SWITCH_EXTERNAL_ID] = DeviceState(
        external_id=_SWITCH_EXTERNAL_ID, status="on", attributes={}
    )
    expected_state = await smart_switch.get_switch_state(device.id)

    result = await service.snapshot_device(device.id)

    assert result["device_type"] == "switch"
    rows = await service.list_snapshots(device_id=device.id)
    assert rows[0]["state"] == expected_state


@pytest.mark.asyncio
async def test_snapshot_thermostat_captures_verbatim_state(
    service: SmartHomeMemoryService,
    smart_home: SmartHomeService,
    thermostats: ThermostatService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _thermostat(smart_home)
    fake_connector.states[_THERMOSTAT_EXTERNAL_ID] = DeviceState(
        external_id=_THERMOSTAT_EXTERNAL_ID,
        status="heat",
        attributes={"current_temperature": 20.0, "temperature": 21.5},
    )
    expected_state = await thermostats.get_thermostat_state(device.id)

    result = await service.snapshot_device(device.id)

    assert result["device_type"] == "thermostat"
    rows = await service.list_snapshots(device_id=device.id)
    assert rows[0]["state"] == expected_state


# --- Snapshot creation: appliance-domain categories (Expansion Logic Contract §7/§8) ---


@pytest.mark.asyncio
async def test_snapshot_fan_captures_verbatim_state(
    service: SmartHomeMemoryService,
    smart_home: SmartHomeService,
    appliances: ApplianceService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    device = await _appliance(smart_home, domain="fan", external_id=_FAN_EXTERNAL_ID, name="Fan")
    fake_connector.states[_FAN_EXTERNAL_ID] = DeviceState(
        external_id=_FAN_EXTERNAL_ID, status="on", attributes={}
    )
    expected_state = await appliances.get_fan_state(device.id)

    result = await service.snapshot_device(device.id)

    assert result["device_type"] == "appliance"
    rows = await service.list_snapshots(device_id=device.id)
    assert rows[0]["state"] == expected_state


@pytest.mark.asyncio
async def test_snapshot_cover_captures_verbatim_state(
    service: SmartHomeMemoryService,
    smart_home: SmartHomeService,
    appliances: ApplianceService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    device = await _appliance(
        smart_home, domain="cover", external_id=_COVER_EXTERNAL_ID, name="Cover"
    )
    fake_connector.states[_COVER_EXTERNAL_ID] = DeviceState(
        external_id=_COVER_EXTERNAL_ID, status="open", attributes={}
    )
    expected_state = await appliances.get_cover_state(device.id)

    result = await service.snapshot_device(device.id)

    assert result["device_type"] == "appliance"
    rows = await service.list_snapshots(device_id=device.id)
    assert rows[0]["state"] == expected_state


@pytest.mark.asyncio
async def test_snapshot_vacuum_captures_verbatim_state(
    service: SmartHomeMemoryService,
    smart_home: SmartHomeService,
    vacuum_humidifier: VacuumHumidifierService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    device = await _appliance(
        smart_home, domain="vacuum", external_id=_VACUUM_EXTERNAL_ID, name="Vacuum"
    )
    fake_connector.states[_VACUUM_EXTERNAL_ID] = DeviceState(
        external_id=_VACUUM_EXTERNAL_ID, status="cleaning", attributes={"battery_level": 80}
    )
    expected_state = await vacuum_humidifier.get_vacuum_state(device.id)

    result = await service.snapshot_device(device.id)

    assert result["device_type"] == "appliance"
    rows = await service.list_snapshots(device_id=device.id)
    assert rows[0]["state"] == expected_state


@pytest.mark.asyncio
async def test_snapshot_humidifier_captures_verbatim_state(
    service: SmartHomeMemoryService,
    smart_home: SmartHomeService,
    vacuum_humidifier: VacuumHumidifierService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    device = await _appliance(
        smart_home, domain="humidifier", external_id=_HUMIDIFIER_EXTERNAL_ID, name="Humidifier"
    )
    fake_connector.states[_HUMIDIFIER_EXTERNAL_ID] = DeviceState(
        external_id=_HUMIDIFIER_EXTERNAL_ID, status="on", attributes={"current_humidity": 45}
    )
    expected_state = await vacuum_humidifier.get_humidifier_state(device.id)

    result = await service.snapshot_device(device.id)

    assert result["device_type"] == "appliance"
    rows = await service.list_snapshots(device_id=device.id)
    assert rows[0]["state"] == expected_state


@pytest.mark.asyncio
async def test_snapshot_media_player_captures_verbatim_state(
    service: SmartHomeMemoryService,
    smart_home: SmartHomeService,
    media_players: MediaPlayerService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    device = await _appliance(
        smart_home, domain="media_player", external_id=_MEDIA_PLAYER_EXTERNAL_ID, name="TV"
    )
    fake_connector.states[_MEDIA_PLAYER_EXTERNAL_ID] = DeviceState(
        external_id=_MEDIA_PLAYER_EXTERNAL_ID,
        status="playing",
        attributes={"media_title": "A Song", "media_artist": "A Band"},
    )
    expected_state = await media_players.get_media_player_state(device.id)

    result = await service.snapshot_device(device.id)

    assert result["device_type"] == "appliance"
    rows = await service.list_snapshots(device_id=device.id)
    assert rows[0]["state"] == expected_state


@pytest.mark.asyncio
async def test_snapshot_water_heater_captures_verbatim_state(
    service: SmartHomeMemoryService,
    smart_home: SmartHomeService,
    water_heaters: WaterHeaterService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    device = await _appliance(
        smart_home,
        domain="water_heater",
        external_id=_WATER_HEATER_EXTERNAL_ID,
        name="Water Heater",
    )
    fake_connector.states[_WATER_HEATER_EXTERNAL_ID] = DeviceState(
        external_id=_WATER_HEATER_EXTERNAL_ID,
        status="eco",
        attributes={"current_temperature": 48.0, "temperature": 50.0},
    )
    expected_state = await water_heaters.get_water_heater_state(device.id)

    result = await service.snapshot_device(device.id)

    assert result["device_type"] == "appliance"
    rows = await service.list_snapshots(device_id=device.id)
    assert rows[0]["state"] == expected_state


@pytest.mark.asyncio
async def test_appliance_dispatch_never_falsely_matches_another_category(
    service: SmartHomeMemoryService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    """A water heater (last in the Tier-2 cascade order) must resolve
    to its own state, not silently succeed against an earlier
    candidate reader (Expansion Logic Contract §7's "why this is safe
    to catch broadly" reasoning, proven behaviorally)."""
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    device = await _appliance(
        smart_home,
        domain="water_heater",
        external_id=_WATER_HEATER_EXTERNAL_ID,
        name="Water Heater",
    )
    fake_connector.states[_WATER_HEATER_EXTERNAL_ID] = DeviceState(
        external_id=_WATER_HEATER_EXTERNAL_ID, status="off", attributes={}
    )

    result = await service.snapshot_device(device.id)

    rows = await service.list_snapshots(device_id=device.id)
    assert rows[0]["state"]["operation_mode"] == "off"
    assert "battery_level" not in rows[0]["state"]  # a vacuum-only field
    assert "volume_level" not in rows[0]["state"]  # a media_player-only field
    assert result["memory_id"]


# --- Unavailable device honesty (Logic Contract §18/§20) ------------------------------


@pytest.mark.asyncio
async def test_unavailable_device_still_produces_honest_snapshot(
    service: SmartHomeMemoryService,
    smart_home: SmartHomeService,
    permissions: PermissionModel,
) -> None:
    """No connector connected -- the light read falls back to
    available/unknown fields rather than raising, and the snapshot must
    still be created, capturing that honestly (never fabricated, never
    silently skipped)."""
    await _grant(permissions)
    _, device = await _light(smart_home)

    result = await service.snapshot_device(device.id)

    rows = await service.list_snapshots(device_id=device.id)
    assert len(rows) == 1
    assert rows[0]["state"]["on"] is None
    assert result["memory_id"]


# --- No fabricated / leaked data (Logic Contract §17B/§20) ----------------------------


@pytest.mark.asyncio
async def test_snapshot_never_leaks_device_metadata_json_secrets(
    service: SmartHomeMemoryService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    """`_light`'s fixture device carries a `secret_token` in
    `Device.metadata_json` -- the snapshot must never surface it,
    because metadata/content are built only from the owning service's
    own normalized read model, never from `Device.metadata_json`
    directly."""
    await _grant(permissions)
    _, device = await _light(smart_home)

    await service.snapshot_device(device.id)

    rows = await service.list_snapshots(device_id=device.id)
    assert "sh-abc123" not in str(rows[0])
    assert "secret_token" not in str(rows[0])
    assert "connector_type" not in rows[0]["state"]


@pytest.mark.asyncio
async def test_snapshot_at_is_close_to_now(
    service: SmartHomeMemoryService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    from datetime import UTC, datetime

    await _grant(permissions)
    _, device = await _light(smart_home)
    before = datetime.now(UTC)

    result = await service.snapshot_device(device.id)

    after = datetime.now(UTC)
    snapshot_at = datetime.fromisoformat(result["snapshot_at"])
    assert before <= snapshot_at <= after


# --- Memory representation (Logic Contract §6) -----------------------------------------


@pytest.mark.asyncio
async def test_memory_type_and_source_are_device_snapshot(
    service: SmartHomeMemoryService,
    smart_home: SmartHomeService,
    memory: MemoryService,
    permissions: PermissionModel,
) -> None:
    await _grant(permissions)
    _, device = await _light(smart_home)

    result = await service.snapshot_device(device.id)

    records = await memory.browse(memory_type=SNAPSHOT_MEMORY_TYPE)
    match = next(r for r in records if r.id == result["memory_id"])
    assert match.memory_type == SNAPSHOT_MEMORY_TYPE
    assert match.source == SNAPSHOT_MEMORY_TYPE


# --- Retrieval (Logic Contract §7) ------------------------------------------------------


@pytest.mark.asyncio
async def test_list_snapshots_empty_by_default(
    service: SmartHomeMemoryService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    assert await service.list_snapshots() == []


@pytest.mark.asyncio
async def test_list_snapshots_filters_by_device_id(
    service: SmartHomeMemoryService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    _, light = await _light(smart_home)
    _, switch = await _switch(smart_home)
    await service.snapshot_device(light.id)
    await service.snapshot_device(switch.id)

    light_only = await service.list_snapshots(device_id=light.id)
    assert len(light_only) == 1
    assert light_only[0]["device_id"] == light.id

    switch_only = await service.list_snapshots(device_id=switch.id)
    assert len(switch_only) == 1
    assert switch_only[0]["device_id"] == switch.id

    everything = await service.list_snapshots()
    assert len(everything) == 2


@pytest.mark.asyncio
async def test_list_snapshots_respects_limit(
    service: SmartHomeMemoryService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    _, light = await _light(smart_home)
    for _ in range(3):
        await service.snapshot_device(light.id)

    rows = await service.list_snapshots(limit=2)
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_list_snapshots_most_recent_first(
    service: SmartHomeMemoryService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    _, light = await _light(smart_home)
    first = await service.snapshot_device(light.id)
    second = await service.snapshot_device(light.id)

    rows = await service.list_snapshots(device_id=light.id)

    assert rows[0]["memory_id"] == second["memory_id"]
    assert rows[1]["memory_id"] == first["memory_id"]


@pytest.mark.asyncio
async def test_list_snapshots_unknown_device_returns_empty_not_error(
    service: SmartHomeMemoryService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    assert await service.list_snapshots(device_id="no-such-device") == []


# --- Deletion (Expansion Logic Contract §12) --------------------------------------------


@pytest.mark.asyncio
async def test_delete_denied_without_grant(
    service: SmartHomeMemoryService, permissions: PermissionModel
) -> None:
    with pytest.raises(SmartHomeMemoryPermissionError):
        await service.delete_snapshot("no-such-id")


@pytest.mark.asyncio
async def test_delete_valid_snapshot_succeeds_and_disappears_from_list(
    service: SmartHomeMemoryService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    _, device = await _light(smart_home)
    created = await service.snapshot_device(device.id)

    result = await service.delete_snapshot(created["memory_id"])

    assert result == {"memory_id": created["memory_id"], "deleted": True}
    assert await service.list_snapshots(device_id=device.id) == []


@pytest.mark.asyncio
async def test_delete_unknown_id_raises_snapshot_not_found(
    service: SmartHomeMemoryService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    with pytest.raises(SnapshotNotFoundError):
        await service.delete_snapshot("no-such-memory-id")


@pytest.mark.asyncio
async def test_delete_already_deleted_snapshot_raises_snapshot_not_found(
    service: SmartHomeMemoryService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    _, device = await _light(smart_home)
    created = await service.snapshot_device(device.id)
    await service.delete_snapshot(created["memory_id"])

    with pytest.raises(SnapshotNotFoundError):
        await service.delete_snapshot(created["memory_id"])


@pytest.mark.asyncio
async def test_delete_cannot_remove_a_non_snapshot_memory(
    service: SmartHomeMemoryService, memory: MemoryService, permissions: PermissionModel
) -> None:
    """A caller holding only this module's own grant must never be
    able to delete an unrelated memory record through this API
    (Expansion Logic Contract §12)."""
    await _grant(permissions)
    unrelated_id = await memory.remember("An unrelated conversation memory.", source="user")

    with pytest.raises(SnapshotNotFoundError):
        await service.delete_snapshot(unrelated_id)

    records = await memory.browse()
    assert any(r.id == unrelated_id for r in records)  # still there, untouched


# --- Home-wide snapshot (Expansion Logic Contract §13) -----------------------------------


@pytest.mark.asyncio
async def test_snapshot_home_denied_without_grant(
    service: SmartHomeMemoryService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    home = await smart_home.create_home("Primary Residence")
    with pytest.raises(SmartHomeMemoryPermissionError):
        await service.snapshot_home(home.id)


@pytest.mark.asyncio
async def test_snapshot_home_unknown_home_raises(
    service: SmartHomeMemoryService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    with pytest.raises(ServiceError):
        await service.snapshot_home("no-such-home")


@pytest.mark.asyncio
async def test_snapshot_home_empty_home_returns_zero_counts(
    service: SmartHomeMemoryService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    home = await smart_home.create_home("Empty Residence")

    result = await service.snapshot_home(home.id)

    assert result["home_id"] == home.id
    assert result["requested_count"] == 0
    assert result["attempted_count"] == 0
    assert result["succeeded_count"] == 0
    assert result["failed_count"] == 0
    assert result["skipped_count"] == 0
    assert result["results"] == []


@pytest.mark.asyncio
async def test_snapshot_home_all_supported_devices_succeed(
    service: SmartHomeMemoryService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    light = await smart_home.register_discovered_device(
        home.id,
        "Light",
        device_type="light",
        external_id=_LIGHT_EXTERNAL_ID,
        metadata={"connector_type": "home_assistant"},
    )
    fan = await _appliance(smart_home, domain="fan", external_id=_FAN_EXTERNAL_ID, home_id=home.id)
    fake_connector.states[_LIGHT_EXTERNAL_ID] = DeviceState(
        external_id=_LIGHT_EXTERNAL_ID, status="on", attributes={}
    )
    fake_connector.states[_FAN_EXTERNAL_ID] = DeviceState(
        external_id=_FAN_EXTERNAL_ID, status="on", attributes={}
    )

    result = await service.snapshot_home(home.id)

    assert result["requested_count"] == 2
    assert result["attempted_count"] == 2
    assert result["succeeded_count"] == 2
    assert result["failed_count"] == 0
    assert result["skipped_count"] == 0
    assert {r["device_id"] for r in result["results"]} == {light.id, fan.id}
    assert all(r["outcome"] == "succeeded" and r["memory_id"] for r in result["results"])
    persisted = await service.list_snapshots()
    assert len(persisted) == 2


@pytest.mark.asyncio
async def test_snapshot_home_skips_unsupported_categories(
    service: SmartHomeMemoryService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    sensor = await smart_home.register_discovered_device(
        home.id, "Motion Sensor", device_type="sensor", external_id="sensor.motion"
    )
    lock = await smart_home.register_discovered_device(
        home.id, "Front Door", device_type="lock", external_id="lock.front_door"
    )

    result = await service.snapshot_home(home.id)

    assert result["requested_count"] == 2
    assert result["attempted_count"] == 0
    assert result["skipped_count"] == 2
    assert result["succeeded_count"] == 0
    outcomes = {r["device_id"]: r["outcome"] for r in result["results"]}
    assert outcomes[sensor.id] == "skipped"
    assert outcomes[lock.id] == "skipped"
    assert await service.list_snapshots() == []


@pytest.mark.asyncio
async def test_snapshot_home_unavailable_device_handled_honestly(
    service: SmartHomeMemoryService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    """No connector connected -- the device is still snapshotted,
    honestly capturing `available: false`/`None`, never skipped and
    never fabricated (mirrors single-device behavior)."""
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    light = await smart_home.register_discovered_device(
        home.id,
        "Light",
        device_type="light",
        external_id=_LIGHT_EXTERNAL_ID,
        metadata={"connector_type": "home_assistant"},
    )

    result = await service.snapshot_home(home.id)

    assert result["succeeded_count"] == 1
    snapshot = (await service.list_snapshots(device_id=light.id))[0]
    assert snapshot["state"]["on"] is None


@pytest.mark.asyncio
async def test_snapshot_home_one_device_failure_does_not_abort_batch(
    service: SmartHomeMemoryService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
    monkeypatch,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    broken = await smart_home.register_discovered_device(
        home.id,
        "Broken Light",
        device_type="light",
        external_id="light.broken",
        metadata={"connector_type": "home_assistant"},
    )
    healthy = await smart_home.register_discovered_device(
        home.id,
        "Healthy Switch",
        device_type="switch",
        external_id=_SWITCH_EXTERNAL_ID,
        metadata={"connector_type": "home_assistant"},
    )
    fake_connector.states[_SWITCH_EXTERNAL_ID] = DeviceState(
        external_id=_SWITCH_EXTERNAL_ID, status="on", attributes={}
    )

    original_remember = service._memory.remember

    async def _flaky_remember(content, **kwargs):
        if kwargs.get("metadata", {}).get("device_id") == broken.id:
            raise RuntimeError("simulated persistence failure")
        return await original_remember(content, **kwargs)

    monkeypatch.setattr(service._memory, "remember", _flaky_remember)

    result = await service.snapshot_home(home.id)

    assert result["requested_count"] == 2
    assert result["attempted_count"] == 2
    assert result["succeeded_count"] == 1
    assert result["failed_count"] == 1
    outcomes = {r["device_id"]: r for r in result["results"]}
    assert outcomes[broken.id]["outcome"] == "failed"
    assert outcomes[broken.id]["detail"]
    assert outcomes[healthy.id]["outcome"] == "succeeded"


@pytest.mark.asyncio
async def test_snapshot_home_result_ordering_matches_list_devices(
    service: SmartHomeMemoryService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    first = await smart_home.register_discovered_device(
        home.id,
        "Light",
        device_type="light",
        external_id=_LIGHT_EXTERNAL_ID,
        metadata={"connector_type": "home_assistant"},
    )
    second = await smart_home.register_discovered_device(
        home.id,
        "Switch",
        device_type="switch",
        external_id=_SWITCH_EXTERNAL_ID,
        metadata={"connector_type": "home_assistant"},
    )

    expected_order = [d.id for d in await smart_home.list_devices(home_id=home.id)]
    result = await service.snapshot_home(home.id)

    assert [r["device_id"] for r in result["results"]] == expected_order
    assert set(expected_order) == {first.id, second.id}


@pytest.mark.asyncio
async def test_snapshot_home_never_sends_a_device_command(
    service: SmartHomeMemoryService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    """Read-only against devices -- the basis for the no-confirmation
    decision (Expansion Logic Contract §15)."""
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    await smart_home.register_discovered_device(
        home.id,
        "Light",
        device_type="light",
        external_id=_LIGHT_EXTERNAL_ID,
        metadata={"connector_type": "home_assistant"},
    )

    await service.snapshot_home(home.id)

    assert fake_connector.sent_commands == []


# --- Cross-cutting invariants (Logic Contract §12/§13/§14/§21) ------------------------
#
# These guards scan the module's *code*, not its docstrings -- the
# module docstring itself explains, in prose, everything this slice
# deliberately does NOT do (EventBus, Scheduler, automatic history,
# ...), which would otherwise collide with a naive whole-source scan.
# `_code_without_docstrings` strips every module/function/class
# docstring via an AST transform before re-serializing, so these tests
# check actual code, never explanatory prose.


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

    from jarvis.services import smart_home_memory_service

    return _code_without_docstrings(inspect.getsource(smart_home_memory_service))


def test_service_has_no_eventbus_reference() -> None:
    source = _service_code()
    assert "event_bus" not in source
    assert "EventBus" not in source


def test_service_has_no_scheduler_reference() -> None:
    source = _service_code()
    assert "Scheduler" not in source
    assert "schedule" not in source.lower()


def test_service_has_no_analytics_reference() -> None:
    source = _service_code()
    assert "Analytics" not in source
    assert "trend" not in source.lower()


def test_service_does_not_import_connectors_directly() -> None:
    import inspect

    from jarvis.services import smart_home_memory_service

    import_lines = [
        line
        for line in inspect.getsource(smart_home_memory_service).splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    joined = "\n".join(import_lines)
    assert "HomeAssistantConnector" not in joined
    assert "MqttConnector" not in joined
    assert "ConnectivityService" not in joined


def test_deletion_is_scoped_never_generic() -> None:
    """`delete_snapshot` (Task Group S) is real, approved scope -- but
    it must only ever appear alongside its own scoping check
    (`browse(memory_type=`), never as a bare pass-through to
    `MemoryService.forget()` with no prior lookup (Expansion Logic
    Contract §12)."""
    source = _service_code()
    assert "forget" in source  # deletion tooling IS expected now (Task Group S)
    assert "async def delete_snapshot" in source
    assert "browse(memory_type=SNAPSHOT_MEMORY_TYPE" in source


def test_no_deferred_functionality_exists() -> None:
    """Every item in the Expansion Logic Contract's own §27 deferred
    table must have no corresponding code path here. `home_wide`/
    `batch_snapshot` are deliberately absent from this list -- Task
    Group S makes both real, approved scope, not deferred."""
    source = _service_code().lower()
    for deferred_term in (
        "automatic_history",
        "continuous",
        "predict",
        "notification",
        "alarm_control_panel",
        "eventbus",
    ):
        assert deferred_term not in source
    # Sensor/Lock must never appear as *supported* device_type keys --
    # this is a structural check (dict key literal), not a prose scan.
    assert '"sensor":' not in source
    assert '"lock":' not in source
