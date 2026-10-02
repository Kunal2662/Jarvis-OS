"""SirenService tests -- Milestone 12 Security & Safety (Siren
Integration Slice).

Real (temp-file) SQLite ``SmartHomeService`` and a real
``PermissionModel`` throughout, matching
``test_m12_smart_lock_service.py``'s own pattern -- only the connector
itself is faked (``FakeDeviceConnector``). Sirens live under the
generic ``device_type="other"`` bucket, discriminated by
``metadata["domain"]``/``["component"]`` -- see
``docs/M12_SECURITY_SIREN_INTEGRATION_LOGIC_CONTRACT.md`` §4.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core.connectivity.registry import ConnectorFactoryRegistry
from jarvis.core.events.event_bus import EventBus
from jarvis.core.exceptions import ServiceError
from jarvis.core.interfaces.connectivity import ConnectorNotConnectedError, DeviceState
from jarvis.core.plugins.permissions import PermissionModel
from jarvis.services.connectivity_service import ConnectivityService
from jarvis.services.siren_service import (
    SIREN_PRINCIPAL,
    SMART_HOME_SCOPE,
    SirenService,
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
) -> SirenService:
    return SirenService(smart_home=smart_home, connectivity=connectivity, permissions=permissions)


async def _grant(permissions: PermissionModel) -> None:
    await permissions.grant(SIREN_PRINCIPAL, SMART_HOME_SCOPE)


async def _home_and_siren(
    smart_home: SmartHomeService,
    *,
    connector_type: str = "home_assistant",
    domain_key: str = "domain",
):
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Front Yard Siren",
        device_type="other",
        external_id="siren.front_yard",
        metadata={"connector_type": connector_type, domain_key: "siren"},
    )
    return home, device


# --- Identity -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_permission_declared_pending_at_construction(permissions: PermissionModel) -> None:
    assert permissions.state(SIREN_PRINCIPAL, SMART_HOME_SCOPE).value == "pending"


@pytest.mark.asyncio
async def test_domain_key_identifies_a_siren(
    service: SirenService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_siren(smart_home, domain_key="domain")
    rows = await service.list_sirens()
    assert [r["id"] for r in rows] == [device.id]


@pytest.mark.asyncio
async def test_component_key_identifies_a_siren(
    service: SirenService, smart_home: SmartHomeService
) -> None:
    """MQTT Discovery-sourced devices carry ``component`` rather than
    ``domain`` -- see Logic Contract §4's fallback order."""
    _, device = await _home_and_siren(smart_home, connector_type="mqtt", domain_key="component")
    rows = await service.list_sirens()
    assert [r["id"] for r in rows] == [device.id]


@pytest.mark.asyncio
async def test_domain_takes_precedence_over_component(
    service: SirenService, smart_home: SmartHomeService
) -> None:
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Ambiguous Entity",
        device_type="other",
        external_id="other.ambiguous",
        metadata={"connector_type": "home_assistant", "domain": "siren", "component": "switch"},
    )
    state = await service.get_siren_state(device.id)
    assert state["id"] == device.id


@pytest.mark.asyncio
async def test_wrong_domain_is_rejected(
    service: SirenService, smart_home: SmartHomeService
) -> None:
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Motion Sensor",
        device_type="other",
        external_id="binary_sensor.motion",
        metadata={"connector_type": "home_assistant", "domain": "binary_sensor"},
    )
    with pytest.raises(ServiceError, match="not a siren"):
        await service.get_siren_state(device.id)


@pytest.mark.asyncio
async def test_missing_metadata_is_rejected(
    service: SirenService, smart_home: SmartHomeService
) -> None:
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id, "No Metadata", device_type="other"
    )
    with pytest.raises(ServiceError, match="not a siren"):
        await service.get_siren_state(device.id)


@pytest.mark.asyncio
async def test_other_device_types_are_rejected_even_with_siren_domain(
    service: SirenService, smart_home: SmartHomeService
) -> None:
    """``device_type`` must also be ``"other"`` -- a switch carrying a
    stray ``domain: siren`` in its metadata is not a siren."""
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Odd Switch",
        device_type="switch",
        external_id="switch.odd",
        metadata={"connector_type": "home_assistant", "domain": "siren"},
    )
    with pytest.raises(ServiceError, match="not a siren"):
        await service.get_siren_state(device.id)


