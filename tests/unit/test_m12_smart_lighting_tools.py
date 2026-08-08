"""Smart Lighting agent tool tests -- Milestone 12 Connectivity REST +
Smart Lighting.

Real ``SmartLightingService`` over real (temp-file) SQLite, a real
``PermissionModel`` and a ``FakeDeviceConnector``, matching
``test_m12_smart_lighting_service.py``'s own fixtures -- these tools are
thin wrappers, so the point of this file is proving the wrapping (tool
registry inclusion, error-to-string handling, the shared permission
gate), not re-testing translation logic already covered there.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("langchain_core")

from jarvis.agents.tools.smart_lighting_tools import build_smart_lighting_tools
from jarvis.core.connectivity.registry import ConnectorFactoryRegistry
from jarvis.core.events.event_bus import EventBus
from jarvis.core.plugins.permissions import PermissionModel
from jarvis.services.connectivity_service import ConnectivityService
from jarvis.services.smart_home_service import SmartHomeService
from jarvis.services.smart_lighting_service import (
    SMART_HOME_SCOPE,
    SMART_LIGHTING_PRINCIPAL,
    SmartLightingService,
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
def service(db, smart_home, connectivity, permissions) -> SmartLightingService:
    return SmartLightingService(
        database=db, smart_home=smart_home, connectivity=connectivity, permissions=permissions
    )


@pytest.fixture
def tools(service: SmartLightingService):
    return {t.name: t for t in build_smart_lighting_tools(service)}


def test_registry_includes_smart_lighting_tools_only_when_wired() -> None:
    from jarvis.agents.tools.registry import build_tool_registry

    assert build_tool_registry() == []


@pytest.mark.asyncio
async def test_registry_includes_smart_lighting_tools_when_service_provided(
    service: SmartLightingService,
) -> None:
    from jarvis.agents.tools.registry import build_tool_registry

    tools = build_tool_registry(smart_lighting=service)
    names = {t.name for t in tools}
    assert {
        "list_lights",
        "get_light_state",
        "set_light_state",
        "set_room_lights",
        "set_group_lights",
        "list_scenes",
        "apply_scene",
    } <= names


@pytest.mark.asyncio
async def test_list_lights_tool_reports_no_lights(tools) -> None:
    result = await tools["list_lights"].ainvoke({})
    assert "No lights" in result


@pytest.mark.asyncio
async def test_set_light_state_tool_denied_without_grant(
    tools, smart_home: SmartHomeService, connectivity: ConnectivityService
) -> None:
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Lamp",
        device_type="light",
        external_id="light.lamp",
        metadata={"connector_type": "home_assistant"},
    )

    result = await tools["set_light_state"].ainvoke({"device_id": device.id, "on": True})

    assert "Couldn't" in result
    assert "permission" in result.lower()


@pytest.mark.asyncio
async def test_set_light_state_tool_succeeds_once_granted(
    tools,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await permissions.grant(SMART_LIGHTING_PRINCIPAL, SMART_HOME_SCOPE)
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Lamp",
        device_type="light",
        external_id="light.lamp",
        metadata={"connector_type": "home_assistant"},
    )

    result = await tools["set_light_state"].ainvoke(
        {"device_id": device.id, "brightness": 60, "color": [10, 20, 30]}
    )

    assert '"success": true' in result.lower()
    assert fake_connector.sent_commands == [
        ("light.lamp", "turn_on", {"brightness_pct": 60, "rgb_color": [10, 20, 30]})
    ]


@pytest.mark.asyncio
async def test_apply_scene_tool_reports_unknown_scene_without_raising(tools) -> None:
    result = await tools["apply_scene"].ainvoke({"scene_id": "no-such-scene"})
    assert "Couldn't apply" in result
