"""Agent tools wrapping
:class:`~jarvis.services.smart_lock_service.SmartLockService`
(Milestone 12 Smart Locks).

Four tools, mirroring ``smart_lighting_tools.py``'s structure exactly.
Named ``lock_device``/``unlock_device`` rather than the bare verbs
``lock``/``unlock`` -- every other tool in this registry uses a
verb+object shape (``set_light_state``, ``apply_scene``), and this
keeps ``AgentSettings.confirm_required_tools`` entries unambiguous.

**``unlock_device`` requires interactive confirmation by default**
(``core/config/settings.py``'s ``confirm_required_tools``) -- unlocking
is the direction with real security consequence; ``lock_device`` does
not, since locking is the fail-safe direction. See
``docs/M12_SMART_LOCKS_LOGIC_CONTRACT.md`` §14 for the full reasoning.
This tool file does not implement the confirmation check itself -- that
happens in the graph's existing ``AgentPermissionGate``
(``agents/permission.py``), reached before any tool call executes;
nothing here needs to know about it.

**No tool authorizes anything, and no tool bypasses the permission
gate.** Every tool below calls the same ``SmartLockService`` method the
REST route does, so both trip the same ``smart_home`` ``PermissionModel``
check. A tool call from an unauthorized principal fails exactly as a
REST call would -- the agent gets no privileged path.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool, tool

from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.services.smart_lock_service import SmartLockService

_logger = get_logger("jarvis.agents.tools.smart_lock")

_MAX_RESULT_CHARS = 4_000


def build_smart_lock_tools(smart_lock: SmartLockService) -> list[BaseTool]:
    @tool
    async def list_locks(home_id: str = "", room_id: str = "") -> str:
        """List known locks, optionally filtered by home_id or
        room_id. Each entry's last-known locked state may be stale;
        call get_lock_status for one lock's live reading."""
        try:
            rows = await smart_lock.list_locks(home_id=home_id or None, room_id=room_id or None)
        except Exception as err:
            _logger.warning("list_locks tool failed: {}", err)
            return f"Couldn't list locks: {err}"
        if not rows:
            return "No locks match that filter."
        return _clip(json.dumps(rows, indent=2, default=str))

    @tool
    async def get_lock_status(device_id: str) -> str:
        """Get one lock's live state (locked/unlocked/unknown) and
        availability by device id. Use list_locks first to find the
        device id."""
        try:
            state = await smart_lock.get_lock_state(device_id)
        except Exception as err:
            _logger.warning("get_lock_status tool failed: {}", err)
            return f"Couldn't read that lock's state: {err}"
        return _clip(json.dumps(state, indent=2, default=str))

    @tool
    async def lock_device(device_id: str) -> str:
        """Lock a door by device id. Takes real effect on the device --
        confirm with the user before calling it."""
        try:
            result = await smart_lock.lock(device_id)
        except Exception as err:
            _logger.warning("lock_device tool failed: {}", err)
            return f"Couldn't lock that device: {err}"
        return _clip(json.dumps(result, indent=2, default=str))

    @tool
    async def unlock_device(device_id: str) -> str:
        """Unlock a door by device id. Physically safety-relevant --
        this tool requires interactive user confirmation before it
        runs, and always confirm with the user yourself regardless."""
        try:
            result = await smart_lock.unlock(device_id)
        except Exception as err:
            _logger.warning("unlock_device tool failed: {}", err)
            return f"Couldn't unlock that device: {err}"
        return _clip(json.dumps(result, indent=2, default=str))

    return [list_locks, get_lock_status, lock_device, unlock_device]


def _clip(text: str) -> str:
    if len(text) <= _MAX_RESULT_CHARS:
        return text
    return (
        text[:_MAX_RESULT_CHARS]
        + f"\n... (truncated at {_MAX_RESULT_CHARS} characters; narrow the query "
        "or ask for fewer results)"
    )
