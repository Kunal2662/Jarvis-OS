"""Alarm control panel agent tool tests -- Milestone 12 Security &
Safety (alarm_control_panel Integration Slice).

Real ``AlarmControlPanelService`` over real (temp-file) SQLite, a real
``PermissionModel`` and a ``FakeDeviceConnector``, matching
``test_m12_siren_tools.py``'s own fixtures. Also exercises the real
``AgentPermissionGate`` (not a stand-in) to prove the ``disarm``
confirmation-required default actually behaves as the Logic Contract
specifies, mirroring ``turn_siren_on``'s own precedent -- this is the
"wiring" this file exists to prove, not a re-test of translation logic
already covered in ``test_m12_alarm_control_panel_service.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("langchain_core")

from jarvis.agents.permission import AgentPermissionGate
from jarvis.agents.tools.alarm_control_panel_tools import build_alarm_control_panel_tools
from jarvis.core.connectivity.registry import ConnectorFactoryRegistry
from jarvis.core.events.event_bus import EventBus
from jarvis.core.plugins.permissions import PermissionModel
from jarvis.services.alarm_control_panel_service import (
    ALARM_CONTROL_PANEL_PRINCIPAL,
    SMART_HOME_SCOPE,
    AlarmControlPanelService,
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
def service(smart_home, connectivity, permissions) -> AlarmControlPanelService:
    return AlarmControlPanelService(
        smart_home=smart_home, connectivity=connectivity, permissions=permissions
    )


@pytest.fixture
def tools(service: AlarmControlPanelService):
    return {t.name: t for t in build_alarm_control_panel_tools(service)}


async def _panel(smart_home: SmartHomeService):
    home = await smart_home.create_home("Primary Residence")
    return await smart_home.register_discovered_device(
        home.id,
        "Front Panel",
        device_type="other",
        external_id="alarm_control_panel.front",
        metadata={"connector_type": "home_assistant", "domain": "alarm_control_panel"},
    )


# --- Registry registration -----------------------------------------------------


def test_registry_omits_alarm_control_panel_tools_when_not_wired() -> None:
    from jarvis.agents.tools.registry import build_tool_registry

    assert build_tool_registry() == []


@pytest.mark.asyncio
async def test_registry_includes_alarm_control_panel_tools_when_service_provided(
    service: AlarmControlPanelService,
) -> None:
    from jarvis.agents.tools.registry import build_tool_registry

    tools = build_tool_registry(alarm_control_panels=service)
    names = {t.name for t in tools}
    assert names == {
        "list_alarm_control_panels",
        "get_alarm_control_panel_state",
        "arm_home",
        "arm_away",
        "disarm",
    }


def test_exactly_five_tools_are_built(service: AlarmControlPanelService) -> None:
    assert len(build_alarm_control_panel_tools(service)) == 5


# --- Basic tool behavior ---------------------------------------------------------


@pytest.mark.asyncio
async def test_list_alarm_control_panels_tool_reports_none(tools) -> None:
    result = await tools["list_alarm_control_panels"].ainvoke({})
    assert "No alarm control panels" in result


@pytest.mark.asyncio
async def test_arm_home_tool_denied_without_grant(tools, smart_home: SmartHomeService) -> None:
    device = await _panel(smart_home)

    result = await tools["arm_home"].ainvoke({"device_id": device.id})

    assert "Couldn't" in result
    assert "permission" in result.lower()


@pytest.mark.asyncio
async def test_arm_away_tool_denied_without_grant(tools, smart_home: SmartHomeService) -> None:
    device = await _panel(smart_home)

    result = await tools["arm_away"].ainvoke({"device_id": device.id})

    assert "Couldn't" in result
    assert "permission" in result.lower()


@pytest.mark.asyncio
async def test_disarm_tool_denied_without_grant(tools, smart_home: SmartHomeService) -> None:
    device = await _panel(smart_home)

    result = await tools["disarm"].ainvoke({"device_id": device.id})

    assert "Couldn't" in result
    assert "permission" in result.lower()


@pytest.mark.asyncio
async def test_arm_home_tool_succeeds_once_granted(
    tools,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await permissions.grant(ALARM_CONTROL_PANEL_PRINCIPAL, SMART_HOME_SCOPE)
    device = await _panel(smart_home)

    result = await tools["arm_home"].ainvoke({"device_id": device.id})

    assert '"success": true' in result.lower()
    assert fake_connector.sent_commands == [("alarm_control_panel.front", "alarm_arm_home", {})]


@pytest.mark.asyncio
async def test_get_alarm_control_panel_state_tool_reports_unknown_device_without_raising(
    tools,
) -> None:
    result = await tools["get_alarm_control_panel_state"].ainvoke({"device_id": "no-such-device"})
    assert "Couldn't read" in result


@pytest.mark.asyncio
async def test_no_tool_schema_accepts_a_code_or_pin_argument(
    service: AlarmControlPanelService,
) -> None:
    for built_tool in build_alarm_control_panel_tools(service):
        schema_fields = set(built_tool.args)
        assert "code" not in schema_fields
        assert "pin" not in schema_fields


# --- Confirmation / safety behavior (AgentPermissionGate integration) -----------


def test_disarm_is_in_the_default_confirm_required_tools() -> None:
    """Production default, not a test-only override -- proves the
    Logic Contract's §12 resolution actually shipped."""
    from jarvis.core.config.settings import Settings

    settings = Settings()
    assert "disarm" in settings.agent.confirm_required_tools
    assert "arm_home" not in settings.agent.confirm_required_tools
    assert "arm_away" not in settings.agent.confirm_required_tools


