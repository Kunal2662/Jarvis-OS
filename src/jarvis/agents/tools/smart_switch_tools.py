"""Agent tools wrapping
:class:`~jarvis.services.smart_switch_service.SmartSwitchService`
(Milestone 12 Energy Management -- Core Energy Slice).

Four tools, mirroring ``smart_lock_tools.py``'s structure. A fifth,
availability-only tool (mirroring Sensors' ``get_sensor_status``) was
evaluated and not added -- ``get_switch_state``'s payload is already
small, so a separate terse tool would be a near-duplicate rather than
a genuine simplification.

**No energy-reading tool exists here.** Power/energy readings are
already available through the existing ``list_sensors``/
``get_sensor_value`` tools (``agents/tools/sensor_tools.py``) -- see
``docs/M12_ENERGY_MANAGEMENT_LOGIC_CONTRACT.md`` §11.

**No tool authorizes anything, and no tool bypasses the permission
gate.** Every mutating tool below calls the same ``SmartSwitchService``
method the REST route does, so both trip the same ``smart_home``
``PermissionModel`` check. Unlike Smart Locks' ``unlock_device``, no
tool here is added to ``AgentSettings.confirm_required_tools`` -- a
switch is not physically safety-relevant.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool, tool

from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.services.smart_switch_service import SmartSwitchService

_logger = get_logger("jarvis.agents.tools.smart_switch")

_MAX_RESULT_CHARS = 4_000


def build_smart_switch_tools(switches: SmartSwitchService) -> list[BaseTool]:
    @tool
    async def list_switches(home_id: str = "", room_id: str = "") -> str:
        """List known switches/smart plugs, optionally filtered by
        home_id or room_id. Each entry's last-known on/off state may be
        stale; call get_switch_state for one switch's live reading."""
        try:
            rows = await switches.list_switches(home_id=home_id or None, room_id=room_id or None)
        except Exception as err:
            _logger.warning("list_switches tool failed: {}", err)
            return f"Couldn't list switches: {err}"
        if not rows:
            return "No switches match that filter."
        return _clip(json.dumps(rows, indent=2, default=str))

    @tool
    async def get_switch_state(device_id: str) -> str:
        """Get one switch's live state (on/off/unknown) and
        availability by device id. Use list_switches first to find the
        device id. For power/energy readings on the same physical
        plug, use get_sensor_value on its sibling sensor device
        instead -- this tool only reports on/off."""
        try:
            state = await switches.get_switch_state(device_id)
        except Exception as err:
            _logger.warning("get_switch_state tool failed: {}", err)
            return f"Couldn't read that switch's state: {err}"
        return _clip(json.dumps(state, indent=2, default=str))

    @tool
    async def switch_on(device_id: str) -> str:
        """Turn a switch/smart plug on by device id. Takes real effect
        on the device -- confirm with the user before calling it."""
        try:
            result = await switches.turn_on(device_id)
        except Exception as err:
            _logger.warning("switch_on tool failed: {}", err)
            return f"Couldn't turn that switch on: {err}"
        return _clip(json.dumps(result, indent=2, default=str))

    @tool
    async def switch_off(device_id: str) -> str:
        """Turn a switch/smart plug off by device id. Takes real effect
        on the device -- confirm with the user before calling it."""
        try:
            result = await switches.turn_off(device_id)
        except Exception as err:
            _logger.warning("switch_off tool failed: {}", err)
            return f"Couldn't turn that switch off: {err}"
        return _clip(json.dumps(result, indent=2, default=str))

    return [list_switches, get_switch_state, switch_on, switch_off]


def _clip(text: str) -> str:
    if len(text) <= _MAX_RESULT_CHARS:
        return text
    return (
        text[:_MAX_RESULT_CHARS]
        + f"\n... (truncated at {_MAX_RESULT_CHARS} characters; narrow the query "
        "or ask for fewer results)"
    )
