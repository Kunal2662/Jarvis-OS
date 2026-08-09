"""Agent tools wrapping
:class:`~jarvis.services.sensor_service.SensorService` (Milestone 12
Sensors).

Four read-only tools, mirroring ``smart_lock_tools.py``'s structure.
``get_sensor_value``/``get_sensor_status`` are thin re-shapings of the
same ``get_sensor_state()`` call, not separate service methods --
added because a conversational agent asking "what's the temperature"
benefits from a terse answer more than the full JSON blob
``get_sensor_state`` returns, and this is the first read-heavy,
data-query-shaped M12 module where that distinction earns its keep.

**No mutation tool exists.** Sensors are read-only -- there is nothing
to gate behind a confirmation requirement the way Smart Locks'
``unlock_device`` is.

**Every tool calls the same ``SensorService`` the REST route does**, so
both trip the same permission check -- see ``services/sensor_service.
py``'s own module docstring for why Sensors' reads (unlike Lighting/
Locks) require the ``smart_home`` grant too.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool, tool

from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.services.sensor_service import SensorService

_logger = get_logger("jarvis.agents.tools.sensor")

_MAX_RESULT_CHARS = 4_000


def build_sensor_tools(sensors: SensorService) -> list[BaseTool]:
    @tool
    async def list_sensors(home_id: str = "", room_id: str = "") -> str:
        """List known sensors, optionally filtered by home_id or
        room_id. Each entry shows device_class and kind (binary/
        numeric) but not the live reading; call get_sensor_state for
        one sensor's current value."""
        try:
            rows = await sensors.list_sensors(home_id=home_id or None, room_id=room_id or None)
        except Exception as err:
            _logger.warning("list_sensors tool failed: {}", err)
            return f"Couldn't list sensors: {err}"
        if not rows:
            return "No sensors match that filter."
        return _clip(json.dumps(rows, indent=2, default=str))

    @tool
    async def get_sensor_state(device_id: str) -> str:
        """Get one sensor's full live reading (state, value, unit,
        availability, timestamp) by device id. Use list_sensors first
        to find the device id."""
        try:
            state = await sensors.get_sensor_state(device_id)
        except Exception as err:
            _logger.warning("get_sensor_state tool failed: {}", err)
            return f"Couldn't read that sensor's state: {err}"
        return _clip(json.dumps(state, indent=2, default=str))

    @tool
    async def get_sensor_value(device_id: str) -> str:
        """Get just a sensor's current value and unit (e.g. "21.5 °C")
        by device id -- a terser answer than get_sensor_state for a
        direct "what's the temperature/humidity/..." question."""
        try:
            state = await sensors.get_sensor_state(device_id)
        except Exception as err:
            _logger.warning("get_sensor_value tool failed: {}", err)
            return f"Couldn't read that sensor's value: {err}"
        return _clip(
            json.dumps(
                {"value": state["value"], "unit": state["unit"], "state": state["state"]},
                default=str,
            )
        )

    @tool
    async def get_sensor_status(device_id: str) -> str:
        """Get just a sensor's availability by device id -- "is this
        sensor online/reachable", not its reading."""
        try:
            state = await sensors.get_sensor_state(device_id)
        except Exception as err:
            _logger.warning("get_sensor_status tool failed: {}", err)
            return f"Couldn't read that sensor's status: {err}"
        return _clip(
            json.dumps({"status": state["status"], "available": state["available"]}, default=str)
        )

    return [list_sensors, get_sensor_state, get_sensor_value, get_sensor_status]


def _clip(text: str) -> str:
    if len(text) <= _MAX_RESULT_CHARS:
        return text
    return (
        text[:_MAX_RESULT_CHARS]
        + f"\n... (truncated at {_MAX_RESULT_CHARS} characters; narrow the query "
        "or ask for fewer results)"
    )
