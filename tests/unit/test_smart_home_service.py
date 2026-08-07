"""SmartHomeService tests -- Milestone 12 Task Group A (Smart Home Core).

Real (temp-file) SQLite throughout, matching
``test_workspace_service.py``'s established pattern -- these are the
repository tests as well as the service tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core.events.event_bus import EventBus
from jarvis.core.events.events import DeviceUpdatedEvent, HomeUpdatedEvent
from jarvis.core.exceptions import ServiceError
from jarvis.services.smart_home_service import SmartHomeService


def _settings(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JARVIS_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'jarvis.db'}")

    from jarvis.core.config import settings as settings_mod

    settings_mod.load_settings.cache_clear()  # type: ignore[attr-defined]
    return settings_mod.load_settings()


@pytest.fixture
async def service(tmp_path: Path, monkeypatch):
    settings = _settings(tmp_path, monkeypatch)
    from jarvis.infrastructure.database.sqlite_client import SQLiteDatabase

    db = SQLiteDatabase(settings.db)
    await db.initialize()
    try:
        yield SmartHomeService(database=db, event_bus=EventBus())
    finally:
        await db.dispose()


@pytest.fixture
async def recorder(tmp_path: Path, monkeypatch):
    """A service whose bus records every relayed smart-home event."""
    settings = _settings(tmp_path, monkeypatch)
    from jarvis.infrastructure.database.sqlite_client import SQLiteDatabase

    db = SQLiteDatabase(settings.db)
    await db.initialize()
    bus = EventBus()
    seen: list[object] = []
    for event_type in (HomeUpdatedEvent, DeviceUpdatedEvent):
        bus.subscribe(event_type, lambda e: seen.append(e) or None)
    try:
        yield SmartHomeService(database=db, event_bus=bus), seen
    finally:
        await db.dispose()


# --- Homes -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_and_read_a_home(service: SmartHomeService) -> None:
    home = await service.create_home("Lake House", description="weekend place")

    assert home.name == "Lake House"
    assert home.status == "active"
    fetched = await service.get_home(home.id)
    assert fetched is not None
    assert fetched.description == "weekend place"


@pytest.mark.asyncio
async def test_empty_home_name_is_rejected(service: SmartHomeService) -> None:
    with pytest.raises(ServiceError, match="empty name"):
        await service.create_home("   ")


@pytest.mark.asyncio
async def test_multi_home_support_is_just_more_than_one_row(service: SmartHomeService) -> None:
    """Multi-Home Support (Smart Home Core's own module item) is not a
    feature flag -- it is the absence of a constraint. Two homes are
    two independent rows, neither aware of the other."""
    first = await service.create_home("Primary Residence")
    second = await service.create_home("Lake House")

    homes = await service.list_homes()
    assert {h.id for h in homes} == {first.id, second.id}


@pytest.mark.asyncio
async def test_unknown_home_status_filter_is_rejected(service: SmartHomeService) -> None:
    with pytest.raises(ServiceError, match="Unknown home status"):
        await service.list_homes(status="vacant")


@pytest.mark.asyncio
async def test_archiving_a_home_publishes_archived_not_updated(recorder) -> None:
    service, seen = recorder
    home = await service.create_home("Cabin")
    seen.clear()

    await service.update_home(home.id, status="archived")

    assert len(seen) == 1
    assert seen[0].action == "archived"  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_deleting_a_missing_home_is_false_not_an_error(service: SmartHomeService) -> None:
    assert await service.delete_home("does-not-exist") is False


# --- Zones -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_zone_requires_a_real_home(service: SmartHomeService) -> None:
    with pytest.raises(ServiceError, match="does not exist"):
        await service.create_zone("no-such-home", "Downstairs")


@pytest.mark.asyncio
async def test_deleting_a_zone_unassigns_its_rooms_rather_than_deleting_them(
    service: SmartHomeService,
) -> None:
    home = await service.create_home("Primary Residence")
    zone = await service.create_zone(home.id, "Downstairs")
    room = await service.create_room(home.id, "Living Room", zone_id=zone.id)

    assert await service.delete_zone(zone.id) is True

    survived = await service.get_room(room.id)
    assert survived is not None
    assert survived.zone_id is None


# --- Rooms ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_room_cannot_reference_a_zone_from_a_different_home(
    service: SmartHomeService,
) -> None:
    home_a = await service.create_home("House A")
    home_b = await service.create_home("House B")
    zone_b = await service.create_zone(home_b.id, "Upstairs")

    with pytest.raises(ServiceError, match="different home"):
        await service.create_room(home_a.id, "Bedroom", zone_id=zone_b.id)


@pytest.mark.asyncio
async def test_deleting_a_room_unassigns_its_devices_rather_than_deleting_them(
    service: SmartHomeService,
) -> None:
    home = await service.create_home("Primary Residence")
    room = await service.create_room(home.id, "Kitchen")
    device = await service.register_discovered_device(home.id, "Fridge Sensor", room_id=room.id)

    assert await service.delete_room(room.id) is True

    survived = await service.get_device(device.id)
    assert survived is not None
    assert survived.room_id is None


# --- Devices: discovery + pairing ----------------------------------------------


@pytest.mark.asyncio
async def test_registering_a_discovered_device_starts_in_discovered_status(
    service: SmartHomeService,
) -> None:
    home = await service.create_home("Primary Residence")

    device = await service.register_discovered_device(home.id, "Hallway Light", device_type="light")

    assert device.status == "discovered"
    assert device.device_type == "light"
    assert device.last_seen_at is None


@pytest.mark.asyncio
async def test_unknown_device_type_is_rejected(service: SmartHomeService) -> None:
    home = await service.create_home("Primary Residence")
    with pytest.raises(ServiceError, match="Unknown device type"):
        await service.register_discovered_device(home.id, "Mystery Gadget", device_type="drone")


@pytest.mark.asyncio
async def test_device_cannot_be_registered_in_a_room_from_a_different_home(
    service: SmartHomeService,
) -> None:
    home_a = await service.create_home("House A")
    home_b = await service.create_home("House B")
    room_b = await service.create_room(home_b.id, "Garage")

    with pytest.raises(ServiceError, match="different home"):
        await service.register_discovered_device(home_a.id, "Door Sensor", room_id=room_b.id)


@pytest.mark.asyncio
async def test_pairing_a_discovered_device_transitions_it_to_paired(
    service: SmartHomeService,
) -> None:
    home = await service.create_home("Primary Residence")
    device = await service.register_discovered_device(
        home.id, "Front Door Lock", device_type="lock"
    )

    paired = await service.pair_device(device.id)

    assert paired is not None
    assert paired.status == "paired"
    assert paired.last_seen_at is not None


@pytest.mark.asyncio
async def test_pairing_an_already_paired_device_is_rejected(service: SmartHomeService) -> None:
    home = await service.create_home("Primary Residence")
    device = await service.register_discovered_device(
        home.id, "Thermostat", device_type="thermostat"
    )
    await service.pair_device(device.id)

    with pytest.raises(ServiceError, match="only a discovered, offline or unreachable"):
        await service.pair_device(device.id)


@pytest.mark.asyncio
async def test_pairing_publishes_status_changed_not_updated(recorder) -> None:
    service, seen = recorder
    home = await service.create_home("Primary Residence")
    device = await service.register_discovered_device(home.id, "Smart Plug", device_type="switch")
    seen.clear()

    await service.pair_device(device.id)

    device_events = [e for e in seen if isinstance(e, DeviceUpdatedEvent)]
    assert len(device_events) == 1
    assert device_events[0].action == "status_changed"
    assert device_events[0].status == "paired"


@pytest.mark.asyncio
async def test_updating_a_device_does_not_change_its_status(service: SmartHomeService) -> None:
    """``update_device`` renames/re-categorizes/re-homes; it is not how
    status changes -- see the service's own docstring for why that is
    a separate method."""
    home = await service.create_home("Primary Residence")
    device = await service.register_discovered_device(home.id, "Hallway Light", device_type="light")

    updated = await service.update_device(device.id, name="Upstairs Hallway Light")

    assert updated is not None
    assert updated.name == "Upstairs Hallway Light"
    assert updated.status == "discovered"


# --- Device health / status dashboard -------------------------------------------


@pytest.mark.asyncio
async def test_home_metadata_reports_derived_device_counts(service: SmartHomeService) -> None:
    home = await service.create_home("Primary Residence")
    zone = await service.create_zone(home.id, "Downstairs")
    room = await service.create_room(home.id, "Living Room", zone_id=zone.id)
    paired = await service.register_discovered_device(
        home.id, "TV", room_id=room.id, device_type="appliance"
    )
    await service.pair_device(paired.id)
    discovered_only = await service.register_discovered_device(
        home.id, "Sensor", device_type="sensor"
    )

    metadata = await service.metadata(home.id)

    assert metadata.room_count == 1
    assert metadata.zone_count == 1
    assert metadata.device_count == 2
    assert metadata.paired_device_count == 1
    # `discovered_only` never left "discovered", so it counts toward
    # neither `paired` nor `offline`/`unreachable` -- those two are a
    # future health check's job (no Connectivity Layer exists yet to
    # drive one), not something this task group's own test should fake
    # by writing to the repository directly.
    assert discovered_only.status == "discovered"
    assert metadata.offline_device_count == 0
    assert metadata.unreachable_device_count == 0


@pytest.mark.asyncio
async def test_metadata_requires_a_real_home(service: SmartHomeService) -> None:
    with pytest.raises(ServiceError, match="does not exist"):
        await service.metadata("no-such-home")


# --- Device groups ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_device_group_membership_round_trip(service: SmartHomeService) -> None:
    home = await service.create_home("Primary Residence")
    group = await service.create_device_group(home.id, "All Lights")
    light = await service.register_discovered_device(home.id, "Kitchen Light", device_type="light")

    added = await service.add_device_to_group(group.id, light.id)
    members = await service.list_group_members(group.id)

    assert added is True
    assert [m.id for m in members] == [light.id]

    removed = await service.remove_device_from_group(group.id, light.id)
    assert removed is True
    assert await service.list_group_members(group.id) == []


@pytest.mark.asyncio
async def test_adding_the_same_device_to_a_group_twice_is_idempotent(
    service: SmartHomeService,
) -> None:
    home = await service.create_home("Primary Residence")
    group = await service.create_device_group(home.id, "All Lights")
    light = await service.register_discovered_device(home.id, "Kitchen Light", device_type="light")

    first = await service.add_device_to_group(group.id, light.id)
    second = await service.add_device_to_group(group.id, light.id)

    assert first is True
    assert second is False
    assert len(await service.list_group_members(group.id)) == 1


@pytest.mark.asyncio
async def test_device_group_cannot_span_two_homes(service: SmartHomeService) -> None:
    home_a = await service.create_home("House A")
    home_b = await service.create_home("House B")
    group_a = await service.create_device_group(home_a.id, "All Lights")
    device_b = await service.register_discovered_device(
        home_b.id, "Porch Light", device_type="light"
    )

    with pytest.raises(ServiceError, match="different home"):
        await service.add_device_to_group(group_a.id, device_b.id)


@pytest.mark.asyncio
async def test_deleting_a_device_group_does_not_delete_its_devices(
    service: SmartHomeService,
) -> None:
    home = await service.create_home("Primary Residence")
    group = await service.create_device_group(home.id, "All Lights")
    light = await service.register_discovered_device(home.id, "Kitchen Light", device_type="light")
    await service.add_device_to_group(group.id, light.id)

    assert await service.delete_device_group(group.id) is True
    assert await service.get_device(light.id) is not None


# --- Search hooks -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_homes_matches_name_and_description(service: SmartHomeService) -> None:
    await service.create_home("Lake House", description="the cabin up north")
    await service.create_home("City Apartment")

    results = await service.search_homes("cabin")

    assert len(results) == 1
    assert results[0].source == "homes"


@pytest.mark.asyncio
async def test_search_devices_matches_manufacturer(service: SmartHomeService) -> None:
    home = await service.create_home("Primary Residence")
    await service.register_discovered_device(
        home.id, "Living Room Bulb", device_type="light", manufacturer="Philips"
    )

    results = await service.search_devices("philips")

    assert len(results) == 1
    assert results[0].source == "devices"


@pytest.mark.asyncio
async def test_empty_search_query_returns_nothing(service: SmartHomeService) -> None:
    assert await service.search_homes("") == []
    assert await service.search_devices("   ") == []
