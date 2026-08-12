"""Smart Lock agent tool tests -- Milestone 12 Smart Locks.

Real ``SmartLockService`` over real (temp-file) SQLite, a real
``PermissionModel`` and a ``FakeDeviceConnector``, matching
``test_m12_smart_lighting_tools.py``'s own fixtures. Also exercises the
real ``AgentPermissionGate`` (not a stand-in) to prove the
``unlock_device`` confirmation-required default actually behaves as the
Logic Contract specifies -- this is the "wiring" this file exists to
prove, not a re-test of translation logic already covered in
``test_m12_smart_lock_service.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("langchain_core")

from jarvis.agents.permission import AgentPermissionGate
from jarvis.agents.tools.smart_lock_tools import build_smart_lock_tools
from jarvis.core.connectivity.registry import ConnectorFactoryRegistry
from jarvis.core.events.event_bus import EventBus
from jarvis.core.plugins.permissions import PermissionModel
from jarvis.services.connectivity_service import ConnectivityService
from jarvis.services.smart_home_service import SmartHomeService
from jarvis.services.smart_lock_service import (
    SMART_HOME_SCOPE,
    SMART_LOCK_PRINCIPAL,
    SmartLockService,
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
def service(smart_home, connectivity, permissions) -> SmartLockService:
    return SmartLockService(
        smart_home=smart_home, connectivity=connectivity, permissions=permissions
    )


@pytest.fixture
def tools(service: SmartLockService):
    return {t.name: t for t in build_smart_lock_tools(service)}


# --- Registry registration -----------------------------------------------------


def test_registry_omits_smart_lock_tools_when_not_wired() -> None:
    from jarvis.agents.tools.registry import build_tool_registry

    assert build_tool_registry() == []


@pytest.mark.asyncio
async def test_registry_includes_smart_lock_tools_when_service_provided(
    service: SmartLockService,
) -> None:
    from jarvis.agents.tools.registry import build_tool_registry

    tools = build_tool_registry(smart_lock=service)
    names = {t.name for t in tools}
    assert {"list_locks", "get_lock_status", "lock_device", "unlock_device"} <= names


# --- Basic tool behavior ---------------------------------------------------------


@pytest.mark.asyncio
async def test_list_locks_tool_reports_no_locks(tools) -> None:
    result = await tools["list_locks"].ainvoke({})
    assert "No locks" in result


@pytest.mark.asyncio
async def test_lock_device_tool_denied_without_grant(tools, smart_home: SmartHomeService) -> None:
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Front Door",
        device_type="lock",
        external_id="lock.front_door",
        metadata={"connector_type": "home_assistant"},
    )

    result = await tools["lock_device"].ainvoke({"device_id": device.id})

    assert "Couldn't" in result
    assert "permission" in result.lower()


@pytest.mark.asyncio
async def test_unlock_device_tool_succeeds_once_granted(
    tools,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await permissions.grant(SMART_LOCK_PRINCIPAL, SMART_HOME_SCOPE)
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Front Door",
        device_type="lock",
        external_id="lock.front_door",
        metadata={"connector_type": "home_assistant"},
    )

    result = await tools["unlock_device"].ainvoke({"device_id": device.id})

    assert '"success": true' in result.lower()
    assert fake_connector.sent_commands == [("lock.front_door", "unlock", {})]


@pytest.mark.asyncio
async def test_get_lock_status_tool_reports_unknown_device_without_raising(tools) -> None:
    result = await tools["get_lock_status"].ainvoke({"device_id": "no-such-device"})
    assert "Couldn't read" in result


# --- Confirmation / safety behavior (AgentPermissionGate integration) -----------


def test_unlock_device_is_in_the_default_confirm_required_tools() -> None:
    """Production default, not a test-only override -- proves the
    Logic Contract's §14 resolution actually shipped."""
    from jarvis.core.config.settings import Settings

    settings = Settings()
    assert "unlock_device" in settings.agent.confirm_required_tools
    assert "lock_device" not in settings.agent.confirm_required_tools


@pytest.mark.asyncio
async def test_gate_requires_confirmation_for_unlock_but_not_lock() -> None:
    gate = AgentPermissionGate(confirm_required_tools=frozenset({"unlock_device"}))

    lock_allowed, _ = await gate.authorize("lock_device", {"device_id": "x"})
    assert lock_allowed is True

    unlock_denied, reason = await gate.authorize("unlock_device", {"device_id": "x"})
    assert unlock_denied is False
    assert "requires confirmation" in reason


@pytest.mark.asyncio
async def test_gate_allows_unlock_when_user_confirms() -> None:
    gate = AgentPermissionGate(confirm_required_tools=frozenset({"unlock_device"}))

    async def approve(_: str) -> bool:
        return True

    allowed, reason = await gate.authorize("unlock_device", {"device_id": "x"}, confirm=approve)

    assert allowed is True
    assert reason == "User confirmed."


@pytest.mark.asyncio
async def test_gate_denies_unlock_when_user_declines() -> None:
    gate = AgentPermissionGate(confirm_required_tools=frozenset({"unlock_device"}))

    async def decline(_: str) -> bool:
        return False

    allowed, _ = await gate.authorize("unlock_device", {"device_id": "x"}, confirm=decline)

    assert allowed is False


@pytest.mark.asyncio
async def test_gate_auto_denies_unlock_with_no_confirmation_channel() -> None:
    """`auto_deny_when_unconfirmable=True` (the existing, unchanged
    default) -- an unconfirmable context denies, never silently
    allows."""
    gate = AgentPermissionGate(confirm_required_tools=frozenset({"unlock_device"}))

    allowed, _ = await gate.authorize("unlock_device", {"device_id": "x"}, confirm=None)

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
    await permissions.grant(SMART_LOCK_PRINCIPAL, SMART_HOME_SCOPE)
    fake_connector.next_command_succeeds = False
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Front Door",
        device_type="lock",
        external_id="lock.front_door",
        metadata={"connector_type": "home_assistant"},
    )

    result = await tools["unlock_device"].ainvoke({"device_id": device.id})

    assert '"success": false' in result.lower()
