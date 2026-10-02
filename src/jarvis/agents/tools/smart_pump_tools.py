"""Agent tools wrapping
:class:`~jarvis.services.smart_pump_service.SmartPumpService`
(Milestone 12 Smart Pumps -- Switch-Backed Device Slice).

**Three tools, mirroring ``smart_switch_tools.py``'s structure minus
the list tool.** Every tool calls the same ``SmartPumpService`` method
the REST route does, so both end up in the same delegated
``SmartSwitchService`` permission check (``core:smart_switch`` under the
shared ``smart_home`` scope). No ``list_pumps`` tool exists: a pump is a
switch-backed device, so the already-shipped ``list_switches`` tool is
how the agent discovers pump-controllable device ids -- a ``list_pumps``
would return the identical rows.

**``pump_on`` and ``pump_off`` BOTH require interactive confirmation.**
This is deliberately *not* the one-directional asymmetry Smart Locks /
Sirens / Alarm Panels establish (``unlock_device``/``turn_siren_on``/
``disarm`` gated, their safe-direction counterparts not): for those, one
direction is unambiguously fail-safe (locking secures, silencing a siren
is always safe, arming adds protection). Neither pump direction carries
that guarantee -- starting a pump risks flooding or dry-run damage,
stopping one can end active protection or required circulation -- and
``docs/MASTER_ROADMAP.md``'s acceptance criterion names the water pump
as ``safety_critical: true`` requiring confirm-before-run with "no
silent execution". Both names are therefore added to
``AgentSettings.confirm_required_tools`` -- the existing
``AgentPermissionGate`` mechanism, not a new one.

**What this confirmation does NOT cover.** The gate keys on tool *name*
only; it cannot distinguish a pump-backed switch from any other switch,
so no per-device ``safety_critical`` enforcement exists (that is future
work, not claimed here). A scheduled workflow is unaffected either way:
background execution hardcodes ``confirm=None``, so ``pump_on``/
``pump_off`` steps are denied there by Policy A, and scheduled pump
operation is expected to go through the existing ``switch_on``/
``switch_off`` tools instead (which are not -- and have never been --
confirm-required).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool, tool

from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.services.smart_pump_service import SmartPumpService

_logger = get_logger("jarvis.agents.tools.smart_pump")

_MAX_RESULT_CHARS = 4_000


def _clip(text: str) -> str:
    if len(text) <= _MAX_RESULT_CHARS:
        return text
    return (
        text[:_MAX_RESULT_CHARS]
        + f"\n... (truncated at {_MAX_RESULT_CHARS} characters; narrow the query "
        "or ask for fewer results)"
    )


def build_smart_pump_tools(pumps: SmartPumpService) -> list[BaseTool]:
    @tool
    async def get_pump_state(device_id: str) -> str:
        """Get one smart pump's live state (on/off/unknown) and
        availability by device id. Pumps are switch-backed devices:
        use list_switches first to find the device id of the pump you
        want."""
        try:
            state = await pumps.get_state(device_id)
        except Exception as err:
            _logger.warning("get_pump_state tool failed: {}", err)
            return f"Couldn't read that pump's state: {err}"
        return _clip(json.dumps(state, indent=2, default=str))

    @tool
    async def pump_on(device_id: str) -> str:
        """Turn a smart pump on by device id. Takes real effect on the
        device -- starting water movement (flood/dry-run hazard) --
        so it requires interactive confirmation before it runs. Pumps
        are switch-backed devices: use list_switches first to find the
        device id."""
        try:
            result = await pumps.turn_on(device_id)
        except Exception as err:
            _logger.warning("pump_on tool failed: {}", err)
            return f"Couldn't turn the pump on: {err}"
        return _clip(json.dumps(result, indent=2, default=str))

    @tool
    async def pump_off(device_id: str) -> str:
        """Turn a smart pump off by device id. Takes real effect on the
        device -- stopping water movement may end active protection or
        required circulation -- so it requires interactive confirmation
        before it runs. Pumps are switch-backed devices: use
        list_switches first to find the device id."""
        try:
            result = await pumps.turn_off(device_id)
        except Exception as err:
            _logger.warning("pump_off tool failed: {}", err)
            return f"Couldn't turn the pump off: {err}"
        return _clip(json.dumps(result, indent=2, default=str))

    return [get_pump_state, pump_on, pump_off]
