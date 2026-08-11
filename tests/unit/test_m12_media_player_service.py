"""MediaPlayerService tests -- Milestone 12 Appliance Control (Media
Player Core Slice).

Real (temp-file) SQLite ``SmartHomeService`` and a real
``PermissionModel`` throughout, matching
``test_m12_vacuum_humidifier_service.py``'s own pattern -- only the
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
from jarvis.services.media_player_service import (
    MEDIA_PLAYER_PRINCIPAL,
    SMART_HOME_SCOPE,
    MediaPlayerService,
    _translate_state_home_assistant,
    _translate_state_mqtt,
    _translate_transport_home_assistant,
    _translate_transport_mqtt,
)
from jarvis.services.smart_home_service import SmartHomeService
from tests.fakes.fake_device_connector import FakeDeviceConnector

_EXTERNAL_ID = "media_player.living_room"


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
) -> MediaPlayerService:
    return MediaPlayerService(
        smart_home=smart_home, connectivity=connectivity, permissions=permissions
    )


async def _grant(permissions: PermissionModel) -> None:
    await permissions.grant(MEDIA_PLAYER_PRINCIPAL, SMART_HOME_SCOPE)


async def _home_and_media_player(
    smart_home: SmartHomeService,
    *,
    external_id: str = _EXTERNAL_ID,
    connector_type: str = "home_assistant",
    metadata_key: str = "domain",
):
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Living Room Speaker",
        device_type="appliance",
        external_id=external_id,
        metadata={"connector_type": connector_type, metadata_key: "media_player"},
    )
    return home, device


def _state(
    *,
    status: str = "playing",
    attributes: dict | None = None,
    external_id: str = _EXTERNAL_ID,
) -> DeviceState:
    return DeviceState(external_id=external_id, status=status, attributes=attributes or {})


# --- Domain discrimination (Logic Contract §2) --------------------------------------


@pytest.mark.asyncio
async def test_domain_key_resolves_via_domain(
    service: MediaPlayerService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_media_player(smart_home, metadata_key="domain")
    state = await service.get_media_player_state(device.id)
    assert state["id"] == device.id


@pytest.mark.asyncio
async def test_domain_key_falls_back_to_component(
    service: MediaPlayerService, smart_home: SmartHomeService
) -> None:
    """MQTT HA-Discovery-sourced devices carry metadata["component"],
    not metadata["domain"] -- this must still resolve correctly
    (Logic Contract §2)."""
    _, device = await _home_and_media_player(
        smart_home, connector_type="mqtt", metadata_key="component"
    )
    state = await service.get_media_player_state(device.id)
    assert state["id"] == device.id


@pytest.mark.asyncio
async def test_domain_preferred_over_component_when_both_present(
    service: MediaPlayerService, smart_home: SmartHomeService
) -> None:
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Speaker",
        device_type="appliance",
        external_id=_EXTERNAL_ID,
        metadata={"domain": "media_player", "component": "switch"},
    )
    state = await service.get_media_player_state(device.id)
    assert state["id"] == device.id


@pytest.mark.asyncio
async def test_missing_domain_and_component_is_rejected(
    service: MediaPlayerService, smart_home: SmartHomeService
) -> None:
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id, "Mystery Appliance", device_type="appliance", external_id="appliance.mystery"
    )
    with pytest.raises(ServiceError, match="not a media player"):
        await service.get_media_player_state(device.id)


@pytest.mark.asyncio
async def test_wrong_component_is_rejected(
    service: MediaPlayerService, smart_home: SmartHomeService
) -> None:
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Vacuum",
        device_type="appliance",
        external_id="vacuum.x",
        metadata={"component": "vacuum"},
    )
    with pytest.raises(ServiceError, match="not a media player"):
        await service.get_media_player_state(device.id)


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
    ],
)
async def test_rejects_every_foreign_type_and_domain(
    service: MediaPlayerService,
    smart_home: SmartHomeService,
    permissions: PermissionModel,
    device_type: str,
    metadata: dict,
) -> None:
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id, "Not A Media Player", device_type=device_type, external_id="x.y", metadata=metadata
    )
    with pytest.raises(ServiceError, match="not a media player"):
        await service.get_media_player_state(device.id)
    with pytest.raises(ServiceError, match="not a media player"):
        await service.play(device.id)


@pytest.mark.asyncio
async def test_unknown_device_raises(
    service: MediaPlayerService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    with pytest.raises(ServiceError):
        await service.get_media_player_state("no-such-device")


# --- Reads are ungated ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_reads_are_ungated(service: MediaPlayerService, smart_home: SmartHomeService) -> None:
    await _home_and_media_player(smart_home)
    rows = await service.list_media_players()
    assert len(rows) == 1
    state = await service.get_media_player_state(rows[0]["id"])
    assert state["id"] == rows[0]["id"]


@pytest.mark.asyncio
async def test_permission_declared_pending_at_construction(permissions: PermissionModel) -> None:
    assert permissions.state(MEDIA_PLAYER_PRINCIPAL, SMART_HOME_SCOPE).value == "pending"


@pytest.mark.asyncio
async def test_transport_denied_without_grant(
    service: MediaPlayerService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_media_player(smart_home)
    with pytest.raises(ServiceError, match="permission"):
        await service.play(device.id)


@pytest.mark.asyncio
async def test_state_mutation_denied_without_grant(
    service: MediaPlayerService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_media_player(smart_home)
    with pytest.raises(ServiceError, match="permission"):
        await service.set_media_player_state(device.id, volume=0.5)


# --- State normalization ----------------------------------------------------------


@pytest.mark.asyncio
async def test_full_state_normalization(
    service: MediaPlayerService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_media_player(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(
        status="playing",
        attributes={
            "volume_level": 0.6,
            "is_volume_muted": False,
            "source": "Spotify",
            "source_list": ["Spotify", "HDMI 1"],
            "media_title": "Song Title",
            "media_artist": "Artist Name",
        },
    )

    state = await service.get_media_player_state(device.id)

    assert state["available"] is True
    assert state["state"] == "playing"
    assert state["volume_level"] == 0.6
    assert state["is_volume_muted"] is False
    assert state["source"] == "Spotify"
    assert state["source_list"] == ["Spotify", "HDMI 1"]
    assert state["media_title"] == "Song Title"
    assert state["media_artist"] == "Artist Name"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw_status", ["playing", "paused", "idle", "standby", "buffering", "on", "off"]
)
async def test_playback_state_is_open_pass_through(
    service: MediaPlayerService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
    raw_status: str,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_media_player(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(status=raw_status)

    state = await service.get_media_player_state(device.id)

    assert state["state"] == raw_status


@pytest.mark.asyncio
async def test_unknown_state_string_passes_through(
    service: MediaPlayerService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    """No closed enum -- an unrecognized state string is not rejected
    or coerced (Logic Contract §4)."""
    await connectivity.connect("home_assistant")
    _, device = await _home_and_media_player(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(status="some_vendor_specific_state")

    state = await service.get_media_player_state(device.id)

    assert state["state"] == "some_vendor_specific_state"


@pytest.mark.asyncio
async def test_unavailable_reports_none_state_not_the_status_string(
    service: MediaPlayerService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_media_player(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(status="unavailable")

    state = await service.get_media_player_state(device.id)

    assert state["available"] is False
    assert state["state"] is None
    assert state["volume_level"] is None
    assert state["is_volume_muted"] is None
    assert state["source"] is None
    assert state["media_title"] is None


@pytest.mark.asyncio
async def test_source_list_survives_unavailability(
    service: MediaPlayerService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_media_player(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(
        status="unavailable", attributes={"source_list": ["Spotify", "HDMI 1"]}
    )

    state = await service.get_media_player_state(device.id)

    assert state["available"] is False
    assert state["source_list"] == ["Spotify", "HDMI 1"]


@pytest.mark.asyncio
async def test_connector_unreachable_falls_back_without_raising(
    service: MediaPlayerService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_media_player(smart_home)
    state = await service.get_media_player_state(device.id)
    assert state["available"] is False
    assert state["state"] is None


@pytest.mark.asyncio
async def test_missing_attributes_report_none_not_zero(
    service: MediaPlayerService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_media_player(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(status="playing")

    state = await service.get_media_player_state(device.id)

    assert state["volume_level"] is None
    assert state["is_volume_muted"] is None
    assert state["source"] is None
    assert state["source_list"] == []
    assert state["media_title"] is None
    assert state["media_artist"] is None


@pytest.mark.asyncio
async def test_malformed_volume_reports_none_not_zero(
    service: MediaPlayerService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_media_player(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(
        status="playing", attributes={"volume_level": "n/a"}
    )

    state = await service.get_media_player_state(device.id)

    assert state["volume_level"] is None


@pytest.mark.asyncio
async def test_malformed_source_list_reports_empty_list(
    service: MediaPlayerService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_media_player(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(
        status="playing", attributes={"source_list": "Spotify"}
    )

    state = await service.get_media_player_state(device.id)

    assert state["source_list"] == []


@pytest.mark.asyncio
async def test_list_is_db_only_no_live_read(
    service: MediaPlayerService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _home_and_media_player(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(status="playing")

    rows = await service.list_media_players()

    assert rows[0]["available"] is False
    assert rows[0]["state"] is None


# --- Transport commands ----------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method_name,wire_command",
    [
        ("play", "media_play"),
        ("pause", "media_pause"),
        ("stop", "media_stop"),
        ("next_track", "media_next_track"),
        ("previous_track", "media_previous_track"),
    ],
)
async def test_transport_command_sends_zero_payload_ha_call(
    service: MediaPlayerService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
    method_name: str,
    wire_command: str,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_media_player(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(status="playing")

    result = await getattr(service, method_name)(device.id)

    assert result["success"] is True
    assert fake_connector.sent_commands == [(_EXTERNAL_ID, wire_command, {})]


@pytest.mark.asyncio
async def test_transport_command_failure_surfaced_not_raised(
    service: MediaPlayerService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_media_player(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(status="playing")
    fake_connector.next_command_succeeds = False

    result = await service.play(device.id)

    assert result["success"] is False
    assert "fake rejection" in result["detail"]


@pytest.mark.asyncio
async def test_no_recorded_connector_raises(
    service: MediaPlayerService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Orphan",
        device_type="appliance",
        external_id="media_player.orphan",
        metadata={"domain": "media_player"},
    )
    with pytest.raises(ServiceError, match="no recorded connector"):
        await service.play(device.id)


def test_transport_translators_are_zero_payload() -> None:
    from jarvis.services.media_player_service import MediaPlayerCommand

    for command in MediaPlayerCommand:
        assert _translate_transport_home_assistant(command) == (command.value, {})
        assert _translate_transport_mqtt(command) == (command.value, {})


@pytest.mark.asyncio
async def test_mqtt_device_uses_defined_transport_vocabulary(
    smart_home: SmartHomeService, permissions: PermissionModel, bus: EventBus
) -> None:
    mqtt_connector = FakeDeviceConnector()
    mqtt_connector.connector_type = "mqtt"
    reg = ConnectorFactoryRegistry()
    reg.register("mqtt", lambda config: mqtt_connector)
    conn = ConnectivityService(registry=reg, smart_home=smart_home, event_bus=bus)
    svc = MediaPlayerService(smart_home=smart_home, connectivity=conn, permissions=permissions)
    await conn.connect("mqtt")
    await permissions.grant(MEDIA_PLAYER_PRINCIPAL, SMART_HOME_SCOPE)
    _, device = await _home_and_media_player(smart_home, connector_type="mqtt")
    mqtt_connector.states[_EXTERNAL_ID] = _state(status="playing")

    result = await svc.play(device.id)

    assert result["success"] is True
    assert mqtt_connector.sent_commands == [(_EXTERNAL_ID, "media_play", {})]


# --- Merged state mutation --------------------------------------------------------


@pytest.mark.asyncio
async def test_volume_only_mutation(
    service: MediaPlayerService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_media_player(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(status="playing")

    result = await service.set_media_player_state(device.id, volume=0.5)

    assert result["success"] is True
    assert fake_connector.sent_commands == [(_EXTERNAL_ID, "volume_set", {"volume_level": 0.5})]


@pytest.mark.asyncio
async def test_mute_only_mutation(
    service: MediaPlayerService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_media_player(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(status="playing")

    result = await service.set_media_player_state(device.id, muted=True)

    assert result["success"] is True
    assert fake_connector.sent_commands == [
        (_EXTERNAL_ID, "volume_mute", {"is_volume_muted": True})
    ]


@pytest.mark.asyncio
async def test_source_only_mutation(
    service: MediaPlayerService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_media_player(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(status="playing")

    result = await service.set_media_player_state(device.id, source="HDMI 1")

    assert result["success"] is True
    assert fake_connector.sent_commands == [(_EXTERNAL_ID, "select_source", {"source": "HDMI 1"})]


@pytest.mark.asyncio
async def test_all_three_combined_ordering_volume_mute_source(
    service: MediaPlayerService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_media_player(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(status="playing")

    result = await service.set_media_player_state(
        device.id, volume=0.3, muted=False, source="Spotify"
    )

    assert result["success"] is True
    assert fake_connector.sent_commands == [
        (_EXTERNAL_ID, "volume_set", {"volume_level": 0.3}),
        (_EXTERNAL_ID, "volume_mute", {"is_volume_muted": False}),
        (_EXTERNAL_ID, "select_source", {"source": "Spotify"}),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs,expected_commands",
    [
        ({"volume": 0.4, "muted": True}, ["volume_set", "volume_mute"]),
        ({"volume": 0.4, "source": "Spotify"}, ["volume_set", "select_source"]),
        ({"muted": True, "source": "Spotify"}, ["volume_mute", "select_source"]),
    ],
)
async def test_pairwise_combinations_preserve_ordering(
    service: MediaPlayerService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
    kwargs: dict,
    expected_commands: list[str],
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_media_player(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(status="playing")

    result = await service.set_media_player_state(device.id, **kwargs)

    assert result["success"] is True
    assert [c[1] for c in fake_connector.sent_commands] == expected_commands


@pytest.mark.asyncio
async def test_empty_mutation_rejected(
    service: MediaPlayerService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    _, device = await _home_and_media_player(smart_home)
    with pytest.raises(ServiceError, match="at least one"):
        await service.set_media_player_state(device.id)


@pytest.mark.asyncio
async def test_first_operation_fails_reports_no_applied(
    service: MediaPlayerService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_media_player(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(status="playing")
    fake_connector.next_command_succeeds = False

    result = await service.set_media_player_state(device.id, volume=0.5, muted=True)

    assert result["success"] is False
    assert "already applied" not in result["detail"]


@pytest.mark.asyncio
async def test_second_operation_fails_reports_first_applied(
    service: MediaPlayerService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_media_player(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(status="playing")

    original_send = fake_connector.send_command
    call_count = {"n": 0}

    async def flaky_send(external_id, command, payload):
        call_count["n"] += 1
        if call_count["n"] == 2:
            fake_connector.next_command_succeeds = False
        else:
            fake_connector.next_command_succeeds = True
        return await original_send(external_id, command, payload)

    fake_connector.send_command = flaky_send  # type: ignore[method-assign]

    result = await service.set_media_player_state(device.id, volume=0.5, muted=True, source="X")

    assert result["success"] is False
    assert "volume_set" in result["detail"]
    assert "already applied" in result["detail"]


@pytest.mark.asyncio
async def test_third_operation_fails_reports_first_two_applied(
    service: MediaPlayerService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_media_player(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(status="playing")

    original_send = fake_connector.send_command
    call_count = {"n": 0}

    async def flaky_send(external_id, command, payload):
        call_count["n"] += 1
        if call_count["n"] == 3:
            fake_connector.next_command_succeeds = False
        else:
            fake_connector.next_command_succeeds = True
        return await original_send(external_id, command, payload)

    fake_connector.send_command = flaky_send  # type: ignore[method-assign]

    result = await service.set_media_player_state(device.id, volume=0.5, muted=True, source="X")

    assert result["success"] is False
    assert "volume_set" in result["detail"]
    assert "volume_mute" in result["detail"]
    assert "already applied" in result["detail"]


def test_state_translators_ordering() -> None:
    assert _translate_state_home_assistant(volume=0.5, muted=None, source=None) == [
        ("volume_set", {"volume_level": 0.5})
    ]
    assert _translate_state_home_assistant(volume=None, muted=True, source=None) == [
        ("volume_mute", {"is_volume_muted": True})
    ]
    assert _translate_state_home_assistant(volume=None, muted=None, source="X") == [
        ("select_source", {"source": "X"})
    ]
    assert _translate_state_home_assistant(volume=0.5, muted=True, source="X") == [
        ("volume_set", {"volume_level": 0.5}),
        ("volume_mute", {"is_volume_muted": True}),
        ("select_source", {"source": "X"}),
    ]


def test_mqtt_state_translator_is_always_one_merged_call() -> None:
    assert _translate_state_mqtt(volume=0.5, muted=None, source=None) == [
        ("set_state", {"volume": 0.5})
    ]
    assert _translate_state_mqtt(volume=None, muted=True, source=None) == [
        ("set_state", {"muted": True})
    ]
    assert _translate_state_mqtt(volume=None, muted=None, source="X") == [
        ("set_state", {"source": "X"})
    ]
    assert _translate_state_mqtt(volume=0.5, muted=True, source="X") == [
        ("set_state", {"volume": 0.5, "muted": True, "source": "X"})
    ]


# --- Volume validation ------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [0.0, 1.0, 0.5])
async def test_volume_boundary_and_normal_values_accepted(
    service: MediaPlayerService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
    value: float,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_media_player(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(status="playing")

    result = await service.set_media_player_state(device.id, volume=value)

    assert result["success"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [True, False])
async def test_bool_volume_rejected(
    service: MediaPlayerService,
    smart_home: SmartHomeService,
    permissions: PermissionModel,
    bad: bool,
) -> None:
    await _grant(permissions)
    _, device = await _home_and_media_player(smart_home)
    with pytest.raises(ServiceError, match="volume must be a number"):
        await service.set_media_player_state(device.id, volume=bad)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
async def test_non_finite_volume_rejected(
    service: MediaPlayerService,
    smart_home: SmartHomeService,
    permissions: PermissionModel,
    bad: float,
) -> None:
    await _grant(permissions)
    _, device = await _home_and_media_player(smart_home)
    with pytest.raises(ServiceError, match="finite"):
        await service.set_media_player_state(device.id, volume=bad)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [-0.1, 1.1, -5.0, 100.0])
async def test_out_of_range_volume_rejected(
    service: MediaPlayerService,
    smart_home: SmartHomeService,
    permissions: PermissionModel,
    bad: float,
) -> None:
    await _grant(permissions)
    _, device = await _home_and_media_player(smart_home)
    with pytest.raises(ServiceError, match="between 0.0 and 1.0"):
        await service.set_media_player_state(device.id, volume=bad)


# --- Mute validation ---------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["true", 1, 0, None])
async def test_non_bool_muted_rejected(
    service: MediaPlayerService,
    smart_home: SmartHomeService,
    permissions: PermissionModel,
    bad,
) -> None:
    if bad is None:
        return  # None means "not supplied" -- not a validation case.
    await _grant(permissions)
    _, device = await _home_and_media_player(smart_home)
    with pytest.raises(ServiceError, match="muted must be a boolean"):
        await service.set_media_player_state(device.id, muted=bad)


# --- Source validation -------------------------------------------------------------


@pytest.mark.asyncio
async def test_source_validated_against_device_reported_list(
    service: MediaPlayerService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_media_player(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(
        status="playing", attributes={"source_list": ["Spotify", "HDMI 1"]}
    )

    with pytest.raises(ServiceError, match="not supported by this device"):
        await service.set_media_player_state(device.id, source="Netflix")


@pytest.mark.asyncio
async def test_source_permissive_when_device_reports_no_list(
    service: MediaPlayerService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    """No fixed source enum is invented -- rejecting a real device over
    a vocabulary gap is the worse failure (Logic Contract §12)."""
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_media_player(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(status="playing")

    result = await service.set_media_player_state(device.id, source="Some Vendor Source")

    assert result["success"] is True
    assert fake_connector.sent_commands[0][2] == {"source": "Some Vendor Source"}


@pytest.mark.asyncio
async def test_source_case_is_preserved_not_lowercased(
    service: MediaPlayerService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_media_player(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(
        status="playing", attributes={"source_list": ["HDMI 1"]}
    )

    result = await service.set_media_player_state(device.id, source="HDMI 1")

    assert result["success"] is True
    assert fake_connector.sent_commands[0][2] == {"source": "HDMI 1"}


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["", "   "])
async def test_empty_source_rejected(
    service: MediaPlayerService,
    smart_home: SmartHomeService,
    permissions: PermissionModel,
    bad: str,
) -> None:
    await _grant(permissions)
    _, device = await _home_and_media_player(smart_home)
    with pytest.raises(ServiceError, match="source must be a non-empty string"):
        await service.set_media_player_state(device.id, source=bad)


# --- Cross-cutting invariants --------------------------------------------------------


def test_service_does_not_import_connectors_directly() -> None:
    """Docstrings may *discuss* the connectors -- only an actual import
    statement would be the real violation this test guards against."""
    import inspect

    from jarvis.services import media_player_service

    import_lines = [
        line
        for line in inspect.getsource(media_player_service).splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    joined = "\n".join(import_lines)
    assert "HomeAssistantConnector" not in joined
    assert "MqttConnector" not in joined
    assert "gmqtt" not in joined
    assert "connectors" not in joined.lower()


def test_service_publishes_no_events() -> None:
    import inspect

    from jarvis.services import media_player_service

    source = inspect.getsource(media_player_service)
    assert "event_bus" not in source
    assert "EventBus" not in source


def test_appliance_service_was_not_extended() -> None:
    """This slice is deliberately its own service -- ApplianceService
    must carry no media-player *implementation* (Logic Contract §3)."""
    import inspect

    from jarvis.services import appliance_service

    source = inspect.getsource(appliance_service)
    # Note: "media_play" is deliberately excluded here -- it's a
    # substring of the pre-existing, legitimate "media_player" text in
    # this file's own docstring (unchanged since Task Group G), not a
    # real leak signal. The symbols below only ever appear if this
    # service's actual implementation were bolted on.
    for leaked_symbol in (
        "MediaPlayerCommand",
        "_MEDIA_PLAYER_DOMAIN",
        "set_media_player_state",
        "volume_set",
        "select_source",
    ):
        assert leaked_symbol not in source


def test_no_deferred_functionality_exists() -> None:
    """play_media/join/unjoin/shuffle/repeat/sound_mode/queue/playlist
    must not exist anywhere in the implementation (Logic Contract §18)."""
    import inspect

    from jarvis.services import media_player_service

    source = inspect.getsource(media_player_service).lower()
    # Note: "join" is deliberately excluded here -- it's a substring of
    # this module's own legitimate `", ".join(applied)` string
    # formatting in `_send_all`'s partial-failure detail message, not
    # the deferred multi-speaker grouping feature. "unjoin" alone is an
    # unambiguous signal for that feature and has no such collision.
    for deferred_term in (
        "play_media",
        "unjoin",
        "clear_playlist",
        "shuffle",
        "repeat",
        "sound_mode",
        "media_position",
        "media_duration",
        "media_content_id",
        "queue",
        "playlist",
    ):
        assert deferred_term not in source