@pytest.mark.asyncio
async def test_list_sirens_excludes_non_siren_other_devices(
    service: SirenService, smart_home: SmartHomeService
) -> None:
    home = await smart_home.create_home("Primary Residence")
    await smart_home.register_discovered_device(
        home.id,
        "Alarm Panel",
        device_type="other",
        external_id="alarm_control_panel.home",
        metadata={"connector_type": "home_assistant", "domain": "alarm_control_panel"},
    )
    _, siren = await _home_and_siren(smart_home)

    rows = await service.list_sirens()

    assert [r["id"] for r in rows] == [siren.id]


# --- Permission enforcement ----------------------------------------------------


@pytest.mark.asyncio
async def test_turn_on_denied_by_default(
    service: SirenService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_siren(smart_home)
    with pytest.raises(ServiceError, match="permission"):
        await service.turn_on(device.id)


@pytest.mark.asyncio
async def test_turn_off_denied_by_default(
    service: SirenService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_siren(smart_home)
    with pytest.raises(ServiceError, match="permission"):
        await service.turn_off(device.id)


@pytest.mark.asyncio
async def test_read_only_operations_do_not_require_permission(
    service: SirenService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_siren(smart_home)
    rows = await service.list_sirens()
    assert len(rows) == 1
    state = await service.get_siren_state(device.id)
    assert state["id"] == device.id


# --- Validation ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_turn_on_rejects_device_with_no_connector(
    service: SirenService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id, "Orphan Siren", device_type="other", metadata={"domain": "siren"}
    )
    with pytest.raises(ServiceError, match="no recorded connector"):
        await service.turn_on(device.id)


@pytest.mark.asyncio
async def test_turn_on_rejects_unsupported_connector_type(
    service: SirenService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    _, device = await _home_and_siren(smart_home, connector_type="zigbee")
    with pytest.raises(ServiceError, match="no command translation"):
        await service.turn_on(device.id)


@pytest.mark.asyncio
async def test_turn_on_unknown_device_raises(
    service: SirenService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    with pytest.raises(ServiceError):
        await service.turn_on("no-such-device")


# --- Home Assistant translation ------------------------------------------------


@pytest.mark.asyncio
async def test_ha_turn_on_translation(
    service: SirenService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_siren(smart_home)

    result = await service.turn_on(device.id)

    assert result["success"] is True
    assert fake_connector.sent_commands == [("siren.front_yard", "turn_on", {})]


@pytest.mark.asyncio
async def test_ha_turn_off_translation(
    service: SirenService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_siren(smart_home)

    result = await service.turn_off(device.id)

    assert result["success"] is True
    assert fake_connector.sent_commands == [("siren.front_yard", "turn_off", {})]


# --- MQTT translation -------------------------------------------------------------


@pytest.mark.asyncio
async def test_mqtt_turn_on_and_off_translation(
    smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    mqtt_connector = FakeDeviceConnector()
    mqtt_connector.connector_type = "mqtt"
    registry = ConnectorFactoryRegistry()
    registry.register("mqtt", lambda config: mqtt_connector)
    mqtt_connectivity = ConnectivityService(registry=registry, smart_home=smart_home)
    mqtt_service = SirenService(
        smart_home=smart_home, connectivity=mqtt_connectivity, permissions=permissions
    )
    await mqtt_connectivity.connect("mqtt")
    await _grant(permissions)
    _, device = await _home_and_siren(smart_home, connector_type="mqtt", domain_key="component")

    await mqtt_service.turn_on(device.id)
    await mqtt_service.turn_off(device.id)

    assert mqtt_connector.sent_commands == [
        ("siren.front_yard", "turn_on", {}),
        ("siren.front_yard", "turn_off", {}),
    ]


# --- Reads: live state merge ------------------------------------------------------


@pytest.mark.asyncio
async def test_get_siren_state_reports_on_true(
    service: SirenService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_siren(smart_home)
    fake_connector.states["siren.front_yard"] = DeviceState(
        external_id="siren.front_yard", status="on", attributes={}
    )

    state = await service.get_siren_state(device.id)

    assert state["on"] is True
    assert state["available"] is True


@pytest.mark.asyncio
async def test_get_siren_state_reports_on_false(
    service: SirenService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_siren(smart_home)
    fake_connector.states["siren.front_yard"] = DeviceState(
        external_id="siren.front_yard", status="off", attributes={}
    )

    state = await service.get_siren_state(device.id)

    assert state["on"] is False


@pytest.mark.asyncio
async def test_get_siren_state_reports_unavailable(
    service: SirenService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_siren(smart_home)
    fake_connector.states["siren.front_yard"] = DeviceState(
        external_id="siren.front_yard", status="unavailable", attributes={}
    )

    state = await service.get_siren_state(device.id)

    assert state["available"] is False
    assert state["on"] is None


@pytest.mark.asyncio
async def test_get_siren_state_falls_back_when_connector_unreachable(
    service: SirenService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_siren(smart_home)

    state = await service.get_siren_state(device.id)

    assert state["id"] == device.id
    assert state["on"] is None
    assert state["available"] is False


@pytest.mark.asyncio
async def test_list_sirens_does_not_make_a_live_connector_read(
    service: SirenService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _home_and_siren(smart_home)
    fake_connector.states["siren.front_yard"] = DeviceState(
        external_id="siren.front_yard", status="on", attributes={}
    )

    rows = await service.list_sirens()

    assert len(rows) == 1
    assert rows[0]["on"] is None  # DB-only -- see SirenService.list_sirens docstring.


# --- Security: no metadata_json leakage -------------------------------------------


@pytest.mark.asyncio
async def test_siren_payload_never_includes_raw_metadata_json(
    service: SirenService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_siren(smart_home)
    state = await service.get_siren_state(device.id)
    assert "metadata" not in state
    assert "metadata_json" not in state
    assert set(state.keys()) == {
        "id",
        "home_id",
        "room_id",
        "name",
        "status",
        "manufacturer",
        "model",
        "external_id",
        "on",
        "available",
    }


# --- Failure honesty ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_failed_command_reports_failure_not_success(
    service: SirenService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    fake_connector.next_command_succeeds = False
    _, device = await _home_and_siren(smart_home)

    result = await service.turn_on(device.id)

    assert result["success"] is False
    assert result["detail"]


@pytest.mark.asyncio
async def test_turn_on_is_not_deduplicated_when_called_twice(
    service: SirenService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_siren(smart_home)

    await service.turn_on(device.id)
    await service.turn_on(device.id)

    assert fake_connector.sent_commands == [
        ("siren.front_yard", "turn_on", {}),
        ("siren.front_yard", "turn_on", {}),
    ]


# --- Task Group W: advanced controls (tone / duration / volume_level) ---------------


@pytest.mark.asyncio
async def test_turn_on_bare_call_regression_still_sends_empty_payload(
    service: SirenService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    """Byte-for-byte pre-Task-Group-W behavior -- Logic Contract §22."""
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_siren(smart_home)

    result = await service.turn_on(device.id)

    assert result["success"] is True
    assert fake_connector.sent_commands == [("siren.front_yard", "turn_on", {})]


@pytest.mark.asyncio
async def test_turn_on_with_tone_only(
    service: SirenService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_siren(smart_home)
    fake_connector.states["siren.front_yard"] = DeviceState(
        external_id="siren.front_yard", status="off", attributes={}
    )

    await service.turn_on(device.id, tone="alarm")

    assert fake_connector.sent_commands == [("siren.front_yard", "turn_on", {"tone": "alarm"})]


@pytest.mark.asyncio
async def test_turn_on_with_duration_only(
    service: SirenService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_siren(smart_home)

    await service.turn_on(device.id, duration=30)

    assert fake_connector.sent_commands == [("siren.front_yard", "turn_on", {"duration": 30})]


@pytest.mark.asyncio
async def test_turn_on_with_volume_level_only(
    service: SirenService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_siren(smart_home)

    await service.turn_on(device.id, volume_level=0.5)

    assert fake_connector.sent_commands == [("siren.front_yard", "turn_on", {"volume_level": 0.5})]


@pytest.mark.asyncio
async def test_turn_on_with_all_three_combined(
    service: SirenService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_siren(smart_home)
    fake_connector.states["siren.front_yard"] = DeviceState(
        external_id="siren.front_yard", status="off", attributes={}
    )

    await service.turn_on(device.id, tone="alarm", duration=30, volume_level=0.5)

    assert fake_connector.sent_commands == [
        ("siren.front_yard", "turn_on", {"tone": "alarm", "duration": 30, "volume_level": 0.5})
    ]


@pytest.mark.asyncio
async def test_turn_off_never_carries_advanced_parameters(
    service: SirenService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    """`turn_off` has no advanced-control parameters at all -- HA's own
    `siren.turn_off` takes none (Logic Contract §7)."""
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_siren(smart_home)

    await service.turn_off(device.id)

    assert fake_connector.sent_commands == [("siren.front_yard", "turn_off", {})]


@pytest.mark.asyncio
async def test_mqtt_turn_on_translation_with_parameters(
    smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    mqtt_connector = FakeDeviceConnector()
    mqtt_connector.connector_type = "mqtt"
    registry = ConnectorFactoryRegistry()
    registry.register("mqtt", lambda config: mqtt_connector)
    mqtt_connectivity = ConnectivityService(registry=registry, smart_home=smart_home)
    mqtt_service = SirenService(
        smart_home=smart_home, connectivity=mqtt_connectivity, permissions=permissions
    )
    await mqtt_connectivity.connect("mqtt")
    await _grant(permissions)
    _, device = await _home_and_siren(smart_home, connector_type="mqtt", domain_key="component")
    mqtt_connector.states["siren.front_yard"] = DeviceState(
        external_id="siren.front_yard", status="off", attributes={}
    )

    await mqtt_service.turn_on(device.id, tone="alarm", duration=30, volume_level=0.5)

    assert mqtt_connector.sent_commands == [
        ("siren.front_yard", "turn_on", {"tone": "alarm", "duration": 30, "volume_level": 0.5})
    ]


# --- Task Group W: validation --------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_tone", [123, True, "", "   "])
async def test_tone_validation_rejects_bad_values(
    service: SirenService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    bad_tone,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_siren(smart_home)

    with pytest.raises(ServiceError, match="tone"):
        await service.turn_on(device.id, tone=bad_tone)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_duration", [True, "30", -1, 1.5])
async def test_duration_validation_rejects_bad_values(
    service: SirenService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    bad_duration,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_siren(smart_home)

    with pytest.raises(ServiceError, match="duration"):
        await service.turn_on(device.id, duration=bad_duration)


@pytest.mark.asyncio
async def test_duration_zero_is_accepted_not_rejected(
    service: SirenService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    """HA's own documentation defines no minimum-positive rule for
    duration -- 0 is passed through, never invented as an error (Logic
    Contract §9)."""
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_siren(smart_home)

    await service.turn_on(device.id, duration=0)

    assert fake_connector.sent_commands == [("siren.front_yard", "turn_on", {"duration": 0})]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_volume", [True, "0.5", -0.1, 1.1, float("nan"), float("inf"), float("-inf")]
)
async def test_volume_level_validation_rejects_bad_values(
    service: SirenService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    bad_volume,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_siren(smart_home)

    with pytest.raises(ServiceError, match="volume_level"):
        await service.turn_on(device.id, volume_level=bad_volume)


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary_volume", [0.0, 1.0])
async def test_volume_level_boundary_values_are_accepted(
    *,
    service: SirenService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
    boundary_volume: float,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_siren(smart_home)

    await service.turn_on(device.id, volume_level=boundary_volume)

    assert fake_connector.sent_commands == [
        ("siren.front_yard", "turn_on", {"volume_level": boundary_volume})
    ]


# --- Task Group W: tone live-capability check -----------------------------------------


@pytest.mark.asyncio
async def test_tone_accepted_when_device_reports_it_in_available_tones(
    service: SirenService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_siren(smart_home)
    fake_connector.states["siren.front_yard"] = DeviceState(
        external_id="siren.front_yard",
        status="off",
        attributes={"available_tones": ["alarm", "chime"]},
    )

    result = await service.turn_on(device.id, tone="alarm")

    assert result["success"] is True
    assert fake_connector.sent_commands == [("siren.front_yard", "turn_on", {"tone": "alarm"})]


@pytest.mark.asyncio
async def test_tone_rejected_when_not_in_devices_available_tones(
    service: SirenService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_siren(smart_home)
    fake_connector.states["siren.front_yard"] = DeviceState(
        external_id="siren.front_yard",
        status="off",
        attributes={"available_tones": ["alarm", "chime"]},
    )

    with pytest.raises(ServiceError, match="not supported"):
        await service.turn_on(device.id, tone="sunny_day")

    assert fake_connector.sent_commands == []


@pytest.mark.asyncio
async def test_tone_permissive_when_device_reports_no_available_tones(
    service: SirenService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    """Rejecting a real device over a vocabulary gap is the worse
    failure -- mirrors `MediaPlayerService._check_source`'s identical
    precedent (Logic Contract §9)."""
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_siren(smart_home)
    fake_connector.states["siren.front_yard"] = DeviceState(
        external_id="siren.front_yard", status="off", attributes={}
    )

    result = await service.turn_on(device.id, tone="anything")

    assert result["success"] is True
    assert fake_connector.sent_commands == [("siren.front_yard", "turn_on", {"tone": "anything"})]


@pytest.mark.asyncio
async def test_tone_permissive_when_connector_unreachable(
    service: SirenService,
    smart_home: SmartHomeService,
    permissions: PermissionModel,
) -> None:
    """No connector connected -- the live tone check itself is skipped
    entirely (`contextlib.suppress(ConnectivityError)`), never raising
    its own distinct error. The overall call still fails, but from the
    exact same downstream `send_command` step -- and with the exact
    same `ConnectorNotConnectedError` -- a bare, tone-less `turn_on()`
    would also raise in this scenario; the tone check adds no new
    failure mode of its own."""
    await _grant(permissions)
    _, device = await _home_and_siren(smart_home)

    with pytest.raises(ConnectorNotConnectedError):
        await service.turn_on(device.id, tone="anything")


# --- Task Group W: error semantics / regression safety -------------------------------


@pytest.mark.asyncio
async def test_unknown_device_with_parameters_still_raises(
    service: SirenService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    with pytest.raises(ServiceError):
        await service.turn_on("no-such-device", tone="alarm", duration=10, volume_level=0.5)


@pytest.mark.asyncio
async def test_non_siren_device_with_parameters_still_raises(
    service: SirenService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Odd Switch",
        device_type="switch",
        external_id="switch.odd",
        metadata={"connector_type": "home_assistant"},
    )
    with pytest.raises(ServiceError, match="not a siren"):
        await service.turn_on(device.id, tone="alarm")


@pytest.mark.asyncio
async def test_permission_denied_with_parameters_still_raises(
    service: SirenService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_siren(smart_home)
    with pytest.raises(ServiceError, match="permission"):
        await service.turn_on(device.id, tone="alarm", duration=10, volume_level=0.5)


@pytest.mark.asyncio
async def test_connector_failure_with_parameters_reports_failure_honestly(
    service: SirenService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    fake_connector.next_command_succeeds = False
    _, device = await _home_and_siren(smart_home)
    fake_connector.states["siren.front_yard"] = DeviceState(
        external_id="siren.front_yard", status="off", attributes={}
    )

    result = await service.turn_on(device.id, tone="alarm", duration=10, volume_level=0.5)

    assert result["success"] is False
    assert result["detail"]


@pytest.mark.asyncio
async def test_no_read_model_fabrication_from_advanced_controls(
    service: SirenService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    """`get_siren_state`'s own key set is unchanged -- no `tone`/
    `duration`/`volume_level`/`available_tones` key ever leaks into the
    persisted/read model (Logic Contract §15)."""
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_siren(smart_home)
    fake_connector.states["siren.front_yard"] = DeviceState(
        external_id="siren.front_yard",
        status="on",
        attributes={"available_tones": ["alarm", "chime"]},
    )

    await service.turn_on(device.id, tone="alarm", duration=10, volume_level=0.5)
    state = await service.get_siren_state(device.id)

    assert set(state.keys()) == {
        "id",
        "home_id",
        "room_id",
        "name",
        "status",
        "manufacturer",
        "model",
        "external_id",
        "on",
        "available",
    }
    assert "tone" not in state
    assert "duration" not in state
    assert "volume_level" not in state
    assert "available_tones" not in state


# --- Cross-cutting invariants -------------------------------------------------------


def _code_without_docstrings(module) -> str:
    """The module's source with every module/class/function docstring
    stripped, via a real AST transform -- not a source guard's own
    problem to fabricate false positives out of prose that *discusses*
    a forbidden term (this module's own docstrings, per Logic Contract
    §3/§4, explicitly discuss why it does *not* touch
    ``alarm_control_panel``/Panic Mode/EventBus -- see
    ``test_m12_security_service.py``'s own identical helper). What
    remains is real code: imports, attribute access, calls, literals --
    the only thing a "this symbol must not appear" guard should ever be
    checking."""
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(module))
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            if (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ):
                node.body.pop(0)
    return ast.unparse(tree)


def test_no_alarm_control_panel_or_panic_mode_coupling() -> None:
    from jarvis.services import siren_service

    code = _code_without_docstrings(siren_service)
    for forbidden_term in (
        "alarm_control_panel",
        "trigger_panic_mode",
        "trigger_vacation_mode",
        "EventBus",
        "Scheduler",
        "Analytics",
        "MemoryService",
    ):
        assert forbidden_term not in code
