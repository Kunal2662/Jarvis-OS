"""ConnectivityService tests -- Milestone 12 Task Group B, Phase 1.

Real (temp-file) SQLite ``SmartHomeService`` throughout, matching
``test_smart_home_service.py``'s own pattern -- these exercise the
orchestration layer against a real domain service, with only the
connector itself faked (there is no real connector until Phase 2).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from jarvis.core.connectivity.registry import ConnectorFactoryRegistry
from jarvis.core.events.event_bus import EventBus
from jarvis.core.events.events import ConnectivityStatusChangedEvent
from jarvis.core.exceptions import ServiceError
from jarvis.core.interfaces.connectivity import (
    ConnectorNotConnectedError,
    DeviceState,
    DiscoveredDevice,
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
async def smart_home(tmp_path: Path, monkeypatch):
    settings = _settings(tmp_path, monkeypatch)
    from jarvis.infrastructure.database.sqlite_client import SQLiteDatabase

    db = SQLiteDatabase(settings.db)
    await db.initialize()
    try:
        yield SmartHomeService(database=db, event_bus=EventBus())
    finally:
        await db.dispose()


@pytest.fixture
def fake_connector() -> FakeDeviceConnector:
    return FakeDeviceConnector()


@pytest.fixture
def registry(fake_connector: FakeDeviceConnector) -> ConnectorFactoryRegistry:
    reg = ConnectorFactoryRegistry()
    reg.register("home_assistant", lambda config: fake_connector)
    return reg


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def service(
    registry: ConnectorFactoryRegistry, smart_home: SmartHomeService, bus: EventBus
) -> ConnectivityService:
    return ConnectivityService(registry=registry, smart_home=smart_home, event_bus=bus)


@pytest.fixture
def recorder(bus: EventBus) -> list[object]:
    seen: list[object] = []
    bus.subscribe(ConnectivityStatusChangedEvent, lambda e: seen.append(e) or None)
    return seen


# --- Connector lifecycle -------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_creates_and_connects_the_connector(
    service: ConnectivityService, fake_connector: FakeDeviceConnector
) -> None:
    await service.connect("home_assistant")

    assert fake_connector.connect_calls == 1
    assert service.is_connected("home_assistant") is True
    assert service.connected_types == ("home_assistant",)


@pytest.mark.asyncio
async def test_connect_is_idempotent_reuses_the_same_instance(
    service: ConnectivityService, fake_connector: FakeDeviceConnector
) -> None:
    await service.connect("home_assistant")
    await service.connect("home_assistant")

    # Same fake instance reconnected, not a second one created.
    assert fake_connector.connect_calls == 2
    assert service.connected_types == ("home_assistant",)


@pytest.mark.asyncio
async def test_connect_publishes_connecting_then_connected(
    service: ConnectivityService, recorder: list[object]
) -> None:
    await service.connect("home_assistant")

    statuses = [e.status for e in recorder]  # type: ignore[attr-defined]
    assert statuses == ["connecting", "connected"]


@pytest.mark.asyncio
async def test_disconnect_on_an_unknown_type_is_a_no_op(service: ConnectivityService) -> None:
    await service.disconnect("home_assistant")  # must not raise
    assert service.is_connected("home_assistant") is False


@pytest.mark.asyncio
async def test_disconnect_tears_down_and_forgets_the_connector(
    service: ConnectivityService, fake_connector: FakeDeviceConnector
) -> None:
    await service.connect("home_assistant")

    await service.disconnect("home_assistant")

    assert fake_connector.disconnect_calls == 1
    assert service.is_connected("home_assistant") is False
    assert service.connected_types == ()


# --- Discovery -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_discovery_requires_a_connected_connector(
    service: ConnectivityService, smart_home: SmartHomeService
) -> None:
    home = await smart_home.create_home("Primary Residence")

    with pytest.raises(ConnectorNotConnectedError):
        await service.run_discovery("home_assistant", home.id)


@pytest.mark.asyncio
async def test_discovery_registers_new_devices(
    service: ConnectivityService,
    smart_home: SmartHomeService,
    fake_connector: FakeDeviceConnector,
) -> None:
    home = await smart_home.create_home("Primary Residence")
    fake_connector.devices = [
        DiscoveredDevice(external_id="ha-1", name="Hallway Light", device_type="light"),
    ]
    await service.connect("home_assistant")

    devices = await service.run_discovery("home_assistant", home.id)

    assert len(devices) == 1
    assert devices[0].name == "Hallway Light"
    assert devices[0].status == "discovered"
    registered = await smart_home.get_device_by_external_id(home.id, "ha-1")
    assert registered is not None


@pytest.mark.asyncio
async def test_discovery_is_idempotent_by_home_and_external_id(
    service: ConnectivityService,
    smart_home: SmartHomeService,
    fake_connector: FakeDeviceConnector,
) -> None:
    home = await smart_home.create_home("Primary Residence")
    fake_connector.devices = [
        DiscoveredDevice(external_id="ha-1", name="Hallway Light", device_type="light"),
    ]
    await service.connect("home_assistant")

    await service.run_discovery("home_assistant", home.id)
    second = await service.run_discovery("home_assistant", home.id)

    assert len(second) == 1
    all_devices = await smart_home.list_devices(home_id=home.id)
    assert len(all_devices) == 1


@pytest.mark.asyncio
async def test_discovered_device_records_its_connector_type(
    service: ConnectivityService,
    smart_home: SmartHomeService,
    fake_connector: FakeDeviceConnector,
) -> None:
    home = await smart_home.create_home("Primary Residence")
    fake_connector.devices = [DiscoveredDevice(external_id="ha-1", name="Plug")]
    await service.connect("home_assistant")

    [device] = await service.run_discovery("home_assistant", home.id)

    assert json.loads(device.metadata_json or "{}")["connector_type"] == "home_assistant"


# --- State + commands ------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_device_state_maps_and_reports_status(
    service: ConnectivityService,
    smart_home: SmartHomeService,
    fake_connector: FakeDeviceConnector,
) -> None:
    home = await smart_home.create_home("Primary Residence")
    fake_connector.devices = [DiscoveredDevice(external_id="ha-1", name="Plug")]
    await service.connect("home_assistant")
    [device] = await service.run_discovery("home_assistant", home.id)
    fake_connector.states["ha-1"] = DeviceState(
        external_id="ha-1", status="on", observed_at=datetime.now(UTC)
    )

    refreshed = await service.refresh_device_state(device.id)

    assert refreshed is not None
    assert refreshed.status == "paired"


@pytest.mark.asyncio
async def test_refresh_device_state_maps_offline(
    service: ConnectivityService,
    smart_home: SmartHomeService,
    fake_connector: FakeDeviceConnector,
) -> None:
    home = await smart_home.create_home("Primary Residence")
    fake_connector.devices = [DiscoveredDevice(external_id="ha-1", name="Plug")]
    await service.connect("home_assistant")
    [device] = await service.run_discovery("home_assistant", home.id)
    fake_connector.states["ha-1"] = DeviceState(external_id="ha-1", status="offline")

    refreshed = await service.refresh_device_state(device.id)

    assert refreshed is not None
    assert refreshed.status == "offline"


@pytest.mark.asyncio
async def test_refresh_device_state_on_a_device_with_no_connector_is_none(
    service: ConnectivityService, smart_home: SmartHomeService
) -> None:
    home = await smart_home.create_home("Primary Residence")
    manual = await smart_home.register_discovered_device(home.id, "Manually Added Sensor")

    assert await service.refresh_device_state(manual.id) is None


@pytest.mark.asyncio
async def test_send_command_routes_to_the_owning_connector(
    service: ConnectivityService,
    smart_home: SmartHomeService,
    fake_connector: FakeDeviceConnector,
) -> None:
    home = await smart_home.create_home("Primary Residence")
    fake_connector.devices = [DiscoveredDevice(external_id="ha-1", name="Lock")]
    await service.connect("home_assistant")
    [device] = await service.run_discovery("home_assistant", home.id)

    result = await service.send_command(device.id, "lock", {"code": "1234"})

    assert result.success is True
    assert fake_connector.sent_commands == [("ha-1", "lock", {"code": "1234"})]


@pytest.mark.asyncio
async def test_send_command_reports_a_device_level_rejection_without_raising(
    service: ConnectivityService,
    smart_home: SmartHomeService,
    fake_connector: FakeDeviceConnector,
) -> None:
    home = await smart_home.create_home("Primary Residence")
    fake_connector.devices = [DiscoveredDevice(external_id="ha-1", name="Lock")]
    await service.connect("home_assistant")
    [device] = await service.run_discovery("home_assistant", home.id)
    fake_connector.next_command_succeeds = False

    result = await service.send_command(device.id, "lock", {})

    assert result.success is False
    assert result.detail == "fake rejection"


@pytest.mark.asyncio
async def test_send_command_on_a_device_with_no_recorded_connector_raises(
    service: ConnectivityService, smart_home: SmartHomeService
) -> None:
    home = await smart_home.create_home("Primary Residence")
    manual = await smart_home.register_discovered_device(home.id, "Manually Added Sensor")

    with pytest.raises(ConnectorNotConnectedError, match="no recorded connector"):
        await service.send_command(manual.id, "toggle", {})


@pytest.mark.asyncio
async def test_send_command_on_a_missing_device_raises(service: ConnectivityService) -> None:
    with pytest.raises(ServiceError, match="does not exist"):
        await service.send_command("no-such-device", "toggle", {})


@pytest.mark.asyncio
async def test_send_command_requires_the_connector_to_be_connected(
    service: ConnectivityService,
    smart_home: SmartHomeService,
    fake_connector: FakeDeviceConnector,
) -> None:
    home = await smart_home.create_home("Primary Residence")
    fake_connector.devices = [DiscoveredDevice(external_id="ha-1", name="Lock")]
    await service.connect("home_assistant")
    [device] = await service.run_discovery("home_assistant", home.id)
    await service.disconnect("home_assistant")

    with pytest.raises(ConnectorNotConnectedError):
        await service.send_command(device.id, "lock", {})
