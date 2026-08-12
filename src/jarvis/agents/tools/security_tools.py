"""Agent tools wrapping
:class:`~jarvis.services.security_service.SecurityService` (Milestone
12 Security & Safety -- Read-Only Alert/Status Slice).

Two read-only tools, mirroring ``sensor_tools.py``'s "terse re-shaping
of one underlying call" structure (``docs/
M12_SECURITY_SAFETY_LOGIC_CONTRACT.md`` §11).
``list_active_security_alerts`` is a thin projection of the same
``get_security_status`` call, justified by the identical precedent
``get_sensor_value``/``get_sensor_status`` already established -- not a
second aggregation path.

**No mutation tool exists.** This module is informational only -- see
the Logic Contract §17. There is nothing to gate behind a confirmation
requirement.

**Every tool calls the same ``SecurityService`` the REST route does**,
so both trip the same ``core:security`` permission check -- and,
through it, ``SensorService``'s own independent ``core:sensors`` check
(Logic Contract §3). Neither tool bypasses ``SecurityService`` to call
``SensorService``/``SmartLockService`` directly.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool, tool

from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.services.security_service import SecurityService

_logger = get_logger("jarvis.agents.tools.security")

_MAX_RESULT_CHARS = 4_000


def build_security_tools(security: SecurityService) -> list[BaseTool]:
    @tool
    async def get_security_status(home_id: str = "", room_id: str = "") -> str:
        """Get the full home security status: overall status
        (CRITICAL/WARNING/UNKNOWN/NORMAL), active hazard alerts
        (smoke/gas/water-leak only), sensor status (door/window/
        motion/presence/occupancy), and lock state. Optionally filter
        by home_id or room_id. This is informational only -- it does
        not take any action."""
        try:
            status = await security.get_security_status(
                home_id=home_id or None, room_id=room_id or None
            )
        except Exception as err:
            _logger.warning("get_security_status tool failed: {}", err)
            return f"Couldn't get security status: {err}"
        return _clip(json.dumps(status, indent=2, default=str))

    @tool
    async def list_active_security_alerts(home_id: str = "", room_id: str = "") -> str:
        """List only the currently active hazard alerts (smoke, gas,
        or water leak detected) -- a terser answer than
        get_security_status for "is anything wrong at home". Does not
        include door/window/motion/presence status, which are never
        classified as alerts."""
        try:
            alerts = await security.list_active_alerts(
                home_id=home_id or None, room_id=room_id or None
            )
        except Exception as err:
            _logger.warning("list_active_security_alerts tool failed: {}", err)
            return f"Couldn't list active security alerts: {err}"
        if not alerts:
            return "No active alerts."
        return _clip(json.dumps(alerts, indent=2, default=str))

    return [get_security_status, list_active_security_alerts]


def _clip(text: str) -> str:
    if len(text) <= _MAX_RESULT_CHARS:
        return text
    return (
        text[:_MAX_RESULT_CHARS]
        + f"\n... (truncated at {_MAX_RESULT_CHARS} characters; narrow the query "
        "or ask for fewer results)"
    )
