"""Agent tools wrapping
:class:`~jarvis.services.smart_home_memory_service.SmartHomeMemoryService`
(Milestone 12 Smart Home Memory -- Manual/On-Demand Device Snapshot
Slice).

**Two tools, matching the two genuinely distinct capabilities the
service exposes** -- not built to mirror REST one-for-one beyond that.
No third tool wrapping ``MemoryService.recall``/``search`` is added
here: those are already exposed generically by the existing
``recall_memory`` tool (``agents/tools/memory_tools.py``), and
duplicating them for snapshot content specifically would be redundant.

**Every tool calls the same ``SmartHomeMemoryService`` the REST route
does**, so both trip the same permission check: creating *and*
retrieving snapshots require the ``smart_home`` grant for
``core:smart_home_memory`` -- a deliberate departure from most M12
appliance-category tools' "reads ungated" precedent (Logic Contract
§10). **No confirmation requirement** -- a snapshot touches one device
and writes one memory row, never a physical device.
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
        a schedule. Only light, switch, and thermostat devices are
        supported in this release; other categories are rejected.
        Returns the stored snapshot's memory id and capture time."""
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

    return [snapshot_device_state, list_device_snapshots]


def _clip(text: str) -> str:
    if len(text) <= _MAX_RESULT_CHARS:
        return text
    return (
        text[:_MAX_RESULT_CHARS]
        + f"\n... (truncated at {_MAX_RESULT_CHARS} characters; narrow the query "
        "or ask for fewer results)"
    )
