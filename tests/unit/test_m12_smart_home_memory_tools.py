"""Smart Home Memory agent tool tests -- Milestone 12 Smart Home Memory
(Manual/On-Demand Device Snapshot Slice).

Real ``SmartHomeMemoryService`` over real (temp-file) SQLite, real
``SmartLightingService``, a real ``MemoryService`` (``FakeLLM``/
``FakeVectorStore``), a real ``PermissionModel`` and a
``FakeDeviceConnector``, matching
``test_m12_water_heater_tools.py``'s own fixtures.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("langchain_core")

from jarvis.agents.tools.smart_home_memory_tools import build_smart_home_memory_tools
from jarvis.core.connectivity.registry import ConnectorFactoryRegistry
from jarvis.core.events.event_bus import EventBus
from jarvis.core.interfaces.connectivity import DeviceState
from jarvis.core.plugins.permissions import PermissionModel
from jarvis.services.connectivity_service import ConnectivityService
from jarvis.services.memory_service import MemoryService
from jarvis.services.smart_home_memory_service import (
    SMART_HOME_MEMORY_PRINCIPAL,
    SMART_HOME_SCOPE,
    SmartHomeMemoryService,
)
from jarvis.services.smart_home_service import SmartHomeService
from jarvis.services.smart_lighting_service import SmartLightingService
from jarvis.services.smart_switch_service import SmartSwitchService
from jarvis.services.thermostat_service import ThermostatService
from tests.fakes.fake_device_connector import FakeDeviceConnector
from tests.fakes.fake_llm import FakeLLM
from tests.fakes.fake_vector_store import FakeVectorStore

_LIGHT_EXTERNAL_ID = "light.living_room"


def _settings(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JARVIS_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'jarvis.db'}")
    monkeypatch.setenv("JARVIS_OPENAI_ENABLED", "false")
    monkeypatch.setenv("JARVIS_OLLAMA_ENABLED", "true")

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
        yield database, settings
    finally:
        await database.dispose()


@pytest.fixture
def fake_connector() -> FakeDeviceConnector:
    return FakeDeviceConnector()


@pytest.fixture
def smart_home(db) -> SmartHomeService:
    database, _ = db
    return SmartHomeService(database=database, event_bus=EventBus())


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
def smart_lighting(
    db,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
) -> SmartLightingService:
    database, _ = db
    return SmartLightingService(
        database=database, smart_home=smart_home, connectivity=connectivity, permissions=permissions
    )


@pytest.fixture
def smart_switch(
    smart_home: SmartHomeService, connectivity: ConnectivityService, permissions: PermissionModel
) -> SmartSwitchService:
    return SmartSwitchService(
        smart_home=smart_home, connectivity=connectivity, permissions=permissions
    )


@pytest.fixture
def thermostats(
    smart_home: SmartHomeService, connectivity: ConnectivityService, permissions: PermissionModel
) -> ThermostatService:
    return ThermostatService(
        smart_home=smart_home, connectivity=connectivity, permissions=permissions
    )


@pytest.fixture
def memory(db) -> MemoryService:
    database, settings = db
    return MemoryService(
        database=database, vector_store=FakeVectorStore(), llm=FakeLLM(), settings=settings
    )


@pytest.fixture
def service(
    smart_home: SmartHomeService,
    smart_lighting: SmartLightingService,
    smart_switch: SmartSwitchService,
    thermostats: ThermostatService,
    memory: MemoryService,
    permissions: PermissionModel,
) -> SmartHomeMemoryService:
    return SmartHomeMemoryService(
        smart_home=smart_home,
        smart_lighting=smart_lighting,
        smart_switch=smart_switch,
        thermostats=thermostats,
        memory=memory,
        permissions=permissions,
    )


@pytest.fixture
def tools(service: SmartHomeMemoryService):
    return {t.name: t for t in build_smart_home_memory_tools(service)}


async def _grant(permissions: PermissionModel) -> None:
    await permissions.grant(SMART_HOME_MEMORY_PRINCIPAL, SMART_HOME_SCOPE)


async def _register_light(smart_home: SmartHomeService):
    home = await smart_home.create_home("Primary Residence")
    return await smart_home.register_discovered_device(
        home.id,
        "Living Room Light",
        device_type="light",
        external_id=_LIGHT_EXTERNAL_ID,
        metadata={"connector_type": "home_assistant"},
    )


# --- Registry registration -----------------------------------------------------


def test_registry_omits_tools_when_not_wired() -> None:
    from jarvis.agents.tools.registry import build_tool_registry

    assert build_tool_registry() == []


@pytest.mark.asyncio
async def test_registry_includes_both_tools_when_service_provided(
    service: SmartHomeMemoryService,
) -> None:
    from jarvis.agents.tools.registry import build_tool_registry

    tools = build_tool_registry(smart_home_memory=service)
    names = {t.name for t in tools}
    assert {"snapshot_device_state", "list_device_snapshots"} <= names


def test_exactly_two_tools_are_built(service: SmartHomeMemoryService) -> None:
    built = {t.name for t in build_smart_home_memory_tools(service)}
    assert built == {"snapshot_device_state", "list_device_snapshots"}


def test_no_recall_or_search_duplicate_tool_exists(service: SmartHomeMemoryService) -> None:
    """`recall_memory` already exists generically (`agents/tools/
    memory_tools.py`) -- this slice must not duplicate it."""
    built = {t.name for t in build_smart_home_memory_tools(service)}
    assert "recall_memory" not in built
    assert "search_memory" not in built
    assert "delete_snapshot" not in built
    assert "forget_snapshot" not in built


# --- snapshot_device_state -----------------------------------------------------------


@pytest.mark.asyncio
async def test_snapshot_tool_denied_without_grant(tools, smart_home: SmartHomeService) -> None:
    device = await _register_light(smart_home)
    result = await tools["snapshot_device_state"].ainvoke({"device_id": device.id})
    assert "Couldn't" in result
    assert "permission" in result.lower()


@pytest.mark.asyncio
async def test_snapshot_tool_succeeds_after_grant(
    tools,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    device = await _register_light(smart_home)
    fake_connector.states[_LIGHT_EXTERNAL_ID] = DeviceState(
        external_id=_LIGHT_EXTERNAL_ID, status="on", attributes={"brightness": 70}
    )

    result = await tools["snapshot_device_state"].ainvoke({"device_id": device.id})

    assert '"device_type": "light"' in result
    assert '"memory_id"' in result


@pytest.mark.asyncio
async def test_snapshot_tool_unsupported_category_reports_error_without_raising(
    tools, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    sensor = await smart_home.register_discovered_device(
        home.id, "Motion Sensor", device_type="sensor", external_id="sensor.motion"
    )

    result = await tools["snapshot_device_state"].ainvoke({"device_id": sensor.id})

    assert "Couldn't" in result
    assert "only supported for" in result


@pytest.mark.asyncio
async def test_snapshot_tool_unknown_device_reports_error_without_raising(tools) -> None:
    result = await tools["snapshot_device_state"].ainvoke({"device_id": "no-such-device"})
    assert isinstance(result, str)
    assert "Couldn't" in result


# --- list_device_snapshots -----------------------------------------------------------


@pytest.mark.asyncio
async def test_list_tool_denied_without_grant(tools) -> None:
    result = await tools["list_device_snapshots"].ainvoke({})
    assert "Couldn't" in result
    assert "permission" in result.lower()


@pytest.mark.asyncio
async def test_list_tool_reports_none_when_empty(tools, permissions: PermissionModel) -> None:
    await _grant(permissions)
    result = await tools["list_device_snapshots"].ainvoke({})
    assert "No device snapshots" in result


@pytest.mark.asyncio
async def test_list_tool_returns_created_snapshot(
    tools,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    device = await _register_light(smart_home)
    fake_connector.states[_LIGHT_EXTERNAL_ID] = DeviceState(
        external_id=_LIGHT_EXTERNAL_ID, status="on", attributes={}
    )
    await tools["snapshot_device_state"].ainvoke({"device_id": device.id})

    result = await tools["list_device_snapshots"].ainvoke({"device_id": device.id})

    assert device.id in result


# --- Confirmation metadata (Logic Contract §9) ----------------------------------------


def test_snapshot_device_state_not_in_confirm_required_tools() -> None:
    """The Logic Contract evaluated and rejected gating this tool
    behind interactive confirmation -- a snapshot touches one device
    and writes one memory row, never a physical device. Pinned here so
    a future change cannot silently add it without deliberately
    touching this test."""
    from jarvis.core.config.settings import AgentSettings

    assert "snapshot_device_state" not in AgentSettings().confirm_required_tools
    assert "list_device_snapshots" not in AgentSettings().confirm_required_tools
