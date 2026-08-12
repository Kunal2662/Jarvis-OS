"""Media Player agent tool tests -- Milestone 12 Appliance Control
(Media Player Core Slice).

Real ``MediaPlayerService`` over real (temp-file) SQLite, a real
``PermissionModel`` and a ``FakeDeviceConnector``, matching
``test_m12_vacuum_humidifier_tools.py``'s own fixtures.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("langchain_core")

from jarvis.agents.tools.media_player_tools import build_media_player_tools
from jarvis.core.connectivity.registry import ConnectorFactoryRegistry
from jarvis.core.events.event_bus import EventBus
from jarvis.core.interfaces.connectivity import DeviceState
from jarvis.core.plugins.permissions import PermissionModel
from jarvis.services.connectivity_service import ConnectivityService
from jarvis.services.media_player_service import (
    MEDIA_PLAYER_PRINCIPAL,
    SMART_HOME_SCOPE,
    MediaPlayerService,
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
def service(smart_home, connectivity, permissions) -> MediaPlayerService:
    return MediaPlayerService(
        smart_home=smart_home, connectivity=connectivity, permissions=permissions
    )


@pytest.fixture
def tools(service: MediaPlayerService):
    return {t.name: t for t in build_media_player_tools(service)}


async def _grant(permissions: PermissionModel) -> None:
    await permissions.grant(MEDIA_PLAYER_PRINCIPAL, SMART_HOME_SCOPE)


async def _register_media_player(smart_home: SmartHomeService):
    home = await smart_home.create_home("Primary Residence")
    return await smart_home.register_discovered_device(
        home.id,
        "Living Room Speaker",
        device_type="appliance",
        external_id=_EXTERNAL_ID,
        metadata={"connector_type": "home_assistant", "domain": "media_player"},
    )


# --- Registry registration -----------------------------------------------------


def test_registry_omits_tools_when_not_wired() -> None:
    from jarvis.agents.tools.registry import build_tool_registry

    assert build_tool_registry() == []


@pytest.mark.asyncio
async def test_registry_includes_all_eight_tools_when_service_provided(
    service: MediaPlayerService,
) -> None:
    from jarvis.agents.tools.registry import build_tool_registry

    tools = build_tool_registry(media_players=service)
    names = {t.name for t in tools}
    assert {
        "list_media_players",
        "get_media_player_state",
        "media_play",
        "media_pause",
        "media_stop",
        "media_next",
        "media_previous",
        "set_media_player_state",
    } <= names


def test_exactly_eight_tools_are_built(service: MediaPlayerService) -> None:
    built = {t.name for t in build_media_player_tools(service)}
    assert built == {
        "list_media_players",
        "get_media_player_state",
        "media_play",
        "media_pause",
        "media_stop",
        "media_next",
        "media_previous",
        "set_media_player_state",
    }


def test_no_volume_mute_source_specific_tools_exist(service: MediaPlayerService) -> None:
    built = {t.name for t in build_media_player_tools(service)}
    assert "set_volume" not in built
    assert "set_mute" not in built
    assert "select_source" not in built


# --- Read tools -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_media_players_tool_reports_none(tools) -> None:
    result = await tools["list_media_players"].ainvoke({})
    assert "No media players" in result


@pytest.mark.asyncio
async def test_get_media_player_state_tool(
    tools,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    device = await _register_media_player(smart_home)
    fake_connector.states[_EXTERNAL_ID] = DeviceState(
        external_id=_EXTERNAL_ID,
        status="playing",
        attributes={"volume_level": 0.7, "media_title": "Song"},
    )

    result = await tools["get_media_player_state"].ainvoke({"device_id": device.id})

    assert '"state": "playing"' in result
    assert '"volume_level": 0.7' in result
    assert '"media_title": "Song"' in result


# --- Transport tools ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_media_play_tool_denied_without_grant(tools, smart_home: SmartHomeService) -> None:
    device = await _register_media_player(smart_home)
    result = await tools["media_play"].ainvoke({"device_id": device.id})
    assert "Couldn't" in result
    assert "permission" in result.lower()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_name,wire_command",
    [
        ("media_play", "media_play"),
        ("media_pause", "media_pause"),
        ("media_stop", "media_stop"),
        ("media_next", "media_next_track"),
        ("media_previous", "media_previous_track"),
    ],
)
async def test_transport_tools_succeed_after_grant(
    tools,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
    tool_name: str,
    wire_command: str,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    device = await _register_media_player(smart_home)
    fake_connector.states[_EXTERNAL_ID] = DeviceState(
        external_id=_EXTERNAL_ID, status="playing", attributes={}
    )

    result = await tools[tool_name].ainvoke({"device_id": device.id})

    assert '"success": true' in result.lower()
    assert fake_connector.sent_commands == [(_EXTERNAL_ID, wire_command, {})]


@pytest.mark.asyncio
async def test_transport_tool_reports_unknown_device_without_raising(
    tools, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    result = await tools["media_play"].ainvoke({"device_id": "no-such-device"})
    assert "Couldn't" in result


# --- Merged state tool --------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_media_player_state_tool_denied_without_grant(
    tools, smart_home: SmartHomeService
) -> None:
    device = await _register_media_player(smart_home)
    result = await tools["set_media_player_state"].ainvoke({"device_id": device.id, "volume": 0.5})
    assert "Couldn't" in result
    assert "permission" in result.lower()


@pytest.mark.asyncio
async def test_set_media_player_state_tool_combined_mutation(
    tools,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    device = await _register_media_player(smart_home)
    fake_connector.states[_EXTERNAL_ID] = DeviceState(
        external_id=_EXTERNAL_ID, status="playing", attributes={}
    )

    result = await tools["set_media_player_state"].ainvoke(
        {"device_id": device.id, "volume": 0.4, "muted": True, "source": "Spotify"}
    )

    assert '"success": true' in result.lower()
    assert fake_connector.sent_commands == [
        (_EXTERNAL_ID, "volume_set", {"volume_level": 0.4}),
        (_EXTERNAL_ID, "volume_mute", {"is_volume_muted": True}),
        (_EXTERNAL_ID, "select_source", {"source": "Spotify"}),
    ]


@pytest.mark.asyncio
async def test_set_media_player_state_tool_reports_error_without_raising(tools) -> None:
    result = await tools["set_media_player_state"].ainvoke(
        {"device_id": "no-such-device", "volume": 0.5}
    )
    assert isinstance(result, str)
