"""Smart Home service -- Milestone 12 Task Group A (Smart Home Core).

Owns the Home / Zone / Room / Device / DeviceGroup domain: lifecycle,
CRUD, derived metadata, the search hook, and event publishing.
Structured to match ``WorkspaceService`` exactly -- an ``IDatabase``
opened per call via ``db.session()``, a repository constructed inside
that session, an optional ``EventBus``, and search methods a
``SearchSource`` wraps.

**What this service deliberately does not do.** It does not talk to a
real device. Discovery and pairing are domain-level status transitions
(``register_discovered_device`` / ``pair_device``) that a later
Connectivity Layer task group will drive from a real protocol scan --
see ``domain/smart_home/models.py``'s module docstring. It does not
implement automation, AI assistance, cameras, energy metrics, remote
access or cloud/Home Assistant sync -- those are separate modules in
M12's own 15-module list with their own task groups.

**Validation posture.** Types and statuses are checked against the
closed vocabularies in ``domain/smart_home/models.py`` and raise
``ServiceError`` on a miss, the same way ``WorkspaceService`` rejects an
unknown workspace status.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from jarvis.core.exceptions import ServiceError
from jarvis.core.interfaces.search import SearchResult
from jarvis.core.logging.logger import get_logger
from jarvis.domain.smart_home.models import (
    DEVICE_STATUSES,
    DEVICE_TYPES,
    HOME_STATUSES,
    HomeMetadata,
)
from jarvis.infrastructure.database.repositories.smart_home_repository import (
    DeviceGroupRepository,
    DeviceRepository,
    HomeRepository,
    RoomRepository,
    ZoneRepository,
)

if TYPE_CHECKING:
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.interfaces.database import IDatabase
    from jarvis.infrastructure.database.models import Device, DeviceGroup, Home, Room, Zone

_logger = get_logger("jarvis.services.smart_home")


class SmartHomeService:
    def __init__(
        self,
        *,
        database: IDatabase,
        event_bus: EventBus | None = None,
    ) -> None:
        self._db = database
        self._event_bus = event_bus

    # ------------------------------------------------------------------
    # Homes
    # ------------------------------------------------------------------
    async def create_home(self, name: str, *, description: str = "") -> Home:
        name = (name or "").strip()
        if not name:
            raise ServiceError("Cannot create a home with an empty name.")
        async with self._db.session() as sess:
            home = await HomeRepository(sess).add(name, description=description)  # type: ignore[arg-type]
            home_id = home.id
        await self._publish_home(home_id, action="created")
        _logger.info("Home created: {} ({})", name, home_id)
        return await self.require_home(home_id)

    async def get_home(self, home_id: str) -> Home | None:
        async with self._db.session() as sess:
            return await HomeRepository(sess).get(home_id)  # type: ignore[arg-type]

    async def require_home(self, home_id: str) -> Home:
        home = await self.get_home(home_id)
        if home is None:
            raise ServiceError(f"Home {home_id!r} does not exist.")
        return home

    async def list_homes(
        self, *, status: str | None = None, limit: int | None = None, offset: int = 0
    ) -> list[Home]:
        _validate(status, HOME_STATUSES, "home status")
        async with self._db.session() as sess:
            repo = HomeRepository(sess)  # type: ignore[arg-type]
            return await repo.list_homes(
                status=status, offset=offset, **({} if limit is None else {"limit": limit})
            )

    async def update_home(
        self,
        home_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        status: str | None = None,
    ) -> Home | None:
        _validate(status, HOME_STATUSES, "home status")
        async with self._db.session() as sess:
            home = await HomeRepository(sess).update(  # type: ignore[arg-type]
                home_id, name=name, description=description, status=status
            )
            if home is None:
                return None
        action = "archived" if status == "archived" else "updated"
        await self._publish_home(home_id, action=action)
        return await self.get_home(home_id)

    async def delete_home(self, home_id: str) -> bool:
        async with self._db.session() as sess:
            deleted = await HomeRepository(sess).delete(home_id)  # type: ignore[arg-type]
        if deleted:
            await self._publish_home(home_id, action="deleted")
        return deleted

    async def metadata(self, home_id: str) -> HomeMetadata:
        """Derived, never stored -- backs Device Health Monitoring and
        the Device Status Dashboard. See ``domain/smart_home/models.py``."""
        await self.require_home(home_id)
        async with self._db.session() as sess:
            repo = HomeRepository(sess)  # type: ignore[arg-type]
            rooms, zones, devices, paired, offline = await repo.counts(home_id)
            unreachable = await repo.unreachable_count(home_id)
        return HomeMetadata(
            home_id=home_id,
            room_count=rooms,
            zone_count=zones,
            device_count=devices,
            paired_device_count=paired,
            offline_device_count=offline,
            unreachable_device_count=unreachable,
        )

    # ------------------------------------------------------------------
    # Zones
    # ------------------------------------------------------------------
    async def create_zone(self, home_id: str, name: str, *, description: str = "") -> Zone:
        name = (name or "").strip()
        if not name:
            raise ServiceError("Cannot create a zone with an empty name.")
        await self.require_home(home_id)
        async with self._db.session() as sess:
            zone = await ZoneRepository(sess).add(home_id, name, description=description)  # type: ignore[arg-type]
            return zone

    async def get_zone(self, zone_id: str) -> Zone | None:
        async with self._db.session() as sess:
            return await ZoneRepository(sess).get(zone_id)  # type: ignore[arg-type]

    async def require_zone(self, zone_id: str) -> Zone:
        zone = await self.get_zone(zone_id)
        if zone is None:
            raise ServiceError(f"Zone {zone_id!r} does not exist.")
        return zone

    async def list_zones(
        self, *, home_id: str | None = None, limit: int | None = None, offset: int = 0
    ) -> list[Zone]:
        async with self._db.session() as sess:
            repo = ZoneRepository(sess)  # type: ignore[arg-type]
            return await repo.list_zones(
                home_id=home_id, offset=offset, **({} if limit is None else {"limit": limit})
            )

    async def update_zone(
        self, zone_id: str, *, name: str | None = None, description: str | None = None
    ) -> Zone | None:
        async with self._db.session() as sess:
            return await ZoneRepository(sess).update(zone_id, name=name, description=description)  # type: ignore[arg-type]

    async def delete_zone(self, zone_id: str) -> bool:
        """Deletes the zone and **keeps its rooms**, clearing their
        ``zone_id`` -- a zone is an organizing convenience, not a
        container a room's existence depends on."""
        async with self._db.session() as sess:
            zones = ZoneRepository(sess)  # type: ignore[arg-type]
            zone = await zones.get(zone_id)
            if zone is None:
                return False
            detached = await zones.clear_rooms(zone_id)
            await zones.delete(zone_id)
        if detached:
            _logger.info("Zone {} deleted; {} room(s) unassigned.", zone_id, detached)
        return True

    # ------------------------------------------------------------------
    # Rooms
    # ------------------------------------------------------------------
    async def create_room(
        self,
        home_id: str,
        name: str,
        *,
        description: str = "",
        zone_id: str | None = None,
    ) -> Room:
        name = (name or "").strip()
        if not name:
            raise ServiceError("Cannot create a room with an empty name.")
        await self.require_home(home_id)
        if zone_id is not None:
            zone = await self.require_zone(zone_id)
            if zone.home_id != home_id:
                raise ServiceError(
                    f"Zone {zone_id!r} belongs to a different home; a room cannot span two."
                )
        async with self._db.session() as sess:
            return await RoomRepository(sess).add(  # type: ignore[arg-type]
                home_id, name, description=description, zone_id=zone_id
            )

    async def get_room(self, room_id: str) -> Room | None:
        async with self._db.session() as sess:
            return await RoomRepository(sess).get(room_id)  # type: ignore[arg-type]

    async def require_room(self, room_id: str) -> Room:
        room = await self.get_room(room_id)
        if room is None:
            raise ServiceError(f"Room {room_id!r} does not exist.")
        return room

    async def list_rooms(
        self,
        *,
        home_id: str | None = None,
        zone_id: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Room]:
        async with self._db.session() as sess:
            repo = RoomRepository(sess)  # type: ignore[arg-type]
            return await repo.list_rooms(
                home_id=home_id,
                zone_id=zone_id,
                offset=offset,
                **({} if limit is None else {"limit": limit}),
            )

    async def update_room(
        self,
        room_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        zone_id: str | None = None,
        clear_zone: bool = False,
    ) -> Room | None:
        async with self._db.session() as sess:
            return await RoomRepository(sess).update(  # type: ignore[arg-type]
                room_id,
                name=name,
                description=description,
                zone_id=zone_id,
                clear_zone=clear_zone,
            )

    async def delete_room(self, room_id: str) -> bool:
        """Deletes the room and **keeps its devices**, clearing their
        ``room_id`` -- removing a room from a floor plan should not
        delete the devices that were in it, the same "reassign, don't
        cascade" choice ``delete_zone`` makes for rooms."""
        async with self._db.session() as sess:
            rooms = RoomRepository(sess)  # type: ignore[arg-type]
            room = await rooms.get(room_id)
            if room is None:
                return False
            detached = await rooms.detach_devices(room_id)
            await rooms.delete(room_id)
        if detached:
            _logger.info("Room {} deleted; {} device(s) unassigned.", room_id, detached)
        return True

    # ------------------------------------------------------------------
    # Devices
    # ------------------------------------------------------------------
    async def register_discovered_device(
        self,
        home_id: str,
        name: str,
        *,
        device_type: str = "other",
        room_id: str | None = None,
        manufacturer: str = "",
        model: str = "",
        external_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Device:
        """Records a discovery result as a real ``Device`` row in
        ``status="discovered"``.

        Nothing in this task group produces one by talking to real
        hardware -- see this module's own docstring and
        ``domain/smart_home/models.py``'s. A later Connectivity Layer
        task group calls this once a real scan finds something; a
        manual "add a device I already know about" flow can call it
        too, since the shape does not care which.

        ``metadata`` (Milestone 12 Task Group B) is written to
        ``Device.metadata_json`` -- the column Task Group A built
        specifically "so a later task group has somewhere to write."
        Connectivity Layer stores ``{"connector_type": ...}`` here so a
        command can later be routed back to the connector that
        discovered the device, without a schema change.

        **Not idempotent by itself.** Calling this twice with the same
        ``external_id`` creates two rows -- deliberately, so a manual
        "add a device I already know about" caller is never silently
        turned into a no-op. A caller that re-discovers the same
        physical device on every poll (Connectivity Layer's own job)
        is expected to check ``get_device_by_external_id`` first and
        call ``update_device``/``report_device_state`` instead when a
        match exists.
        """
        name = (name or "").strip()
        if not name:
            raise ServiceError("Cannot register a device with an empty name.")
        _validate(device_type, DEVICE_TYPES, "device type", required=True)
        await self.require_home(home_id)
        if room_id is not None:
            room = await self.require_room(room_id)
            if room.home_id != home_id:
                raise ServiceError(
                    f"Room {room_id!r} belongs to a different home; a device cannot span two."
                )
        metadata_json = json.dumps(metadata) if metadata else "{}"
        async with self._db.session() as sess:
            device = await DeviceRepository(sess).add(  # type: ignore[arg-type]
                home_id,
                name,
                device_type=device_type,
                status="discovered",
                room_id=room_id,
                manufacturer=manufacturer,
                model=model,
                external_id=external_id,
                metadata_json=metadata_json,
            )
            device_id = device.id
        await self._publish_device(device_id, home_id, action="created", status="discovered")
        return await self.require_device(device_id)

    async def get_device_by_external_id(self, home_id: str, external_id: str) -> Device | None:
        """Milestone 12 Task Group B's own discovery-idempotency check
        -- a connector calls this before ``register_discovered_device``
        to decide whether a discovery result is a new device or an
        update to one already known."""
        async with self._db.session() as sess:
            return await DeviceRepository(sess).get_by_external_id(  # type: ignore[arg-type]
                home_id, external_id
            )

    async def report_device_state(
        self, device_id: str, *, status: str, touch_last_seen: bool = True
    ) -> Device | None:
        """Milestone 12 Task Group B's own method: a connector's real
        state read drives a device's status here, generalizing
        ``pair_device``'s single ``discovered`` -> ``paired``
        transition to any status a connector actually reports
        (``paired`` -> ``offline``, ``offline`` -> ``paired``, ...).
        This is what finally gives ``HomeMetadata.offline_device_count``
        / ``unreachable_device_count`` real data -- both fields existed
        since Task Group A with nothing to drive them.
        """
        _validate(status, DEVICE_STATUSES, "device status", required=True)
        device = await self.get_device(device_id)
        if device is None:
            return None
        async with self._db.session() as sess:
            await DeviceRepository(sess).update(  # type: ignore[arg-type]
                device_id, status=status, touch_last_seen=touch_last_seen
            )
        await self._publish_device(
            device_id, device.home_id, action="status_changed", status=status
        )
        return await self.get_device(device_id)

    async def pair_device(self, device_id: str) -> Device | None:
        """``discovered`` -> ``paired``, directly -- this task group has
        no real pairing handshake to run, so there is no intermediate
        ``pairing`` state to hold here. A future Connectivity Layer task
        group that adds a real, multi-step pairing flow can introduce
        one without changing this method's contract, since callers
        already treat the return value as "the device's new state,"
        not "pairing succeeded synchronously."
        """
        device = await self.get_device(device_id)
        if device is None:
            raise ServiceError(f"Device {device_id!r} does not exist.")
        if device.status not in {"discovered", "offline", "unreachable"}:
            raise ServiceError(
                f"Device {device_id!r} is {device.status!r}; only a discovered, offline or "
                "unreachable device can be (re-)paired."
            )
        async with self._db.session() as sess:
            await DeviceRepository(sess).update(  # type: ignore[arg-type]
                device_id, status="paired", touch_last_seen=True
            )
        await self._publish_device(
            device_id, device.home_id, action="status_changed", status="paired"
        )
        return await self.get_device(device_id)

    async def get_device(self, device_id: str) -> Device | None:
        async with self._db.session() as sess:
            return await DeviceRepository(sess).get(device_id)  # type: ignore[arg-type]

    async def require_device(self, device_id: str) -> Device:
        device = await self.get_device(device_id)
        if device is None:
            raise ServiceError(f"Device {device_id!r} does not exist.")
        return device

    async def list_devices(
        self,
        *,
        home_id: str | None = None,
        room_id: str | None = None,
        device_type: str | None = None,
        status: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Device]:
        _validate(device_type, DEVICE_TYPES, "device type")
        _validate(status, DEVICE_STATUSES, "device status")
        async with self._db.session() as sess:
            repo = DeviceRepository(sess)  # type: ignore[arg-type]
            return await repo.list_devices(
                home_id=home_id,
                room_id=room_id,
                device_type=device_type,
                status=status,
                offset=offset,
                **({} if limit is None else {"limit": limit}),
            )

    async def update_device(
        self,
        device_id: str,
        *,
        name: str | None = None,
        device_type: str | None = None,
        room_id: str | None = None,
        clear_room: bool = False,
        manufacturer: str | None = None,
        model: str | None = None,
    ) -> Device | None:
        """Renames, re-categorizes or re-homes a device. **Not** how a
        device's ``status`` changes -- that is ``pair_device`` (or a
        future Connectivity Layer health check), kept as its own method
        because a status transition publishes ``action="status_changed"``
        and this always publishes ``"updated"``; folding both into one
        method would make a caller's own action field unreliable."""
        _validate(device_type, DEVICE_TYPES, "device type")
        async with self._db.session() as sess:
            device = await DeviceRepository(sess).update(  # type: ignore[arg-type]
                device_id,
                name=name,
                device_type=device_type,
                room_id=room_id,
                clear_room=clear_room,
                manufacturer=manufacturer,
                model=model,
            )
            if device is None:
                return None
            home_id = device.home_id
        await self._publish_device(device_id, home_id, action="updated", status="")
        return await self.get_device(device_id)

    async def delete_device(self, device_id: str) -> bool:
        async with self._db.session() as sess:
            devices = DeviceRepository(sess)  # type: ignore[arg-type]
            device = await devices.get(device_id)
            if device is None:
                return False
            home_id = device.home_id
            await devices.delete(device_id)
        await self._publish_device(device_id, home_id, action="deleted", status="")
        return True

    # ------------------------------------------------------------------
    # Device groups
    # ------------------------------------------------------------------
    async def create_device_group(
        self, home_id: str, name: str, *, description: str = ""
    ) -> DeviceGroup:
        name = (name or "").strip()
        if not name:
            raise ServiceError("Cannot create a device group with an empty name.")
        await self.require_home(home_id)
        async with self._db.session() as sess:
            return await DeviceGroupRepository(sess).add(  # type: ignore[arg-type]
                home_id, name, description=description
            )

    async def get_device_group(self, group_id: str) -> DeviceGroup | None:
        async with self._db.session() as sess:
            return await DeviceGroupRepository(sess).get(group_id)  # type: ignore[arg-type]

    async def list_device_groups(
        self, *, home_id: str | None = None, limit: int | None = None, offset: int = 0
    ) -> list[DeviceGroup]:
        async with self._db.session() as sess:
            repo = DeviceGroupRepository(sess)  # type: ignore[arg-type]
            return await repo.list_groups(
                home_id=home_id, offset=offset, **({} if limit is None else {"limit": limit})
            )

    async def delete_device_group(self, group_id: str) -> bool:
        """Deletes the group. Its membership rows cascade (a group
        membership has no meaning once the group is gone); the devices
        themselves are untouched -- ``DeviceGroupMember`` is the only
        thing ``ON DELETE CASCADE`` reaches from ``smart_home_device_
        groups``."""
        async with self._db.session() as sess:
            return await DeviceGroupRepository(sess).delete(group_id)  # type: ignore[arg-type]

    async def add_device_to_group(self, group_id: str, device_id: str) -> bool:
        group = await self.get_device_group(group_id)
        if group is None:
            raise ServiceError(f"Device group {group_id!r} does not exist.")
        device = await self.require_device(device_id)
        if device.home_id != group.home_id:
            raise ServiceError(
                f"Device {device_id!r} belongs to a different home than group {group_id!r}."
            )
        async with self._db.session() as sess:
            return await DeviceGroupRepository(sess).add_member(group_id, device_id)  # type: ignore[arg-type]

    async def remove_device_from_group(self, group_id: str, device_id: str) -> bool:
        async with self._db.session() as sess:
            return await DeviceGroupRepository(sess).remove_member(group_id, device_id)  # type: ignore[arg-type]

    async def list_group_members(self, group_id: str) -> list[Device]:
        async with self._db.session() as sess:
            return await DeviceGroupRepository(sess).list_members(group_id)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Search hooks
    # ------------------------------------------------------------------
    async def search_homes(self, query: str, *, top_k: int = 10) -> list[SearchResult]:
        query = (query or "").strip()
        if not query:
            return []
        async with self._db.session() as sess:
            hits = await HomeRepository(sess).search(query, limit=top_k)  # type: ignore[arg-type]
        return [
            SearchResult(
                id=h.id,
                title=h.name,
                content=h.description,
                source="homes",
                score=1.0 if h.status == "active" else 0.5,
                uri=f"home://{h.id}",
                metadata={"status": h.status},
            )
            for h in hits
        ]

    async def search_devices(self, query: str, *, top_k: int = 10) -> list[SearchResult]:
        query = (query or "").strip()
        if not query:
            return []
        async with self._db.session() as sess:
            hits = await DeviceRepository(sess).search(query, limit=top_k)  # type: ignore[arg-type]
        return [
            SearchResult(
                id=d.id,
                title=d.name,
                content=f"{d.manufacturer} {d.model}".strip(),
                source="devices",
                score=1.0 if d.status == "paired" else 0.6,
                uri=f"device://{d.id}",
                metadata={"status": d.status, "device_type": d.device_type, "home_id": d.home_id},
            )
            for d in hits
        ]

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    async def _publish_home(self, home_id: str, *, action: str) -> None:
        if self._event_bus is None:
            return
        from jarvis.core.events.events import HomeUpdatedEvent

        await self._event_bus.publish(HomeUpdatedEvent(home_id=home_id, action=action))

    async def _publish_device(
        self, device_id: str, home_id: str, *, action: str, status: str
    ) -> None:
        if self._event_bus is None:
            return
        from jarvis.core.events.events import DeviceUpdatedEvent

        await self._event_bus.publish(
            DeviceUpdatedEvent(device_id=device_id, home_id=home_id, action=action, status=status)
        )


def _validate(
    value: str | None, allowed: frozenset[str], label: str, *, required: bool = False
) -> None:
    if value is None:
        if required:
            raise ServiceError(f"A {label} is required; allowed: {sorted(allowed)}.")
        return
    if value not in allowed:
        raise ServiceError(f"Unknown {label} {value!r}; allowed: {sorted(allowed)}.")
