"""Agent tools wrapping
:class:`~jarvis.services.smart_home_memory_service.SmartHomeMemoryService`
(Milestone 12 Smart Home Memory -- Manual/On-Demand Device Snapshot
Slice + Device-Category Expansion Slice).

**Four tools, matching the four genuinely distinct capabilities the
service exposes** -- not built to mirror REST one-for-one beyond that.
No tool wrapping ``MemoryService.recall``/``search`` is added here:
those are already exposed generically by the existing
``recall_memory`` tool (``agents/tools/memory_tools.py``), and
duplicating them for snapshot content specifically would be redundant.

**Every tool calls the same ``SmartHomeMemoryService`` the REST route
does**, so all four trip the same permission check: every operation
requires the ``smart_home`` grant for ``core:smart_home_memory`` -- a
deliberate departure from most M12 appliance-category tools' "reads
ungated" precedent (Logic Contract §10). **No confirmation
requirement anywhere in this module** -- a single snapshot touches one
device and writes one memory row; a home-wide snapshot never sends a
device a command (read-only); a single-snapshot deletion is smaller in
consequence than any tool this codebase currently gates (Expansion
Logic Contract §15).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool, tool

from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.services.smart_home_memory_service import SmartHomeMemoryService

_logger = get_logger("jarvis.agents.tools.smart_home_memory")

_MAX_RESULT_CHARS = 4_000


def build_smart_home_memory_tools(service: SmartHomeMemoryService) -> list[BaseTool]:
    @tool
    async def snapshot_device_state(device_id: str) -> str:
        """Capture a device's current state into memory, right now,
        because this was asked for -- never automatically and never on
        a schedule. Light, switch, thermostat, fan, cover, vacuum,
        humidifier, media player, and water heater devices are
        supported; other categories are rejected. Returns the stored
        snapshot's memory id and capture time."""
        try:
            result = await service.snapshot_device(device_id)
        except Exception as err:
            _logger.warning("snapshot_device_state tool failed: {}", err)
            return f"Couldn't snapshot that device: {err}"
        return _clip(json.dumps(result, indent=2, default=str))

    @tool
    async def list_device_snapshots(device_id: str = "", limit: int = 20) -> str:
        """List previously-captured device snapshots, most recent
        first. Pass device_id to see only that device's snapshots, or
        leave it blank to see snapshots across every device."""
        try:
            rows = await service.list_snapshots(device_id=device_id or None, limit=limit)
        except Exception as err:
            _logger.warning("list_device_snapshots tool failed: {}", err)
            return f"Couldn't list device snapshots: {err}"
        if not rows:
            return "No device snapshots match that filter."
        return _clip(json.dumps(rows, indent=2, default=str))

    @tool
    async def delete_device_snapshot(memory_id: str) -> str:
        """Delete one previously-captured device snapshot by its
        memory id, found via list_device_snapshots. Only deletes
        device-snapshot memories -- never any other kind of memory."""
        try:
            result = await service.delete_snapshot(memory_id)
        except Exception as err:
            _logger.warning("delete_device_snapshot tool failed: {}", err)
            return f"Couldn't delete that snapshot: {err}"
        return _clip(json.dumps(result, indent=2, default=str))

    @tool
    async def snapshot_home(home_id: str) -> str:
        """Snapshot every supported device in one home in a single
        call. Devices in unsupported categories (e.g. sensors, locks)
        are skipped, not treated as failures; one device's failure
        never stops the rest. Returns per-device results and aggregate
        counts."""
        try:
            result = await service.snapshot_home(home_id)
        except Exception as err:
            _logger.warning("snapshot_home tool failed: {}", err)
            return f"Couldn't snapshot that home: {err}"
        return _clip(json.dumps(result, indent=2, default=str))

    return [snapshot_device_state, list_device_snapshots, delete_device_snapshot, snapshot_home]


def _clip(text: str) -> str:
    if len(text) <= _MAX_RESULT_CHARS:
        return text
    return (
        text[:_MAX_RESULT_CHARS]
        + f"\n... (truncated at {_MAX_RESULT_CHARS} characters; narrow the query "
        "or ask for fewer results)"
    )
