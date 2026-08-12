"""Smart Home domain models -- Milestone 12 Task Group A (Smart Home Core).

The closed vocabularies this task group's service layer validates
against, plus one derived value object. No ORM here, matching
``domain/workspace/models.py``'s own split: persisted rows live in
``infrastructure/database/models.py``, this module only owns pure data
and the rules a service checks before writing one.

**Why device discovery and pairing are domain *states*, not live
actions, in this task group.** No protocol adapter exists yet --
ESP32/MQTT/Zigbee/Z-Wave/Matter/Thread/Home Assistant are M12's own
Connectivity Layer, a later task group. ``DEVICE_STATUSES`` models the
lifecycle a real scan will eventually drive
(``discovered`` -> ``pairing`` -> ``paired``, with ``offline`` /
``unreachable`` for a paired device a later health check finds gone,
and ``removed`` for a device taken out of service without deleting its
history). ``SmartHomeService.register_discovered_device`` records a
discovery result; nothing in this task group produces one by talking to
real hardware -- the same boundary M11 Task Group B drew around
``Reminder`` ("scheduling metadata and status transitions... **No
execution**").
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

#: A home is either in use or put away -- mirrors ``WORKSPACE_STATUSES``
#: exactly (``domain/workspace/models.py``), including the reasoning: a
#: closed set so a filter never silently returns nothing on a typo.
HOME_STATUSES: frozenset[str] = frozenset({"active", "archived"})

#: The device lifecycle this task group's domain models but does not
#: drive -- see this module's own docstring. ``removed`` is distinct
#: from deleting the row: a device taken out of service keeps its
#: history (pairing date, past readings a later module adds) rather
#: than losing it to a hard delete.
DEVICE_STATUSES: frozenset[str] = frozenset(
    {"discovered", "pairing", "paired", "offline", "unreachable", "removed"}
)

#: One category per device-focused module in M12's own 15-module list
#: (Smart Lighting -> light, Smart Locks -> lock, Sensors -> sensor,
#: Smart Cameras -> camera, Energy Management -> switch, Appliance
#: Control -> appliance) plus ``thermostat`` (named explicitly in
#: Appliance Control's own feature list) and ``other`` for anything a
#: later Connectivity Layer adapter reports that does not fit yet --
#: an unknown type should be accepted and shown as "other", not
#: rejected, since refusing to register a real device over a
#: vocabulary gap is a worse failure than an imprecise category.
DEVICE_TYPES: frozenset[str] = frozenset(
    {"light", "lock", "sensor", "camera", "switch", "thermostat", "appliance", "other"}
)


@dataclass(frozen=True, slots=True)
class HomeMetadata:
    """Derived counts for one home -- the data **Device Health
    Monitoring** and **Device Status Dashboard** (Smart Home Core's own
    last two listed items) read. Computed on read, never persisted --
    same reasoning as ``WorkspaceMetadata``: a stored count drifts the
    first time a device is deleted through a path that forgot to
    decrement it.
    """

    home_id: str
    room_count: int = 0
    zone_count: int = 0
    device_count: int = 0
    paired_device_count: int = 0
    offline_device_count: int = 0
    unreachable_device_count: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "home_id": self.home_id,
            "room_count": self.room_count,
            "zone_count": self.zone_count,
            "device_count": self.device_count,
            "paired_device_count": self.paired_device_count,
            "offline_device_count": self.offline_device_count,
            "unreachable_device_count": self.unreachable_device_count,
        }


def utcnow_iso(value: datetime | None) -> str | None:
    """Shared by every REST payload builder in this task group so a
    ``None`` timestamp serializes the same way everywhere."""
    return value.isoformat() if value else None
