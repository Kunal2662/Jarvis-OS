"""Agent tools wrapping
:class:`~jarvis.services.water_heater_service.WaterHeaterService`
(Milestone 12 Appliance Control -- Water Heater Core Slice).

**Three tools, mirroring ``thermostat_tools.py``'s shape, not Media
Player's eight.** Water heater control has no independent zero-payload
transport verb -- every command is an attribute mutation, so one
merged ``set_water_heater_state`` tool covers temperature/operation
mode/on-off together rather than splitting into per-attribute tools,
the identical reasoning ``thermostat_tools.py``'s own module docstring
already states.

**Every tool calls the same ``WaterHeaterService`` the REST route
does**, so both trip the same permission check: reads are ungated, and
the mutation requires the ``smart_home`` grant for
``core:water_heaters``. No tool reaches ``ConnectivityService`` or a
connector directly. **No confirmation requirement** -- Logic Contract
§11 evaluated and rejected gating this behind
``confirm_required_tools``.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool, tool

from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.services.water_heater_service import WaterHeaterService

_logger = get_logger("jarvis.agents.tools.water_heater")

_MAX_RESULT_CHARS = 4_000


def build_water_heater_tools(service: WaterHeaterService) -> list[BaseTool]:
    @tool
    async def list_water_heaters(home_id: str = "", room_id: str = "") -> str:
        """List known water heaters, optionally filtered by home_id or
        room_id. Entries show last-known DB fields only; call
        get_water_heater_state for one device's live state."""
        try:
            rows = await service.list_water_heaters(
                home_id=home_id or None, room_id=room_id or None
            )
        except Exception as err:
            _logger.warning("list_water_heaters tool failed: {}", err)
            return f"Couldn't list water heaters: {err}"
        if not rows:
            return "No water heaters match that filter."
        return _clip(json.dumps(rows, indent=2, default=str))

    @tool
    async def get_water_heater_state(device_id: str) -> str:
        """Get one water heater's live reading by device id: current
        and target temperature, operation mode (and the modes it
        supports), on/off, its reported min/max temperature, and
        availability. Use list_water_heaters first to find the device
        id."""
        try:
            state = await service.get_water_heater_state(device_id)
        except Exception as err:
            _logger.warning("get_water_heater_state tool failed: {}", err)
            return f"Couldn't read that water heater's state: {err}"
        return _clip(json.dumps(state, indent=2, default=str))

    @tool
    async def set_water_heater_state(
        device_id: str,
        temperature: float | None = None,
        operation_mode: str = "",
        on: bool | None = None,
    ) -> str:
        """Set a water heater's target temperature, operation mode,
        and/or on/off in one call. Supply at least one of them.
        Temperature is in the device's own unit -- no conversion is
        performed. operation_mode must be one the device reports as
        supported (see get_water_heater_state). Takes real effect on
        the device."""
        try:
            result = await service.set_water_heater_state(
                device_id,
                temperature=temperature,
                operation_mode=operation_mode or None,
                on=on,
            )
        except Exception as err:
            _logger.warning("set_water_heater_state tool failed: {}", err)
            return f"Couldn't change that water heater: {err}"
        return _clip(json.dumps(result, indent=2, default=str))

    return [list_water_heaters, get_water_heater_state, set_water_heater_state]


def _clip(text: str) -> str:
    if len(text) <= _MAX_RESULT_CHARS:
        return text
    return (
        text[:_MAX_RESULT_CHARS]
        + f"\n... (truncated at {_MAX_RESULT_CHARS} characters; narrow the query "
        "or ask for fewer results)"
    )
