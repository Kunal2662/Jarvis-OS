"""Appliance agent tool tests -- Milestone 12 Appliance Control (Core
Appliance Slice: Fans + Covers).

Real ``ApplianceService`` over real (temp-file) SQLite, a real
``PermissionModel`` and a ``FakeDeviceConnector``, matching
``test_m12_smart_switch_tools.py``'s own fixtures.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("langchain_core")

from jarvis.agents.tools.appliance_tools import build_appliance_tools
from jarvis.core.connectivity.registry import ConnectorFactoryRegistry
from jarvis.core.events.event_bus import EventBus
from jarvis.core.plugins.permissions import PermissionModel
from jarvis.services.appliance_service import (
    APPLIANCE_PRINCIPAL,
    SMART_HOME_SCOPE,
    ApplianceService,
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
def service(smart_home, connectivity, permissions) -> ApplianceService:
    return ApplianceService(
        smart_home=smart_home, connectivity=connectivity, permissions=permissions
    )


@pytest.fixture
def tools(service: ApplianceService):
    return {t.name: t for t in build_appliance_tools(service)}


# --- Registry registration -----------------------------------------------------


def test_registry_omits_appliance_tools_when_not_wired() -> None:
    from jarvis.agents.tools.registry import build_tool_registry

    assert build_tool_registry() == []


@pytest.mark.asyncio
async def test_registry_includes_appliance_tools_when_service_provided(
    service: ApplianceService,
) -> None:
    from jarvis.agents.tools.registry import build_tool_registry

    tools = build_tool_registry(appliances=service)
    names = {t.name for t in tools}
    assert {
        "list_fans",
        "get_fan_state",
        "fan_on",
        "fan_off",
        "set_fan_percentage",
        "list_covers",
        "get_cover_state",
        "cover_open",
        "cover_close",
        "set_cover_position",
    } <= names


@pytest.mark.asyncio
async def test_orchestrator_accepts_appliances_constructor_argument(
    service: ApplianceService,
) -> None:
    """AgentOrchestrator integration (§15): `appliances` is a real
    constructor parameter threaded to `build_tool_registry` inside
    `start()` -- verified via `inspect.signature` rather than a full
    orchestrator boot, which needs LLM/memory/automation/browser
    services this test has no reason to construct."""
    import inspect

    from jarvis.agents.orchestrator import AgentOrchestrator

    params = inspect.signature(AgentOrchestrator.__init__).parameters
    assert "appliances" in params


# --- Reads are ungated -------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_fans_tool_works_without_grant(tools) -> None:
    result = await tools["list_fans"].ainvoke({})
    assert "No fans" in result


@pytest.mark.asyncio
async def test_list_covers_tool_works_without_grant(tools) -> None:
    result = await tools["list_covers"].ainvoke({})
    assert "No covers" in result


@pytest.mark.asyncio
async def test_get_fan_state_tool_works_without_grant(tools, smart_home: SmartHomeService) -> None:
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Living Room Fan",
        device_type="appliance",
        external_id="fan.living_room_fan",
        metadata={"connector_type": "home_assistant", "domain": "fan"},
    )

    result = await tools["get_fan_state"].ainvoke({"device_id": device.id})

    assert "Couldn't" not in result
    assert device.id in result


@pytest.mark.asyncio
async def test_get_cover_state_tool_works_without_grant(
    tools, smart_home: SmartHomeService
) -> None:
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Living Room Blind",
        device_type="appliance",
        external_id="cover.living_room_blind",
        metadata={"connector_type": "home_assistant", "domain": "cover"},
    )

    result = await tools["get_cover_state"].ainvoke({"device_id": device.id})

    assert "Couldn't" not in result
    assert device.id in result


# --- Mutations are permission-gated -----------------------------------------------


@pytest.mark.asyncio
async def test_fan_on_tool_denied_without_grant(tools, smart_home: SmartHomeService) -> None:
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Living Room Fan",
        device_type="appliance",
        external_id="fan.living_room_fan",
        metadata={"connector_type": "home_assistant", "domain": "fan"},
    )

    result = await tools["fan_on"].ainvoke({"device_id": device.id})

    assert "Couldn't" in result
    assert "permission" in result.lower()


@pytest.mark.asyncio
async def test_cover_open_tool_denied_without_grant(tools, smart_home: SmartHomeService) -> None:
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Living Room Blind",
        device_type="appliance",
        external_id="cover.living_room_blind",
        metadata={"connector_type": "home_assistant", "domain": "cover"},
    )

    result = await tools["cover_open"].ainvoke({"device_id": device.id})

    assert "Couldn't" in result
    assert "permission" in result.lower()


@pytest.mark.asyncio
async def test_fan_off_tool_succeeds_once_granted(
    tools,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await permissions.grant(APPLIANCE_PRINCIPAL, SMART_HOME_SCOPE)
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Living Room Fan",
        device_type="appliance",
        external_id="fan.living_room_fan",
        metadata={"connector_type": "home_assistant", "domain": "fan"},
    )

    result = await tools["fan_off"].ainvoke({"device_id": device.id})

    assert '"success": true' in result.lower()
    assert fake_connector.sent_commands == [("fan.living_room_fan", "turn_off", {})]


@pytest.mark.asyncio
async def test_cover_close_tool_succeeds_once_granted(
    tools,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await permissions.grant(APPLIANCE_PRINCIPAL, SMART_HOME_SCOPE)
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Living Room Blind",
        device_type="appliance",
        external_id="cover.living_room_blind",
        metadata={"connector_type": "home_assistant", "domain": "cover"},
    )

    result = await tools["cover_close"].ainvoke({"device_id": device.id})

    assert '"success": true' in result.lower()
    assert fake_connector.sent_commands == [("cover.living_room_blind", "close_cover", {})]


@pytest.mark.asyncio
async def test_set_fan_percentage_tool_denied_without_grant(
    tools, smart_home: SmartHomeService
) -> None:
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Living Room Fan",
        device_type="appliance",
        external_id="fan.living_room_fan",
        metadata={"connector_type": "home_assistant", "domain": "fan"},
    )

    result = await tools["set_fan_percentage"].ainvoke({"device_id": device.id, "percentage": 50})

    assert "Couldn't" in result
    assert "permission" in result.lower()


@pytest.mark.asyncio
async def test_set_fan_percentage_tool_succeeds_once_granted(
    tools,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await permissions.grant(APPLIANCE_PRINCIPAL, SMART_HOME_SCOPE)
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Living Room Fan",
        device_type="appliance",
        external_id="fan.living_room_fan",
        metadata={"connector_type": "home_assistant", "domain": "fan"},
    )

    result = await tools["set_fan_percentage"].ainvoke({"device_id": device.id, "percentage": 65})

    assert '"success": true' in result.lower()
    assert fake_connector.sent_commands == [
        ("fan.living_room_fan", "set_percentage", {"percentage": 65})
    ]


@pytest.mark.asyncio
async def test_set_fan_percentage_tool_rejects_out_of_range_without_raising(
    tools, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await permissions.grant(APPLIANCE_PRINCIPAL, SMART_HOME_SCOPE)
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Living Room Fan",
        device_type="appliance",
        external_id="fan.living_room_fan",
        metadata={"connector_type": "home_assistant", "domain": "fan"},
    )

    result = await tools["set_fan_percentage"].ainvoke({"device_id": device.id, "percentage": 150})

    assert "Couldn't" in result
    assert "0-100" in result


@pytest.mark.asyncio
async def test_set_cover_position_tool_denied_without_grant(
    tools, smart_home: SmartHomeService
) -> None:
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Living Room Blind",
        device_type="appliance",
        external_id="cover.living_room_blind",
        metadata={"connector_type": "home_assistant", "domain": "cover"},
    )

    result = await tools["set_cover_position"].ainvoke({"device_id": device.id, "position": 50})

    assert "Couldn't" in result
    assert "permission" in result.lower()


@pytest.mark.asyncio
async def test_set_cover_position_tool_succeeds_once_granted(
    tools,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await permissions.grant(APPLIANCE_PRINCIPAL, SMART_HOME_SCOPE)
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Living Room Blind",
        device_type="appliance",
        external_id="cover.living_room_blind",
        metadata={"connector_type": "home_assistant", "domain": "cover"},
    )

    result = await tools["set_cover_position"].ainvoke({"device_id": device.id, "position": 20})

    assert '"success": true' in result.lower()
    assert fake_connector.sent_commands == [
        ("cover.living_room_blind", "set_cover_position", {"position": 20})
    ]


@pytest.mark.asyncio
async def test_set_cover_position_tool_rejects_out_of_range_without_raising(
    tools, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await permissions.grant(APPLIANCE_PRINCIPAL, SMART_HOME_SCOPE)
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Living Room Blind",
        device_type="appliance",
        external_id="cover.living_room_blind",
        metadata={"connector_type": "home_assistant", "domain": "cover"},
    )

    result = await tools["set_cover_position"].ainvoke({"device_id": device.id, "position": -5})

    assert "Couldn't" in result
    assert "0-100" in result


@pytest.mark.asyncio
async def test_get_fan_state_tool_reports_unknown_device_without_raising(tools) -> None:
    result = await tools["get_fan_state"].ainvoke({"device_id": "no-such-device"})
    assert "Couldn't read" in result


@pytest.mark.asyncio
async def test_get_cover_state_tool_reports_unknown_device_without_raising(tools) -> None:
    result = await tools["get_cover_state"].ainvoke({"device_id": "no-such-device"})
    assert "Couldn't read" in result


# --- No confirmation gate (unlike unlock_device) ---------------------------------


def test_appliance_mutations_are_not_in_default_confirm_required_tools() -> None:
    """Neither a fan nor a cover (nor adjusting either's speed/
    position) is physically safety-relevant the way a lock is -- no
    AgentSettings default entry, unlike unlock_device."""
    from jarvis.core.config.settings import Settings

    settings = Settings()
    assert "fan_on" not in settings.agent.confirm_required_tools
    assert "fan_off" not in settings.agent.confirm_required_tools
    assert "set_fan_percentage" not in settings.agent.confirm_required_tools
    assert "cover_open" not in settings.agent.confirm_required_tools
    assert "cover_close" not in settings.agent.confirm_required_tools
    assert "set_cover_position" not in settings.agent.confirm_required_tools
