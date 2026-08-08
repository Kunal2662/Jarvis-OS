"""Smart Home repositories -- Milestone 12 Task Group A (Smart Home Core).

Five repositories over ``homes`` / ``smart_home_zones`` /
``smart_home_rooms`` / ``smart_home_devices`` /
``smart_home_device_groups``, following ``WorkspaceRepository``'s shape
exactly: constructed with an ``AsyncSession``, one class per aggregate,
no session or transaction management of its own (the service owns that
via ``db.session()``), and ``flush()`` rather than ``commit()`` after an
insert so the caller's transaction boundary stays the caller's.
"""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from jarvis.infrastructure.database.models import (
    Device,
    DeviceGroup,
    DeviceGroupMember,
    Home,
    Room,
    Zone,
    _utcnow,
)


class HomeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, name: str, *, description: str = "", settings_json: str = "{}") -> Home:
        home = Home(name=name, description=description, settings_json=settings_json)
        self._s.add(home)
        await self._s.flush()
        return home

    async def get(self, home_id: str) -> Home | None:
        return await self._s.get(Home, home_id)

    async def list_homes(
        self, *, status: str | None = None, limit: int = 200, offset: int = 0
    ) -> list[Home]:
        stmt = select(Home).order_by(Home.created_at.desc()).limit(limit).offset(offset)
        if status is not None:
            stmt = stmt.where(Home.status == status)
        return list((await self._s.execute(stmt)).scalars().all())

    async def update(
        self,
        home_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        status: str | None = None,
        settings_json: str | None = None,
    ) -> Home | None:
        home = await self.get(home_id)
        if home is None:
            return None
        if name is not None:
            home.name = name
        if description is not None:
            home.description = description
        if status is not None:
            home.status = status
        if settings_json is not None:
            home.settings_json = settings_json
        return home

    async def delete(self, home_id: str) -> bool:
        home = await self.get(home_id)
        if home is None:
            return False
        await self._s.delete(home)
        return True

    async def search(self, query: str, *, limit: int = 10) -> list[Home]:
        pattern = f"%{query.lower()}%"
        stmt = (
            select(Home)
            .where(
                or_(func.lower(Home.name).like(pattern), func.lower(Home.description).like(pattern))
            )
            .order_by(Home.updated_at.desc())
            .limit(limit)
        )
        return list((await self._s.execute(stmt)).scalars().all())

    async def counts(self, home_id: str) -> tuple[int, int, int, int, int]:
        """``(room_count, zone_count, device_count, paired_count,
        offline_count)`` -- backs ``HomeMetadata``. ``unreachable`` is
        counted separately by the caller from the same device list
        rather than a sixth aggregate query; see
        ``SmartHomeService.metadata``."""
        rooms = await self._s.scalar(
            select(func.count()).select_from(Room).where(Room.home_id == home_id)
        )
        zones = await self._s.scalar(
            select(func.count()).select_from(Zone).where(Zone.home_id == home_id)
        )
        devices = await self._s.scalar(
            select(func.count()).select_from(Device).where(Device.home_id == home_id)
        )
        paired = await self._s.scalar(
            select(func.count())
            .select_from(Device)
            .where(Device.home_id == home_id, Device.status == "paired")
        )
        offline = await self._s.scalar(
            select(func.count())
            .select_from(Device)
            .where(Device.home_id == home_id, Device.status == "offline")
        )
        return (
            int(rooms or 0),
            int(zones or 0),
            int(devices or 0),
            int(paired or 0),
            int(offline or 0),
        )

    async def unreachable_count(self, home_id: str) -> int:
        value = await self._s.scalar(
            select(func.count())
            .select_from(Device)
            .where(Device.home_id == home_id, Device.status == "unreachable")
        )
        return int(value or 0)


class ZoneRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, home_id: str, name: str, *, description: str = "") -> Zone:
        zone = Zone(home_id=home_id, name=name, description=description)
        self._s.add(zone)
        await self._s.flush()
        return zone

    async def get(self, zone_id: str) -> Zone | None:
        return await self._s.get(Zone, zone_id)

    async def list_zones(
        self, *, home_id: str | None = None, limit: int = 200, offset: int = 0
    ) -> list[Zone]:
        stmt = select(Zone).order_by(Zone.created_at.desc()).limit(limit).offset(offset)
        if home_id is not None:
            stmt = stmt.where(Zone.home_id == home_id)
        return list((await self._s.execute(stmt)).scalars().all())

    async def update(
        self, zone_id: str, *, name: str | None = None, description: str | None = None
    ) -> Zone | None:
        zone = await self.get(zone_id)
        if zone is None:
            return None
        if name is not None:
            zone.name = name
        if description is not None:
            zone.description = description
        return zone

    async def delete(self, zone_id: str) -> bool:
        zone = await self.get(zone_id)
        if zone is None:
            return False
        await self._s.delete(zone)
        return True

    async def clear_rooms(self, zone_id: str) -> int:
        """Sets ``zone_id`` to ``None`` on every room in this zone,
        returning how many moved. Called before deleting a zone so its
        rooms fall back to "no zone" instead of the ORM's default
        cascade removing rooms that are physical spaces, not zone
        members -- the same "reassign, don't cascade" choice
        ``ProjectRepository.detach_notes`` makes for notes."""
        rooms = list(
            (await self._s.execute(select(Room).where(Room.zone_id == zone_id))).scalars().all()
        )
        for room in rooms:
            room.zone_id = None
        return len(rooms)


class RoomRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(
        self,
        home_id: str,
        name: str,
        *,
        description: str = "",
        zone_id: str | None = None,
    ) -> Room:
        room = Room(home_id=home_id, zone_id=zone_id, name=name, description=description)
        self._s.add(room)
        await self._s.flush()
        return room

    async def get(self, room_id: str) -> Room | None:
        return await self._s.get(Room, room_id)

    async def list_rooms(
        self,
        *,
        home_id: str | None = None,
        zone_id: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[Room]:
        stmt = select(Room).order_by(Room.created_at.desc()).limit(limit).offset(offset)
        if home_id is not None:
            stmt = stmt.where(Room.home_id == home_id)
        if zone_id is not None:
            stmt = stmt.where(Room.zone_id == zone_id)
        return list((await self._s.execute(stmt)).scalars().all())

    async def update(
        self,
        room_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        zone_id: str | None = None,
        clear_zone: bool = False,
    ) -> Room | None:
        room = await self.get(room_id)
        if room is None:
            return None
        if name is not None:
            room.name = name
        if description is not None:
            room.description = description
        if clear_zone:
            room.zone_id = None
        elif zone_id is not None:
            room.zone_id = zone_id
        return room

    async def delete(self, room_id: str) -> bool:
        room = await self.get(room_id)
        if room is None:
            return False
        await self._s.delete(room)
        return True

    async def detach_devices(self, room_id: str) -> int:
        """Clears ``room_id`` on this room's devices, returning how many
        moved -- called before deleting a room so its devices are not
        cascaded away, the same reasoning as ``ZoneRepository
        .clear_rooms``."""
        devices = list(
            (await self._s.execute(select(Device).where(Device.room_id == room_id))).scalars().all()
        )
        for device in devices:
            device.room_id = None
        return len(devices)


class DeviceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(
        self,
        home_id: str,
        name: str,
        *,
        device_type: str = "other",
        status: str = "discovered",
        room_id: str | None = None,
        manufacturer: str = "",
        model: str = "",
        external_id: str | None = None,
        metadata_json: str = "{}",
    ) -> Device:
        device = Device(
            home_id=home_id,
            room_id=room_id,
            name=name,
            device_type=device_type,
            status=status,
            manufacturer=manufacturer,
            model=model,
            external_id=external_id,
            metadata_json=metadata_json,
        )
        self._s.add(device)
        await self._s.flush()
        return device

    async def get(self, device_id: str) -> Device | None:
        return await self._s.get(Device, device_id)

    async def get_by_external_id(self, home_id: str, external_id: str) -> Device | None:
        """Scoped to *home_id* as well as *external_id* -- two
        different homes' connectors could, in principle, both discover
        a device that happens to report the same external id (e.g. two
        independent Home Assistant instances), and a lookup that
        ignored the home would silently merge them. Milestone 12 Task
        Group B's own discovery-idempotency check."""
        stmt = select(Device).where(Device.home_id == home_id, Device.external_id == external_id)
        return (await self._s.execute(stmt)).scalars().first()

    async def list_devices(
        self,
        *,
        home_id: str | None = None,
        room_id: str | None = None,
        device_type: str | None = None,
        status: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[Device]:
        stmt = select(Device).order_by(Device.created_at.desc()).limit(limit).offset(offset)
        if home_id is not None:
            stmt = stmt.where(Device.home_id == home_id)
        if room_id is not None:
            stmt = stmt.where(Device.room_id == room_id)
        if device_type is not None:
            stmt = stmt.where(Device.device_type == device_type)
        if status is not None:
            stmt = stmt.where(Device.status == status)
        return list((await self._s.execute(stmt)).scalars().all())

    async def update(
        self,
        device_id: str,
        *,
        name: str | None = None,
        device_type: str | None = None,
        status: str | None = None,
        room_id: str | None = None,
        clear_room: bool = False,
        manufacturer: str | None = None,
        model: str | None = None,
        external_id: str | None = None,
        metadata_json: str | None = None,
        touch_last_seen: bool = False,
    ) -> Device | None:
        device = await self.get(device_id)
        if device is None:
            return None
        if name is not None:
            device.name = name
        if device_type is not None:
            device.device_type = device_type
        if status is not None:
            device.status = status
        if clear_room:
            device.room_id = None
        elif room_id is not None:
            device.room_id = room_id
        if manufacturer is not None:
            device.manufacturer = manufacturer
        if model is not None:
            device.model = model
        if external_id is not None:
            device.external_id = external_id
        if metadata_json is not None:
            device.metadata_json = metadata_json
        if touch_last_seen:
            device.last_seen_at = _utcnow()
        return device

    async def delete(self, device_id: str) -> bool:
        device = await self.get(device_id)
        if device is None:
            return False
        await self._s.delete(device)
        return True

    async def search(self, query: str, *, limit: int = 10) -> list[Device]:
        pattern = f"%{query.lower()}%"
        stmt = (
            select(Device)
            .where(
                or_(
                    func.lower(Device.name).like(pattern),
                    func.lower(Device.manufacturer).like(pattern),
                    func.lower(Device.model).like(pattern),
                )
            )
            .order_by(Device.updated_at.desc())
            .limit(limit)
        )
        return list((await self._s.execute(stmt)).scalars().all())


class DeviceGroupRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, home_id: str, name: str, *, description: str = "") -> DeviceGroup:
        group = DeviceGroup(home_id=home_id, name=name, description=description)
        self._s.add(group)
        await self._s.flush()
        return group

    async def get(self, group_id: str) -> DeviceGroup | None:
        return await self._s.get(DeviceGroup, group_id)

    async def list_groups(
        self, *, home_id: str | None = None, limit: int = 200, offset: int = 0
    ) -> list[DeviceGroup]:
        stmt = (
            select(DeviceGroup).order_by(DeviceGroup.created_at.desc()).limit(limit).offset(offset)
        )
        if home_id is not None:
            stmt = stmt.where(DeviceGroup.home_id == home_id)
        return list((await self._s.execute(stmt)).scalars().all())

    async def update(
        self, group_id: str, *, name: str | None = None, description: str | None = None
    ) -> DeviceGroup | None:
        group = await self.get(group_id)
        if group is None:
            return None
        if name is not None:
            group.name = name
        if description is not None:
            group.description = description
        return group

    async def delete(self, group_id: str) -> bool:
        group = await self.get(group_id)
        if group is None:
            return False
        await self._s.delete(group)
        return True

    async def add_member(self, group_id: str, device_id: str) -> bool:
        """Idempotent: adding an already-present device is a no-op
        rather than a duplicate-key error, matching
        ``ProvisioningJournal.complete``'s own "re-completing is a
        no-op" reasoning applied to a join row instead of a journal
        entry."""
        existing = await self._s.get(DeviceGroupMember, (group_id, device_id))
        if existing is not None:
            return False
        self._s.add(DeviceGroupMember(device_group_id=group_id, device_id=device_id))
        await self._s.flush()
        return True

    async def remove_member(self, group_id: str, device_id: str) -> bool:
        existing = await self._s.get(DeviceGroupMember, (group_id, device_id))
        if existing is None:
            return False
        await self._s.delete(existing)
        return True

    async def list_members(self, group_id: str) -> list[Device]:
        stmt = (
            select(Device)
            .join(DeviceGroupMember, DeviceGroupMember.device_id == Device.id)
            .where(DeviceGroupMember.device_group_id == group_id)
            .order_by(DeviceGroupMember.added_at.asc())
        )
        return list((await self._s.execute(stmt)).scalars().all())

    async def member_count(self, group_id: str) -> int:
        value = await self._s.scalar(
            select(func.count())
            .select_from(DeviceGroupMember)
            .where(DeviceGroupMember.device_group_id == group_id)
        )
        return int(value or 0)