@pytest.mark.asyncio
async def test_gate_requires_confirmation_for_disarm_but_not_arm_home_or_arm_away() -> None:
    gate = AgentPermissionGate(confirm_required_tools=frozenset({"disarm"}))

    home_allowed, _ = await gate.authorize("arm_home", {"device_id": "x"})
    assert home_allowed is True

    away_allowed, _ = await gate.authorize("arm_away", {"device_id": "x"})
    assert away_allowed is True

    disarm_denied, reason = await gate.authorize("disarm", {"device_id": "x"})
    assert disarm_denied is False
    assert "requires confirmation" in reason


@pytest.mark.asyncio
async def test_gate_allows_disarm_when_user_confirms() -> None:
    gate = AgentPermissionGate(confirm_required_tools=frozenset({"disarm"}))

    async def approve(_: str) -> bool:
        return True

    allowed, reason = await gate.authorize("disarm", {"device_id": "x"}, confirm=approve)

    assert allowed is True
    assert reason == "User confirmed."


@pytest.mark.asyncio
async def test_gate_denies_disarm_when_user_declines() -> None:
    gate = AgentPermissionGate(confirm_required_tools=frozenset({"disarm"}))

    async def decline(_: str) -> bool:
        return False

    allowed, _ = await gate.authorize("disarm", {"device_id": "x"}, confirm=decline)

    assert allowed is False


@pytest.mark.asyncio
async def test_gate_auto_denies_disarm_with_no_confirmation_channel() -> None:
    """``auto_deny_when_unconfirmable=True`` (the existing, unchanged
    default) -- an unconfirmable context denies, never silently
    allows."""
    gate = AgentPermissionGate(confirm_required_tools=frozenset({"disarm"}))

    allowed, _ = await gate.authorize("disarm", {"device_id": "x"}, confirm=None)

    assert allowed is False


@pytest.mark.asyncio
async def test_failed_command_never_reports_success_via_tool(
    tools,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await permissions.grant(ALARM_CONTROL_PANEL_PRINCIPAL, SMART_HOME_SCOPE)
    fake_connector.next_command_succeeds = False
    device = await _panel(smart_home)

    result = await tools["arm_home"].ainvoke({"device_id": device.id})

    assert '"success": false' in result.lower()
