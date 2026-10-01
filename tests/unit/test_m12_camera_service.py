"""CameraService tests -- Milestone 12 Smart Cameras (Core Camera
Slice).

Real (temp-file) SQLite ``SmartHomeService`` and a real
``PermissionModel`` throughout, matching ``test_m12_smart_lock_service.py``'s
own pattern -- only the connector itself is faked (``FakeDeviceConnector``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core.connectivity.registry import ConnectorFactoryRegistry
from jarvis.core.events.event_bus import EventBus
from jarvis.core.exceptions import ServiceError
from jarvis.core.interfaces.connectivity import DeviceState
from jarvis.core.plugins.permissions import PermissionModel
from jarvis.services.camera_service import (
    CAMERA_PRINCIPAL,
    SMART_HOME_SCOPE,
    CameraPermissionError,
    CameraService,
    _translate_home_assistant,
    _translate_mqtt,
)
from jarvis.services.connectivity_service import ConnectivityService
from jarvis.services.smart_home_service import SmartHomeService
from tests.fakes.fake_device_connector import FakeDeviceConnector

_EXTERNAL_ID = "camera.front_door"


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
) -> CameraService:
    return CameraService(smart_home=smart_home, connectivity=connectivity, permissions=permissions)


async def _grant(permissions: PermissionModel) -> None:
    await permissions.grant(CAMERA_PRINCIPAL, SMART_HOME_SCOPE)


async def _home_and_camera(smart_home: SmartHomeService, connector_type: str = "home_assistant"):
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Front Door Camera",
        device_type="camera",
        external_id=_EXTERNAL_ID,
        metadata={"connector_type": connector_type},
    )
    return home, device


def _state(status: str = "idle", attributes: dict | None = None) -> DeviceState:
    return DeviceState(external_id=_EXTERNAL_ID, status=status, attributes=attributes or {})


# --- Permission enforcement (every operation, including reads -- Logic Contract §4) ---


@pytest.mark.asyncio
async def test_permission_declared_pending_at_construction(permissions: PermissionModel) -> None:
    assert permissions.state(CAMERA_PRINCIPAL, SMART_HOME_SCOPE).value == "pending"


@pytest.mark.asyncio
async def test_list_cameras_denied_without_grant(
    service: CameraService, smart_home: SmartHomeService
) -> None:
    await _home_and_camera(smart_home)
    with pytest.raises(CameraPermissionError, match="permission"):
        await service.list_cameras()


@pytest.mark.asyncio
async def test_get_camera_state_denied_without_grant(
    service: CameraService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_camera(smart_home)
    with pytest.raises(CameraPermissionError, match="permission"):
        await service.get_camera_state(device.id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method_name", ["turn_on", "turn_off", "enable_motion_detection", "disable_motion_detection"]
)
async def test_commands_denied_without_grant(
    service: CameraService, smart_home: SmartHomeService, method_name: str
) -> None:
    _, device = await _home_and_camera(smart_home)
    with pytest.raises(CameraPermissionError, match="permission"):
        await getattr(service, method_name)(device.id)


# --- Domain / device-type safety ------------------------------------------------------


@pytest.mark.asyncio
async def test_rejects_non_camera_device(
    service: CameraService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    switch = await smart_home.register_discovered_device(
        home.id, "Hallway Switch", device_type="switch", external_id="switch.hallway"
    )
    with pytest.raises(ServiceError, match="not a camera"):
        await service.get_camera_state(switch.id)
    with pytest.raises(ServiceError, match="not a camera"):
        await service.turn_on(switch.id)


@pytest.mark.asyncio
async def test_unknown_device_raises(service: CameraService, permissions: PermissionModel) -> None:
    await _grant(permissions)
    with pytest.raises(ServiceError):
        await service.get_camera_state("no-such-device")


@pytest.mark.asyncio
async def test_rejects_device_with_no_connector(
    service: CameraService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id, "Orphan Camera", device_type="camera"
    )
    with pytest.raises(ServiceError, match="no recorded connector"):
        await service.turn_on(device.id)


@pytest.mark.asyncio
async def test_rejects_unsupported_connector_type(
    service: CameraService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    _, device = await _home_and_camera(smart_home, connector_type="zigbee")
    with pytest.raises(ServiceError, match="no command translation"):
        await service.turn_on(device.id)


# --- State normalization ---------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("raw_status", ["idle", "recording", "streaming"])
async def test_state_is_open_pass_through(
    service: CameraService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
    raw_status: str,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_camera(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(status=raw_status)

    state = await service.get_camera_state(device.id)

    assert state["state"] == raw_status
    assert state["available"] is True


@pytest.mark.asyncio
async def test_unavailable_reports_none_state(
    service: CameraService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_camera(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(status="unavailable")

    state = await service.get_camera_state(device.id)

    assert state["available"] is False
    assert state["state"] is None
    assert state["motion_detection"] is None


@pytest.mark.asyncio
async def test_motion_detection_true_when_reported(
    service: CameraService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_camera(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(
        status="idle", attributes={"motion_detection": True}
    )

    state = await service.get_camera_state(device.id)

    assert state["motion_detection"] is True


@pytest.mark.asyncio
async def test_motion_detection_absent_is_none_not_false(
    service: CameraService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    """HA itself only adds this key when truthy (Logic Contract §3) --
    an absent key must never be read as a fabricated `False`."""
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_camera(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(status="idle")

    state = await service.get_camera_state(device.id)

    assert state["motion_detection"] is None


@pytest.mark.asyncio
async def test_connector_unreachable_falls_back(
    service: CameraService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    _, device = await _home_and_camera(smart_home)

    state = await service.get_camera_state(device.id)

    assert state["available"] is False
    assert state["state"] is None


@pytest.mark.asyncio
async def test_list_cameras_is_db_only_no_live_read(
    service: CameraService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    await _home_and_camera(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(status="recording")

    rows = await service.list_cameras()

    assert len(rows) == 1
    assert rows[0]["available"] is False
    assert rows[0]["state"] is None


# --- Commands ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method_name,wire_command",
    [
        ("turn_on", "turn_on"),
        ("turn_off", "turn_off"),
        ("enable_motion_detection", "enable_motion_detection"),
        ("disable_motion_detection", "disable_motion_detection"),
    ],
)
async def test_command_sends_zero_payload_ha_call(
    service: CameraService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
    method_name: str,
    wire_command: str,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_camera(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(status="idle")

    result = await getattr(service, method_name)(device.id)

    assert result["success"] is True
    assert fake_connector.sent_commands == [(_EXTERNAL_ID, wire_command, {})]


@pytest.mark.asyncio
async def test_command_failure_surfaced_not_raised(
    service: CameraService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_camera(smart_home)
    fake_connector.states[_EXTERNAL_ID] = _state(status="idle")
    fake_connector.next_command_succeeds = False

    result = await service.turn_on(device.id)

    assert result["success"] is False
    assert result["detail"]


# --- Translators (unit-level, both connectors) -----------------------------------------


def test_ha_translator_zero_payload() -> None:
    from jarvis.services.camera_service import CameraCommand

    for command in CameraCommand:
        assert _translate_home_assistant(command) == (command.value, {})


def test_mqtt_translator_zero_payload() -> None:
    from jarvis.services.camera_service import CameraCommand

    for command in CameraCommand:
        assert _translate_mqtt(command) == (command.value, {})


@pytest.mark.asyncio
async def test_mqtt_device_uses_defined_vocabulary(
    smart_home: SmartHomeService, permissions: PermissionModel, bus: EventBus
) -> None:
    mqtt_connector = FakeDeviceConnector()
    mqtt_connector.connector_type = "mqtt"
    reg = ConnectorFactoryRegistry()
    reg.register("mqtt", lambda config: mqtt_connector)
    conn = ConnectivityService(registry=reg, smart_home=smart_home, event_bus=bus)
    svc = CameraService(smart_home=smart_home, connectivity=conn, permissions=permissions)
    await conn.connect("mqtt")
    await permissions.grant(CAMERA_PRINCIPAL, SMART_HOME_SCOPE)
    _, device = await _home_and_camera(smart_home, connector_type="mqtt")
    mqtt_connector.states[_EXTERNAL_ID] = _state(status="idle")

    result = await svc.turn_on(device.id)

    assert result["success"] is True
    assert mqtt_connector.sent_commands == [(_EXTERNAL_ID, "turn_on", {})]


# --- Cross-cutting invariants ------------------------------------------------------------


def test_service_does_not_import_connectors_directly() -> None:
    import inspect

    from jarvis.services import camera_service

    source = inspect.getsource(camera_service)
    for leaked_term in ("HomeAssistantConnector(", "MqttConnector(", "httpx"):
        assert leaked_term not in source


def test_service_publishes_no_events() -> None:
    import inspect

    from jarvis.services import camera_service

    source = inspect.getsource(camera_service)
    assert "event_bus" not in source.lower()


def test_no_deferred_functionality_exists() -> None:
    """Live Streaming, Recording, Snapshot Capture, ML-driven Motion/
    Person/Package/Vehicle Detection, and Face Recognition must not
    exist anywhere in the implementation (Logic Contract §9). Narrow,
    wire-shaped terms only -- "record"/"stream" alone would false-
    positive on this module's own legitimate discussion of the
    idle/recording/streaming state vocabulary."""
    import inspect

    from jarvis.services import camera_service

    source = inspect.getsource(camera_service).lower()
    for deferred_term in (
        "camera.snapshot",
        "camera.record",
        "rtsp",
        "stream_url",
        "face_recognition",
        "person_detect",
        "package_detect",
        "vehicle_detect",
    ):
        assert deferred_term not in source
