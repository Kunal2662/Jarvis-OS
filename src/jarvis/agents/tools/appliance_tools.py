"""Agent tools wrapping
:class:`~jarvis.services.appliance_service.ApplianceService` (Milestone
12 Appliance Control -- Core Appliance Slice: Fans + Covers; Fan
Percentage + Cover Position Slice).

Ten tools, mirroring ``smart_switch_tools.py``'s structure, doubled for
the two capabilities this slice supports, plus one dedicated
percentage/position-setting tool per capability -- not an optional
argument added to ``fan_on``/``cover_open`` (see
``docs/M12_APPLIANCE_FAN_COVER_POSITION_LOGIC_CONTRACT.md`` §11).

**No tool authorizes anything, and no tool bypasses the permission
gate.** Every mutating tool below calls the same ``ApplianceService``
method the REST route does, so both trip the same ``smart_home``
``PermissionModel`` check. No tool here is added to ``AgentSettings.
confirm_required_tools`` -- neither a fan nor a cover (nor adjusting
either's speed/position) is physically safety-relevant the way a lock
is.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool, tool

from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.services.appliance_service import ApplianceService

_logger = get_logger("jarvis.agents.tools.appliance")

_MAX_RESULT_CHARS = 4_000


def build_appliance_tools(appliances: ApplianceService) -> list[BaseTool]:
    """Composes the fan and cover tool sets -- split into two private
    helpers purely to keep each factory function's own statement count
    manageable (ten tools total would otherwise be one long function);
    the public signature/behavior is unchanged."""
    return [*_build_fan_tools(appliances), *_build_cover_tools(appliances)]


def _build_fan_tools(appliances: ApplianceService) -> list[BaseTool]:
    @tool
    async def list_fans(home_id: str = "", room_id: str = "") -> str:
        """List known fans, optionally filtered by home_id or room_id.
        Each entry's last-known on/off state may be stale; call
        get_fan_state for one fan's live reading."""
        try:
            rows = await appliances.list_fans(home_id=home_id or None, room_id=room_id or None)
        except Exception as err:
            _logger.warning("list_fans tool failed: {}", err)
            return f"Couldn't list fans: {err}"
        if not rows:
            return "No fans match that filter."
        return _clip(json.dumps(rows, indent=2, default=str))

    @tool
    async def get_fan_state(device_id: str) -> str:
        """Get one fan's live state (on/off/unknown) and availability
        by device id. Use list_fans first to find the device id."""
        try:
            state = await appliances.get_fan_state(device_id)
        except Exception as err:
            _logger.warning("get_fan_state tool failed: {}", err)
            return f"Couldn't read that fan's state: {err}"
        return _clip(json.dumps(state, indent=2, default=str))

    @tool
    async def fan_on(device_id: str) -> str:
        """Turn a fan on by device id. Takes real effect on the device
        -- confirm with the user before calling it."""
        try:
            result = await appliances.fan_on(device_id)
        except Exception as err:
            _logger.warning("fan_on tool failed: {}", err)
            return f"Couldn't turn that fan on: {err}"
        return _clip(json.dumps(result, indent=2, default=str))

    @tool
    async def fan_off(device_id: str) -> str:
        """Turn a fan off by device id. Takes real effect on the device
        -- confirm with the user before calling it."""
        try:
            result = await appliances.fan_off(device_id)
        except Exception as err:
            _logger.warning("fan_off tool failed: {}", err)
            return f"Couldn't turn that fan off: {err}"
        return _clip(json.dumps(result, indent=2, default=str))

    @tool
    async def set_fan_percentage(device_id: str, percentage: int) -> str:
        """Set a fan's speed to an exact percentage (0-100) by device
        id. 0 is a valid value, sent as-is -- it does not turn the fan
        off. Takes real effect on the device -- confirm with the user
        before calling it."""
        try:
            result = await appliances.set_fan_percentage(device_id, percentage)
        except Exception as err:
            _logger.warning("set_fan_percentage tool failed: {}", err)
            return f"Couldn't set that fan's percentage: {err}"
        return _clip(json.dumps(result, indent=2, default=str))

    return [list_fans, get_fan_state, fan_on, fan_off, set_fan_percentage]


def _build_cover_tools(appliances: ApplianceService) -> list[BaseTool]:
    @tool
    async def list_covers(home_id: str = "", room_id: str = "") -> str:
        """List known covers/blinds/curtains, optionally filtered by
        home_id or room_id. Each entry's last-known open/closed state
        may be stale; call get_cover_state for one cover's live
        reading."""
        try:
            rows = await appliances.list_covers(home_id=home_id or None, room_id=room_id or None)
        except Exception as err:
            _logger.warning("list_covers tool failed: {}", err)
            return f"Couldn't list covers: {err}"
        if not rows:
            return "No covers match that filter."
        return _clip(json.dumps(rows, indent=2, default=str))

    @tool
    async def get_cover_state(device_id: str) -> str:
        """Get one cover's live state (open/closed/opening/closing/
        unknown) and availability by device id. Use list_covers first
        to find the device id."""
        try:
            state = await appliances.get_cover_state(device_id)
        except Exception as err:
            _logger.warning("get_cover_state tool failed: {}", err)
            return f"Couldn't read that cover's state: {err}"
        return _clip(json.dumps(state, indent=2, default=str))

    @tool
    async def cover_open(device_id: str) -> str:
        """Open a cover/blind/curtain by device id. Takes real effect
        on the device -- confirm with the user before calling it."""
        try:
            result = await appliances.cover_open(device_id)
        except Exception as err:
            _logger.warning("cover_open tool failed: {}", err)
            return f"Couldn't open that cover: {err}"
        return _clip(json.dumps(result, indent=2, default=str))

    @tool
    async def cover_close(device_id: str) -> str:
        """Close a cover/blind/curtain by device id. Takes real effect
        on the device -- confirm with the user before calling it."""
        try:
            result = await appliances.cover_close(device_id)
        except Exception as err:
            _logger.warning("cover_close tool failed: {}", err)
            return f"Couldn't close that cover: {err}"
        return _clip(json.dumps(result, indent=2, default=str))

    @tool
    async def set_cover_position(device_id: str, position: int) -> str:
        """Set a cover/blind/curtain to an exact position (0-100,
        0=closed, 100=open) by device id. Takes real effect on the
        device -- confirm with the user before calling it."""
        try:
            result = await appliances.set_cover_position(device_id, position)
        except Exception as err:
            _logger.warning("set_cover_position tool failed: {}", err)
            return f"Couldn't set that cover's position: {err}"
        return _clip(json.dumps(result, indent=2, default=str))

    return [list_covers, get_cover_state, cover_open, cover_close, set_cover_position]


def _clip(text: str) -> str:
    if len(text) <= _MAX_RESULT_CHARS:
        return text
    return (
        text[:_MAX_RESULT_CHARS]
        + f"\n... (truncated at {_MAX_RESULT_CHARS} characters; narrow the query "
        "or ask for fewer results)"
    )
