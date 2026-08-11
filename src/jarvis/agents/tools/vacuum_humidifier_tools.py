"""Agent tools wrapping
:class:`~jarvis.services.vacuum_humidifier_service.VacuumHumidifierService`
(Milestone 12 Appliance Control -- Vacuum + Humidifier Core Slice).

**Vacuum -- six tools, one per verb**, mirroring ``appliance_tools.py``'s
own one-tool-per-command shape: four independent commands, not
attributes that combine, so no merged mutation tool exists for them.

**Humidifier -- three tools, merged mutation**, mirroring
``thermostat_tools.py``'s shape: on/off and target humidity combine
into one user intent.

**Every tool calls the same ``VacuumHumidifierService`` the REST route
does**, so both trip the same permission check: reads are ungated, and
mutations require the ``smart_home`` grant for ``core:vacuum_humidifier``.
No tool reaches ``ConnectivityService`` or a connector directly. No
mutation tool requires confirmation -- neither vacuum movement nor
humidifier on/off/humidity rises to ``unlock_device``'s tier (Logic
Contract §13).
"""

from __future__ import annotations

import json
from collections.abc import Awaitable
from typing import TYPE_CHECKING, Any

from langchain_core.tools import BaseTool, tool

from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.services.vacuum_humidifier_service import VacuumHumidifierService

_logger = get_logger("jarvis.agents.tools.vacuum_humidifier")

_MAX_RESULT_CHARS = 4_000


async def _run_vacuum_command(tool_name: str, verb: str, call: Awaitable[dict[str, Any]]) -> str:
    """Shared by the four vacuum command tools -- they are structurally
    identical (call one `VacuumHumidifierService` method, catch,
    format), so factoring this out keeps `build_vacuum_humidifier_tools`
    itself short rather than repeating the same try/except four times."""
    try:
        result = await call
    except Exception as err:
        _logger.warning("{} tool failed: {}", tool_name, err)
        return f"Couldn't {verb} that vacuum: {err}"
    return _clip(json.dumps(result, indent=2, default=str))


def build_vacuum_humidifier_tools(service: VacuumHumidifierService) -> list[BaseTool]:
    @tool
    async def list_vacuums(home_id: str = "", room_id: str = "") -> str:
        """List known robot vacuums, optionally filtered by home_id or
        room_id. Entries show last-known DB fields only; call
        get_vacuum_state for one vacuum's live state and battery
        level."""
        try:
            rows = await service.list_vacuums(home_id=home_id or None, room_id=room_id or None)
        except Exception as err:
            _logger.warning("list_vacuums tool failed: {}", err)
            return f"Couldn't list vacuums: {err}"
        if not rows:
            return "No vacuums match that filter."
        return _clip(json.dumps(rows, indent=2, default=str))

    @tool
    async def get_vacuum_state(device_id: str) -> str:
        """Get one vacuum's live state (e.g. docked/cleaning/paused),
        battery level if reported, and availability by device id. Use
        list_vacuums first to find the device id."""
        try:
            state = await service.get_vacuum_state(device_id)
        except Exception as err:
            _logger.warning("get_vacuum_state tool failed: {}", err)
            return f"Couldn't read that vacuum's state: {err}"
        return _clip(json.dumps(state, indent=2, default=str))

    @tool
    async def vacuum_start(device_id: str) -> str:
        """Start or resume cleaning for a robot vacuum by device id.
        Takes real effect on the device."""
        return await _run_vacuum_command("vacuum_start", "start", service.start(device_id))

    @tool
    async def vacuum_stop(device_id: str) -> str:
        """Stop a robot vacuum without returning it to its dock, by
        device id. Takes real effect on the device."""
        return await _run_vacuum_command("vacuum_stop", "stop", service.stop(device_id))

    @tool
    async def vacuum_pause(device_id: str) -> str:
        """Pause a robot vacuum's current cleaning task by device id.
        Takes real effect on the device."""
        return await _run_vacuum_command("vacuum_pause", "pause", service.pause(device_id))

    @tool
    async def vacuum_dock(device_id: str) -> str:
        """Send a robot vacuum back to its charging dock by device id.
        Takes real effect on the device."""
        return await _run_vacuum_command("vacuum_dock", "dock", service.return_to_base(device_id))

    @tool
    async def list_humidifiers(home_id: str = "", room_id: str = "") -> str:
        """List known humidifiers, optionally filtered by home_id or
        room_id. Entries show last-known DB fields only; call
        get_humidifier_state for one humidifier's live reading."""
        try:
            rows = await service.list_humidifiers(home_id=home_id or None, room_id=room_id or None)
        except Exception as err:
            _logger.warning("list_humidifiers tool failed: {}", err)
            return f"Couldn't list humidifiers: {err}"
        if not rows:
            return "No humidifiers match that filter."
        return _clip(json.dumps(rows, indent=2, default=str))

    @tool
    async def get_humidifier_state(device_id: str) -> str:
        """Get one humidifier's live reading by device id: on/off,
        current humidity, target humidity, mode (read-only), reported
        min/max humidity, and availability. Use list_humidifiers first
        to find the device id."""
        try:
            state = await service.get_humidifier_state(device_id)
        except Exception as err:
            _logger.warning("get_humidifier_state tool failed: {}", err)
            return f"Couldn't read that humidifier's state: {err}"
        return _clip(json.dumps(state, indent=2, default=str))

    @tool
    async def set_humidifier_state(
        device_id: str, on: bool | None = None, target_humidity: float | None = None
    ) -> str:
        """Turn a humidifier on/off, set its target humidity, or both
        in one call. Supply at least one of them. Mode cannot be
        changed through this tool -- it is read-only. Takes real effect
        on the device."""
        try:
            result = await service.set_humidifier_state(
                device_id, on=on, target_humidity=target_humidity
            )
        except Exception as err:
            _logger.warning("set_humidifier_state tool failed: {}", err)
            return f"Couldn't change that humidifier: {err}"
        return _clip(json.dumps(result, indent=2, default=str))

    return [
        list_vacuums,
        get_vacuum_state,
        vacuum_start,
        vacuum_stop,
        vacuum_pause,
        vacuum_dock,
        list_humidifiers,
        get_humidifier_state,
        set_humidifier_state,
    ]


def _clip(text: str) -> str:
    if len(text) <= _MAX_RESULT_CHARS:
        return text
    return (
        text[:_MAX_RESULT_CHARS]
        + f"\n... (truncated at {_MAX_RESULT_CHARS} characters; narrow the query "
        "or ask for fewer results)"
    )
