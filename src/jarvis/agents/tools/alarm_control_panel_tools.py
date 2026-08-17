"""Agent tools wrapping
:class:`~jarvis.services.alarm_control_panel_service.AlarmControlPanelService`
(Milestone 12 Security & Safety -- alarm_control_panel Integration
Slice).

**Five tools, mirroring ``siren_tools.py``'s structure.** Every tool
calls the same ``AlarmControlPanelService`` method the REST route
does, so both trip the same ``smart_home`` ``PermissionModel`` check
for ``core:alarm_control_panels``.

**No tool accepts a ``code``/``pin`` argument, anywhere.** Each tool's
own generated argument schema has no such field to fill -- the
absence is structural (Logic Contract §8/§11), not a validation rule
an agent or user could talk its way around.

**``disarm`` requires interactive confirmation -- ``arm_home``/
``arm_away`` do not.** The same directional-risk asymmetry
``smart_lock_tools.py``'s own ``unlock_device``/``siren_tools.py``'s
own ``turn_siren_on`` already established: arming adds protection and
is always the safe direction; disarming removes it. ``disarm`` is
added to ``AgentSettings.confirm_required_tools`` -- the existing
``AgentPermissionGate`` mechanism, not a new one (Logic Contract §12).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool, tool

from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.services.alarm_control_panel_service import AlarmControlPanelService

_logger = get_logger("jarvis.agents.tools.alarm_control_panel")

_MAX_RESULT_CHARS = 4_000


def build_alarm_control_panel_tools(
    alarm_control_panels: AlarmControlPanelService,
) -> list[BaseTool]:
    @tool
    async def list_alarm_control_panels(home_id: str = "", room_id: str = "") -> str:
        """List known alarm control panels, optionally filtered by
        home_id or room_id. Entries show last-known DB fields only;
        call get_alarm_control_panel_state for one panel's live
        state."""
        try:
            rows = await alarm_control_panels.list_alarm_control_panels(
                home_id=home_id or None, room_id=room_id or None
            )
        except Exception as err:
            _logger.warning("list_alarm_control_panels tool failed: {}", err)
            return f"Couldn't list alarm control panels: {err}"
        if not rows:
            return "No alarm control panels match that filter."
        return _clip(json.dumps(rows, indent=2, default=str))

    @tool
    async def get_alarm_control_panel_state(device_id: str) -> str:
        """Get one alarm control panel's live state and availability
        by device id. Use list_alarm_control_panels first to find the
        device id."""
        try:
            state = await alarm_control_panels.get_alarm_control_panel_state(device_id)
        except Exception as err:
            _logger.warning("get_alarm_control_panel_state tool failed: {}", err)
            return f"Couldn't read that alarm control panel's state: {err}"
        return _clip(json.dumps(state, indent=2, default=str))

    @tool
    async def arm_home(device_id: str) -> str:
        """Arm an alarm control panel in home mode by device id. Takes
        real effect on the device. This panel does not accept a PIN/
        code through JARVIS -- if the device requires one, this call
        will fail honestly."""
        try:
            result = await alarm_control_panels.arm_home(device_id)
        except Exception as err:
            _logger.warning("arm_home tool failed: {}", err)
            return f"Couldn't arm that panel (home mode): {err}"
        return _clip(json.dumps(result, indent=2, default=str))

    @tool
    async def arm_away(device_id: str) -> str:
        """Arm an alarm control panel in away mode by device id. Takes
        real effect on the device. This panel does not accept a PIN/
        code through JARVIS -- if the device requires one, this call
        will fail honestly."""
        try:
            result = await alarm_control_panels.arm_away(device_id)
        except Exception as err:
            _logger.warning("arm_away tool failed: {}", err)
            return f"Couldn't arm that panel (away mode): {err}"
        return _clip(json.dumps(result, indent=2, default=str))

    @tool
    async def disarm(device_id: str) -> str:
        """Disarm an alarm control panel by device id. Removes
        protection -- takes real effect on the device. Requires
        interactive confirmation before it runs. This panel does not
        accept a PIN/code through JARVIS -- if the device requires
        one, this call will fail honestly."""
        try:
            result = await alarm_control_panels.disarm(device_id)
        except Exception as err:
            _logger.warning("disarm tool failed: {}", err)
            return f"Couldn't disarm that panel: {err}"
        return _clip(json.dumps(result, indent=2, default=str))

    return [
        list_alarm_control_panels,
        get_alarm_control_panel_state,
        arm_home,
        arm_away,
        disarm,
    ]


def _clip(text: str) -> str:
    if len(text) <= _MAX_RESULT_CHARS:
        return text
    return (
        text[:_MAX_RESULT_CHARS]
        + f"\n... (truncated at {_MAX_RESULT_CHARS} characters; narrow the query "
        "or ask for fewer results)"
    )
