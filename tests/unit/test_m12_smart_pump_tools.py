"""Smart Pump agent tool tests -- Milestone 12 Smart Pumps
(Switch-Backed Device Slice).

Real ``SmartPumpService`` over real (temp-file) SQLite, a real
``PermissionModel`` and a ``FakeDeviceConnector``, matching
``test_m12_smart_switch_tools.py``'s own fixtures -- plus the
``AgentPermissionGate`` integration tests proving ``pump_on``/
``pump_off`` participate in the existing ``confirm_required_tools``
mechanism (never a new gate of their own).
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("langchain_core")

from jarvis.agents.permission import AgentPermissionGate
from jarvis.agents.tools.smart_pump_tools import build_smart_pump_tools
from jarvis.core.connectivity.registry import ConnectorFactoryRegistry
from jarvis.core.events.event_bus import EventBus
from jarvis.core.plugins.permissions import PermissionModel
from jarvis.services.connectivity_service import ConnectivityService
from jarvis.services.smart_home_service import SmartHomeService
from jarvis.services.smart_pump_service import SmartPumpService
from jarvis.services.smart_switch_service import (
    SMART_HOME_SCOPE,
    SMART_SWITCH_PRINCIPAL,
    SmartSwitchService,
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
def switch_service(smart_home, connectivity, permissions) -> SmartSwitchService:
    return SmartSwitchService(
        smart_home=smart_home, connectivity=connectivity, permissions=permissions
    )


@pytest.fixture
def pump_service(switch_service, smart_home) -> SmartPumpService:
    return SmartPumpService(switches=switch_service, smart_home=smart_home)


@pytest.fixture
def tools(pump_service: SmartPumpService):
    return {t.name: t for t in build_smart_pump_tools(pump_service)}


async def _register_pump(smart_home: SmartHomeService):
    home = await smart_home.create_home("Primary Residence")
    return await smart_home.register_discovered_device(
        home.id,
        "Water Pump",
        device_type="switch",
        external_id="switch.water_pump",
        metadata={"connector_type": "home_assistant"},
    )


# --- Registry registration -------------------------------------------------------


def test_registry_omits_pump_tools_when_not_wired() -> None:
    from jarvis.agents.tools.registry import build_tool_registry

    names = {t.name for t in build_tool_registry()}
    assert not {"pump_on", "pump_off", "get_pump_state"} & names


@pytest.mark.asyncio
async def test_registry_includes_pump_tools_when_service_provided(
    pump_service: SmartPumpService,
) -> None:
    from jarvis.agents.tools.registry import build_tool_registry

    tools = build_tool_registry(pumps=pump_service)
    names = {t.name for t in tools}
    assert {"pump_on", "pump_off", "get_pump_state"} <= names


def test_tool_names_are_exactly_the_three_pump_tools(
    pump_service: SmartPumpService,
) -> None:
    """No ``list_pumps`` -- ``list_switches`` already enumerates every
    pump-controllable device, so a list tool would duplicate it."""
    names = {t.name for t in build_smart_pump_tools(pump_service)}
    assert names == {"pump_on", "pump_off", "get_pump_state"}


# --- Reads are ungated -------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_pump_state_tool_works_without_grant(tools, smart_home: SmartHomeService) -> None:
    device = await _register_pump(smart_home)

    result = await tools["get_pump_state"].ainvoke({"device_id": device.id})

    assert "Couldn't" not in result
    assert device.id in result
    assert '"kind": "pump"' in result


@pytest.mark.asyncio
async def test_get_pump_state_tool_reports_unknown_device_without_raising(tools) -> None:
    result = await tools["get_pump_state"].ainvoke({"device_id": "no-such-device"})
    assert "Couldn't read" in result


@pytest.mark.asyncio
async def test_get_pump_state_tool_rejects_non_switch_device(
    tools, smart_home: SmartHomeService
) -> None:
    home = await smart_home.create_home("Primary Residence")
    light = await smart_home.register_discovered_device(
        home.id, "Ceiling Light", device_type="light", external_id="light.ceiling"
    )

    result = await tools["get_pump_state"].ainvoke({"device_id": light.id})

    assert "Couldn't read" in result
    assert "not a pump" in result


# --- Mutations are permission-gated (inherited switch grant) -----------------------


@pytest.mark.asyncio
async def test_pump_on_tool_denied_without_grant(tools, smart_home: SmartHomeService) -> None:
    device = await _register_pump(smart_home)

    result = await tools["pump_on"].ainvoke({"device_id": device.id})

    assert "Couldn't" in result
    assert "permission" in result.lower()


@pytest.mark.asyncio
async def test_pump_on_tool_succeeds_once_granted(
    tools,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await permissions.grant(SMART_SWITCH_PRINCIPAL, SMART_HOME_SCOPE)
    device = await _register_pump(smart_home)

    result = await tools["pump_on"].ainvoke({"device_id": device.id})

    assert '"success": true' in result.lower()
    assert '"kind": "pump"' in result
    assert fake_connector.sent_commands == [("switch.water_pump", "turn_on", {})]


@pytest.mark.asyncio
async def test_pump_off_tool_succeeds_once_granted(
    tools,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await permissions.grant(SMART_SWITCH_PRINCIPAL, SMART_HOME_SCOPE)
    device = await _register_pump(smart_home)

    result = await tools["pump_off"].ainvoke({"device_id": device.id})

    assert '"success": true' in result.lower()
    assert fake_connector.sent_commands == [("switch.water_pump", "turn_off", {})]


@pytest.mark.asyncio
async def test_pump_on_tool_reports_failure_honestly(
    tools,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await permissions.grant(SMART_SWITCH_PRINCIPAL, SMART_HOME_SCOPE)
    fake_connector.next_command_succeeds = False
    device = await _register_pump(smart_home)

    result = await tools["pump_on"].ainvoke({"device_id": device.id})

    assert '"success": false' in result.lower()


# --- Confirmation / safety behavior (existing AgentPermissionGate mechanism) --------


def test_pump_on_and_pump_off_are_in_the_default_confirm_required_tools() -> None:
    """Production default, not a test-only override -- both directions
    are gated (neither pump direction is unambiguously fail-safe), and
    the read tool plus the deliberately-ungated ``switch_on``/
    ``switch_off`` scheduling path are pinned alongside them."""
    from jarvis.core.config.settings import Settings

    settings = Settings()
    assert "pump_on" in settings.agent.confirm_required_tools
    assert "pump_off" in settings.agent.confirm_required_tools
    assert "get_pump_state" not in settings.agent.confirm_required_tools
    # The scheduling path stays ungated, or no schedule could ever drive
    # a pump (Policy A denies every confirm-required step).
    assert "switch_on" not in settings.agent.confirm_required_tools
    assert "switch_off" not in settings.agent.confirm_required_tools


@pytest.mark.asyncio
async def test_gate_requires_confirmation_for_both_pump_directions() -> None:
    """Default construction (``auto_deny_when_unconfirmable=True``) --
    an unconfirmable context denies, never silently allows."""
    from jarvis.core.config.settings import Settings

    gate = AgentPermissionGate(confirm_required_tools=Settings().agent.confirm_required_tools)

    on_allowed, on_reason = await gate.authorize("pump_on", {"device_id": "x"}, confirm=None)
    assert on_allowed is False
    assert "requires confirmation" in on_reason

    off_allowed, off_reason = await gate.authorize("pump_off", {"device_id": "x"}, confirm=None)
    assert off_allowed is False
    assert "requires confirmation" in off_reason


@pytest.mark.asyncio
async def test_gate_allows_pump_on_when_user_confirms() -> None:
    from jarvis.core.config.settings import Settings

    gate = AgentPermissionGate(confirm_required_tools=Settings().agent.confirm_required_tools)

    async def approve(_: str) -> bool:
        return True

    allowed, reason = await gate.authorize("pump_on", {"device_id": "x"}, confirm=approve)

    assert allowed is True
    assert reason == "User confirmed."


@pytest.mark.asyncio
async def test_gate_denies_pump_off_when_user_declines() -> None:
    from jarvis.core.config.settings import Settings

    gate = AgentPermissionGate(confirm_required_tools=Settings().agent.confirm_required_tools)

    async def decline(_: str) -> bool:
        return False

    allowed, _ = await gate.authorize("pump_off", {"device_id": "x"}, confirm=decline)

    assert allowed is False


@pytest.mark.asyncio
async def test_gate_allows_read_and_switch_tools_without_confirmation() -> None:
    """The ungated counterparts stay ungated: the pump state read and
    the existing switch tools (the scheduling path) need no prompt."""
    from jarvis.core.config.settings import Settings

    gate = AgentPermissionGate(confirm_required_tools=Settings().agent.confirm_required_tools)

    for tool_name in ("get_pump_state", "switch_on", "switch_off"):
        allowed, reason = await gate.authorize(tool_name, {"device_id": "x"}, confirm=None)
        assert allowed is True, f"{tool_name} must not require confirmation"
        assert reason == "No confirmation required."


# --- No schema surprises -------------------------------------------------------------


@pytest.mark.asyncio
async def test_every_pump_tool_takes_exactly_a_device_id(pump_service: SmartPumpService) -> None:
    """No code/pin/secret arguments, mirroring the alarm panel slice's
    own schema pin -- the pump surface accepts nothing but the device."""
    for built_tool in build_smart_pump_tools(pump_service):
        assert set(built_tool.args) == {"device_id"}
