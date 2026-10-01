"""Camera agent tool tests -- Milestone 12 Smart Cameras (Core Camera
Slice).

Real ``CameraService`` over real (temp-file) SQLite, a real
``PermissionModel`` and a ``FakeDeviceConnector``, matching
``test_m12_smart_lock_tools.py``'s own fixtures. Also exercises the
real ``AgentPermissionGate`` to prove the ``camera_turn_off``/
``disable_camera_motion_detection`` confirmation-required default
actually behaves as the Logic Contract specifies.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("langchain_core")

from jarvis.agents.permission import AgentPermissionGate
from jarvis.agents.tools.camera_tools import build_camera_tools
from jarvis.core.connectivity.registry import ConnectorFactoryRegistry
from jarvis.core.events.event_bus import EventBus
from jarvis.core.plugins.permissions import PermissionModel
from jarvis.services.camera_service import CAMERA_PRINCIPAL, SMART_HOME_SCOPE, CameraService
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
def fake_connector() -> FakeDeviceConnector:
    return FakeDeviceConnector()


@pytest.fixture
def smart_home(db) -> SmartHomeService:
    return SmartHomeService(database=db, event_bus=EventBus())


@pytest.fixture
def connectivity(
    fake_connector: FakeDeviceConnector, smart_home: SmartHomeService
) -> ConnectivityService:
    registry = ConnectorFactoryRegistry()
    registry.register("home_assistant", lambda config: fake_connector)
    return ConnectivityService(registry=registry, smart_home=smart_home)


@pytest.fixture
def permissions(tmp_path: Path) -> PermissionModel:
    return PermissionModel(EventBus(), store_path=tmp_path / "permissions.json")


@pytest.fixture
def service(smart_home, connectivity, permissions) -> CameraService:
    return CameraService(smart_home=smart_home, connectivity=connectivity, permissions=permissions)


@pytest.fixture
def tools(service: CameraService):
    return {t.name: t for t in build_camera_tools(service)}


async def _register_camera(smart_home: SmartHomeService):
    home = await smart_home.create_home("Primary Residence")
    return await smart_home.register_discovered_device(
        home.id,
        "Front Door Camera",
        device_type="camera",
        external_id=_EXTERNAL_ID,
        metadata={"connector_type": "home_assistant"},
    )


async def _grant(permissions: PermissionModel) -> None:
    await permissions.grant(CAMERA_PRINCIPAL, SMART_HOME_SCOPE)


# --- Registry registration -----------------------------------------------------


def test_registry_omits_camera_tools_when_not_wired() -> None:
    from jarvis.agents.tools.registry import build_tool_registry

    assert build_tool_registry() == []


@pytest.mark.asyncio
async def test_registry_includes_all_six_camera_tools_when_service_provided(
    service: CameraService,
) -> None:
    from jarvis.agents.tools.registry import build_tool_registry

    tools = build_tool_registry(cameras=service)
    names = {t.name for t in tools}
    assert {
        "list_cameras",
        "get_camera_state",
        "camera_turn_on",
        "camera_turn_off",
        "enable_camera_motion_detection",
        "disable_camera_motion_detection",
    } <= names


def test_exactly_six_tools_are_built(service: CameraService) -> None:
    built = {t.name for t in build_camera_tools(service)}
    assert built == {
        "list_cameras",
        "get_camera_state",
        "camera_turn_on",
        "camera_turn_off",
        "enable_camera_motion_detection",
        "disable_camera_motion_detection",
    }


# --- Basic tool behavior ---------------------------------------------------------


@pytest.mark.asyncio
async def test_list_cameras_tool_denied_without_grant(tools) -> None:
    result = await tools["list_cameras"].ainvoke({})
    assert "Couldn't" in result
    assert "permission" in result.lower()


@pytest.mark.asyncio
async def test_list_cameras_tool_reports_none(tools, permissions: PermissionModel) -> None:
    await _grant(permissions)
    result = await tools["list_cameras"].ainvoke({})
    assert "No cameras" in result


@pytest.mark.asyncio
async def test_get_camera_state_tool_denied_without_grant(
    tools, smart_home: SmartHomeService
) -> None:
    device = await _register_camera(smart_home)
    result = await tools["get_camera_state"].ainvoke({"device_id": device.id})
    assert "Couldn't" in result
    assert "permission" in result.lower()


@pytest.mark.asyncio
async def test_get_camera_state_tool(
    tools,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    from jarvis.core.interfaces.connectivity import DeviceState

    await connectivity.connect("home_assistant")
    await _grant(permissions)
    device = await _register_camera(smart_home)
    fake_connector.states[_EXTERNAL_ID] = DeviceState(
        external_id=_EXTERNAL_ID, status="idle", attributes={"motion_detection": True}
    )

    result = await tools["get_camera_state"].ainvoke({"device_id": device.id})

    assert '"state": "idle"' in result
    assert '"motion_detection": true' in result.lower()


@pytest.mark.asyncio
async def test_camera_turn_on_tool_denied_without_grant(
    tools, smart_home: SmartHomeService
) -> None:
    device = await _register_camera(smart_home)
    result = await tools["camera_turn_on"].ainvoke({"device_id": device.id})
    assert "Couldn't" in result
    assert "permission" in result.lower()


@pytest.mark.asyncio
async def test_camera_turn_on_tool_succeeds_once_granted(
    tools,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    device = await _register_camera(smart_home)

    result = await tools["camera_turn_on"].ainvoke({"device_id": device.id})

    assert '"success": true' in result.lower()
    assert fake_connector.sent_commands == [(_EXTERNAL_ID, "turn_on", {})]


@pytest.mark.asyncio
async def test_enable_camera_motion_detection_tool_succeeds_once_granted(
    tools,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    device = await _register_camera(smart_home)

    result = await tools["enable_camera_motion_detection"].ainvoke({"device_id": device.id})

    assert '"success": true' in result.lower()
    assert fake_connector.sent_commands == [(_EXTERNAL_ID, "enable_motion_detection", {})]


@pytest.mark.asyncio
async def test_get_camera_state_tool_reports_unknown_device_without_raising(
    tools, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    result = await tools["get_camera_state"].ainvoke({"device_id": "no-such-device"})
    assert "Couldn't read" in result


@pytest.mark.asyncio
async def test_failed_command_never_reports_success_via_tool(
    tools,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    fake_connector.next_command_succeeds = False
    device = await _register_camera(smart_home)

    result = await tools["camera_turn_on"].ainvoke({"device_id": device.id})

    assert '"success": false' in result.lower()


# --- Confirmation / safety behavior (AgentPermissionGate integration) -----------


def test_turn_off_and_disable_motion_are_in_the_default_confirm_required_tools() -> None:
    """Production default, not a test-only override -- proves the
    Logic Contract's §8 resolution actually shipped."""
    from jarvis.core.config.settings import Settings

    settings = Settings()
    assert "camera_turn_off" in settings.agent.confirm_required_tools
    assert "disable_camera_motion_detection" in settings.agent.confirm_required_tools
    assert "camera_turn_on" not in settings.agent.confirm_required_tools
    assert "enable_camera_motion_detection" not in settings.agent.confirm_required_tools


@pytest.mark.asyncio
async def test_gate_requires_confirmation_for_turn_off_but_not_turn_on() -> None:
    gate = AgentPermissionGate(confirm_required_tools=frozenset({"camera_turn_off"}))

    on_allowed, _ = await gate.authorize("camera_turn_on", {"device_id": "x"})
    assert on_allowed is True

    off_denied, reason = await gate.authorize("camera_turn_off", {"device_id": "x"})
    assert off_denied is False
    assert "requires confirmation" in reason


@pytest.mark.asyncio
async def test_gate_auto_denies_turn_off_with_no_confirmation_channel() -> None:
    gate = AgentPermissionGate(confirm_required_tools=frozenset({"camera_turn_off"}))

    allowed, _ = await gate.authorize("camera_turn_off", {"device_id": "x"}, confirm=None)

    assert allowed is False
