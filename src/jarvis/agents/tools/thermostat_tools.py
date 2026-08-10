"""Agent tools wrapping
:class:`~jarvis.services.thermostat_service.ThermostatService`
(Milestone 12 Appliance Control -- Climate / Thermostat Slice).

**Three tools, not four.** Mutation is one merged
``set_thermostat_state`` rather than separate
``set_thermostat_temperature``/``set_thermostat_mode`` tools: splitting
it would make the common "set it to 22 and switch to cool" request cost
two tool calls and two wire round-trips, and it would diverge from
``smart_lighting_tools.py``, which exposes one ``set_light_state``
taking every optional attribute rather than one tool per attribute.

``hvac_mode`` uses ``""``-as-unset rather than ``None`` for LangChain
schema friendliness -- matching ``list_lights(home_id: str = "")``'s
existing convention -- and is converted to ``None`` at the service
boundary.

**Every tool calls the same ``ThermostatService`` the REST route does**,
so both trip the same permission check: reads are ungated, and the
mutation requires the ``smart_home`` grant for ``core:thermostats``.
No tool reaches ``ConnectivityService`` or a connector directly.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool, tool

from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.services.thermostat_service import ThermostatService

_logger = get_logger("jarvis.agents.tools.thermostat")

_MAX_RESULT_CHARS = 4_000


def build_thermostat_tools(thermostats: ThermostatService) -> list[BaseTool]:
    @tool
    async def list_thermostats(home_id: str = "", room_id: str = "") -> str:
        """List known thermostats, optionally filtered by home_id or
        room_id. Entries show last-known DB fields only; call
        get_thermostat_state for one thermostat's live temperature and
        mode."""
        try:
            rows = await thermostats.list_thermostats(
                home_id=home_id or None, room_id=room_id or None
            )
        except Exception as err:
            _logger.warning("list_thermostats tool failed: {}", err)
            return f"Couldn't list thermostats: {err}"
        if not rows:
            return "No thermostats match that filter."
        return _clip(json.dumps(rows, indent=2, default=str))

    @tool
    async def get_thermostat_state(device_id: str) -> str:
        """Get one thermostat's live reading by device id: current
        temperature, target temperature, HVAC mode, the modes the device
        supports, its reported min/max temperature, and availability.
        Use list_thermostats first to find the device id."""
        try:
            state = await thermostats.get_thermostat_state(device_id)
        except Exception as err:
            _logger.warning("get_thermostat_state tool failed: {}", err)
            return f"Couldn't read that thermostat's state: {err}"
        return _clip(json.dumps(state, indent=2, default=str))

    @tool
    async def set_thermostat_state(
        device_id: str, temperature: float | None = None, hvac_mode: str = ""
    ) -> str:
        """Set a thermostat's target temperature, its HVAC mode, or both
        in one call. Supply at least one of them. Temperature is in the
        device's own unit -- no conversion is performed. hvac_mode must
        be one the device reports as supported (see
        get_thermostat_state). Takes real effect on the device."""
        try:
            result = await thermostats.set_thermostat_state(
                device_id, temperature=temperature, hvac_mode=hvac_mode or None
            )
        except Exception as err:
            _logger.warning("set_thermostat_state tool failed: {}", err)
            return f"Couldn't change that thermostat: {err}"
        return _clip(json.dumps(result, indent=2, default=str))

    return [list_thermostats, get_thermostat_state, set_thermostat_state]


def _clip(text: str) -> str:
    if len(text) <= _MAX_RESULT_CHARS:
        return text
    return (
        text[:_MAX_RESULT_CHARS]
        + f"\n... (truncated at {_MAX_RESULT_CHARS} characters; narrow the query "
        "or ask for fewer results)"
    )
