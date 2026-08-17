"""Agent tools wrapping
:class:`~jarvis.services.siren_service.SirenService` (Milestone 12
Security & Safety -- Siren Integration Slice).

**Four tools, mirroring ``smart_switch_tools.py``'s structure.** Every
tool calls the same ``SirenService`` method the REST route does, so
both trip the same ``smart_home`` ``PermissionModel`` check for
``core:sirens``.

**``turn_siren_on`` requires interactive confirmation --
``turn_siren_off`` does not.** The same directional-risk asymmetry
``smart_lock_tools.py``'s own ``unlock_device`` already established
(locking needs no confirmation, unlocking does): turning a siren on is
loud, disruptive, and can draw an unwanted emergency response; turning
one off is always the safe direction. ``turn_siren_on`` is added to
``AgentSettings.confirm_required_tools`` -- the existing
``AgentPermissionGate`` mechanism, not a new one (Logic Contract §10).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool, tool

from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.services.siren_service import SirenService

_logger = get_logger("jarvis.agents.tools.siren")

_MAX_RESULT_CHARS = 4_000


def build_siren_tools(sirens: SirenService) -> list[BaseTool]:
    @tool
    async def list_sirens(home_id: str = "", room_id: str = "") -> str:
        """List known sirens, optionally filtered by home_id or
        room_id. Entries show last-known DB fields only; call
        get_siren_state for one siren's live state."""
        try:
            rows = await sirens.list_sirens(home_id=home_id or None, room_id=room_id or None)
        except Exception as err:
            _logger.warning("list_sirens tool failed: {}", err)
            return f"Couldn't list sirens: {err}"
        if not rows:
            return "No sirens match that filter."
        return _clip(json.dumps(rows, indent=2, default=str))

    @tool
    async def get_siren_state(device_id: str) -> str:
        """Get one siren's live on/off state and availability by
        device id. Use list_sirens first to find the device id."""
        try:
            state = await sirens.get_siren_state(device_id)
        except Exception as err:
            _logger.warning("get_siren_state tool failed: {}", err)
            return f"Couldn't read that siren's state: {err}"
        return _clip(json.dumps(state, indent=2, default=str))

    @tool
    async def turn_siren_on(device_id: str) -> str:
        """Turn a siren on by device id. Loud and disruptive -- takes
        real effect on the device. Requires interactive confirmation
        before it runs."""
        try:
            result = await sirens.turn_on(device_id)
        except Exception as err:
            _logger.warning("turn_siren_on tool failed: {}", err)
            return f"Couldn't turn that siren on: {err}"
        return _clip(json.dumps(result, indent=2, default=str))

    @tool
    async def turn_siren_off(device_id: str) -> str:
        """Turn a siren off by device id. Always the safe direction --
        no confirmation required. Takes real effect on the device."""
        try:
            result = await sirens.turn_off(device_id)
        except Exception as err:
            _logger.warning("turn_siren_off tool failed: {}", err)
            return f"Couldn't turn that siren off: {err}"
        return _clip(json.dumps(result, indent=2, default=str))

    return [list_sirens, get_siren_state, turn_siren_on, turn_siren_off]


def _clip(text: str) -> str:
    if len(text) <= _MAX_RESULT_CHARS:
        return text
    return (
        text[:_MAX_RESULT_CHARS]
        + f"\n... (truncated at {_MAX_RESULT_CHARS} characters; narrow the query "
        "or ask for fewer results)"
    )
