"""Siren agent tool tests -- Milestone 12 Security & Safety (Siren
Integration Slice).

Real ``SirenService`` over real (temp-file) SQLite, a real
``PermissionModel`` and a ``FakeDeviceConnector``, matching
``test_m12_smart_lock_tools.py``'s own fixtures. Also exercises the real
``AgentPermissionGate`` (not a stand-in) to prove the ``turn_siren_on``
confirmation-required default actually behaves as the Logic Contract
specifies, mirroring ``unlock_device``'s own precedent -- this is the
"wiring" this file exists to prove, not a re-test of translation logic
already covered in ``test_m12_siren_service.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("langchain_core")

from jarvis.agents.permission import AgentPermissionGate
from jarvis.agents.tools.siren_tools import build_siren_tools
from jarvis.core.connectivity.registry import ConnectorFactoryRegistry
from jarvis.core.events.event_bus import EventBus
from jarvis.core.plugins.permissions import PermissionModel
from jarvis.services.connectivity_service import ConnectivityService
from jarvis.services.siren_service import SIREN_PRINCIPAL, SMART_HOME_SCOPE, SirenService
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
def service(smart_home, connectivity, permissions) -> SirenService:
    return SirenService(smart_home=smart_home, connectivity=connectivity, permissions=permissions)


@pytest.fixture
def tools(service: SirenService):
    return {t.name: t for t in build_siren_tools(service)}


async def _siren(smart_home: SmartHomeService):
    home = await smart_home.create_home("Primary Residence")
    return await smart_home.register_discovered_device(
        home.id,
        "Front Yard Siren",
        device_type="other",
        external_id="siren.front_yard",
        metadata={"connector_type": "home_assistant", "domain": "siren"},
    )


# --- Registry registration -----------------------------------------------------


def test_registry_omits_siren_tools_when_not_wired() -> None:
    from jarvis.agents.tools.registry import build_tool_registry

    assert build_tool_registry() == []


@pytest.mark.asyncio
async def test_registry_includes_siren_tools_when_service_provided(
    service: SirenService,
) -> None:
    from jarvis.agents.tools.registry import build_tool_registry

    tools = build_tool_registry(siren=service)
    names = {t.name for t in tools}
    assert names == {"list_sirens", "get_siren_state", "turn_siren_on", "turn_siren_off"}


# --- Basic tool behavior ---------------------------------------------------------


@pytest.mark.asyncio
async def test_list_sirens_tool_reports_no_sirens(tools) -> None:
    result = await tools["list_sirens"].ainvoke({})
    assert "No sirens" in result


@pytest.mark.asyncio
async def test_turn_siren_on_tool_denied_without_grant(tools, smart_home: SmartHomeService) -> None:
    device = await _siren(smart_home)

    result = await tools["turn_siren_on"].ainvoke({"device_id": device.id})

    assert "Couldn't" in result
    assert "permission" in result.lower()


@pytest.mark.asyncio
async def test_turn_siren_off_tool_succeeds_once_granted(
    tools,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await permissions.grant(SIREN_PRINCIPAL, SMART_HOME_SCOPE)
    device = await _siren(smart_home)

    result = await tools["turn_siren_off"].ainvoke({"device_id": device.id})

    assert '"success": true' in result.lower()
    assert fake_connector.sent_commands == [("siren.front_yard", "turn_off", {})]


@pytest.mark.asyncio
async def test_get_siren_state_tool_reports_unknown_device_without_raising(tools) -> None:
    result = await tools["get_siren_state"].ainvoke({"device_id": "no-such-device"})
    assert "Couldn't read" in result


# --- Confirmation / safety behavior (AgentPermissionGate integration) -----------


def test_turn_siren_on_is_in_the_default_confirm_required_tools() -> None:
    """Production default, not a test-only override -- proves the
    Logic Contract's §10 resolution actually shipped."""
    from jarvis.core.config.settings import Settings

    settings = Settings()
    assert "turn_siren_on" in settings.agent.confirm_required_tools
    assert "turn_siren_off" not in settings.agent.confirm_required_tools


@pytest.mark.asyncio
async def test_gate_requires_confirmation_for_turn_on_but_not_turn_off() -> None:
    gate = AgentPermissionGate(confirm_required_tools=frozenset({"turn_siren_on"}))

    off_allowed, _ = await gate.authorize("turn_siren_off", {"device_id": "x"})
    assert off_allowed is True

    on_denied, reason = await gate.authorize("turn_siren_on", {"device_id": "x"})
    assert on_denied is False
    assert "requires confirmation" in reason


@pytest.mark.asyncio
async def test_gate_allows_turn_on_when_user_confirms() -> None:
    gate = AgentPermissionGate(confirm_required_tools=frozenset({"turn_siren_on"}))

    async def approve(_: str) -> bool:
        return True

    allowed, reason = await gate.authorize("turn_siren_on", {"device_id": "x"}, confirm=approve)

    assert allowed is True
    assert reason == "User confirmed."


@pytest.mark.asyncio
async def test_gate_denies_turn_on_when_user_declines() -> None:
    gate = AgentPermissionGate(confirm_required_tools=frozenset({"turn_siren_on"}))

    async def decline(_: str) -> bool:
        return False

    allowed, _ = await gate.authorize("turn_siren_on", {"device_id": "x"}, confirm=decline)

    assert allowed is False


@pytest.mark.asyncio
async def test_gate_auto_denies_turn_on_with_no_confirmation_channel() -> None:
    """`auto_deny_when_unconfirmable=True` (the existing, unchanged
    default) -- an unconfirmable context denies, never silently
    allows."""
    gate = AgentPermissionGate(confirm_required_tools=frozenset({"turn_siren_on"}))

    allowed, _ = await gate.authorize("turn_siren_on", {"device_id": "x"}, confirm=None)

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
    await permissions.grant(SIREN_PRINCIPAL, SMART_HOME_SCOPE)
    fake_connector.next_command_succeeds = False
    device = await _siren(smart_home)

    result = await tools["turn_siren_off"].ainvoke({"device_id": device.id})

    assert '"success": false' in result.lower()
