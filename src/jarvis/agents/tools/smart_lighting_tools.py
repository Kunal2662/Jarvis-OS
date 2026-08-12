"""Agent tools wrapping
:class:`~jarvis.services.smart_lighting_service.SmartLightingService`
(Milestone 12 Connectivity REST + Smart Lighting).

One tool per normalized operation, unlike ``integration_tools.py``'s
discover-then-invoke pair. Smart Lighting's vocabulary is small and
fixed (on/off, brightness, color, color temperature, room/group
fan-out, scene application) -- the same reason ``automation_tools.py``
and ``system_tools.py`` expose one tool per capability rather than a
generic dispatcher; a catalogue-style ``describe`` tool only earns its
keep once the vocabulary is large enough that listing it beats naming
it, which M11's 65-operation integration catalogue is and this is not.

**Scene creation/deletion are deliberately not tools here.** Defining
what a scene *is* is a setup action a person does once through the REST
surface or a future UI; *applying* an already-defined scene is the
repeated, conversational action an agent is actually asked to do
("turn on movie night") -- so only ``apply_scene``/``list_scenes`` are
exposed, not ``create_scene``/``delete_scene``.

**No tool authorizes anything, and no tool bypasses the permission
gate.** Every tool below calls the same ``SmartLightingService`` method
the REST route does, so both trip the same ``smart_home``
``PermissionModel`` check (see ``services/smart_lighting_service.py``'s
own module docstring). A tool call from an unauthorized principal fails
exactly as a REST call would -- the agent gets no privileged path.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool, tool

from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.services.smart_lighting_service import SmartLightingService

_logger = get_logger("jarvis.agents.tools.smart_lighting")

_MAX_RESULT_CHARS = 4_000


def build_smart_lighting_tools(smart_lighting: SmartLightingService) -> list[BaseTool]:
    @tool
    async def list_lights(home_id: str = "", room_id: str = "") -> str:
        """List known lights, optionally filtered by home_id or room_id.
        Each entry's last-known state (on/brightness/color) may be stale;
        call get_light_state for one light's live reading."""
        try:
            rows = await smart_lighting.list_lights(
                home_id=home_id or None, room_id=room_id or None
            )
        except Exception as err:
            _logger.warning("list_lights tool failed: {}", err)
            return f"Couldn't list lights: {err}"
        if not rows:
            return "No lights match that filter."
        return _clip(json.dumps(rows, indent=2, default=str))

    @tool
    async def get_light_state(device_id: str) -> str:
        """Get one light's live state (on/off, brightness, color
        temperature, color) by device id. Use list_lights first to find
        the device id."""
        try:
            state = await smart_lighting.get_light_state(device_id)
        except Exception as err:
            _logger.warning("get_light_state tool failed: {}", err)
            return f"Couldn't read that light's state: {err}"
        return _clip(json.dumps(state, indent=2, default=str))

    @tool
    async def set_light_state(
        device_id: str,
        on: bool | None = None,
        brightness: int | None = None,
        color_temp_kelvin: int | None = None,
        color: list[int] | None = None,
    ) -> str:
        """Change one light: on/off, brightness (0-100), color
        temperature in Kelvin, or an (r, g, b) color (each 0-255). Set
        only the attributes you want to change. This takes real effect
        on the device -- confirm with the user before calling it."""
        try:
            result = await smart_lighting.set_light_state(
                device_id,
                on=on,
                brightness=brightness,
                color_temp_kelvin=color_temp_kelvin,
                color=color,
            )
        except Exception as err:
            _logger.warning("set_light_state tool failed: {}", err)
            return f"Couldn't change that light: {err}"
        return _clip(json.dumps(result, indent=2, default=str))

    @tool
    async def set_room_lights(
        room_id: str,
        on: bool | None = None,
        brightness: int | None = None,
        color_temp_kelvin: int | None = None,
        color: list[int] | None = None,
    ) -> str:
        """Change every light in a room at once. Same attributes as
        set_light_state. Takes real effect -- confirm with the user
        first."""
        try:
            results = await smart_lighting.apply_room(
                room_id,
                on=on,
                brightness=brightness,
                color_temp_kelvin=color_temp_kelvin,
                color=color,
            )
        except Exception as err:
            _logger.warning("set_room_lights tool failed: {}", err)
            return f"Couldn't change that room's lights: {err}"
        if not results:
            return f"No lights found in room {room_id!r}."
        return _clip(json.dumps(results, indent=2, default=str))

    @tool
    async def set_group_lights(
        group_id: str,
        on: bool | None = None,
        brightness: int | None = None,
        color_temp_kelvin: int | None = None,
        color: list[int] | None = None,
    ) -> str:
        """Change every light in a device group at once. Same
        attributes as set_light_state. Takes real effect -- confirm with
        the user first."""
        try:
            results = await smart_lighting.apply_group(
                group_id,
                on=on,
                brightness=brightness,
                color_temp_kelvin=color_temp_kelvin,
                color=color,
            )
        except Exception as err:
            _logger.warning("set_group_lights tool failed: {}", err)
            return f"Couldn't change that group's lights: {err}"
        if not results:
            return f"No lights found in group {group_id!r}."
        return _clip(json.dumps(results, indent=2, default=str))

    @tool
    async def list_scenes(home_id: str = "") -> str:
        """List saved lighting scenes, optionally filtered by home_id."""
        try:
            rows = await smart_lighting.list_scenes(home_id=home_id or None)
        except Exception as err:
            _logger.warning("list_scenes tool failed: {}", err)
            return f"Couldn't list scenes: {err}"
        if not rows:
            return "No saved scenes."
        return _clip(json.dumps(rows, indent=2, default=str))

    @tool
    async def apply_scene(scene_id: str) -> str:
        """Apply a saved lighting scene by id -- sets every light it
        defines to its stored state. Use list_scenes first to find the
        scene id. Takes real effect -- confirm with the user first."""
        try:
            results = await smart_lighting.apply_scene(scene_id)
        except Exception as err:
            _logger.warning("apply_scene tool failed: {}", err)
            return f"Couldn't apply that scene: {err}"
        return _clip(json.dumps(results, indent=2, default=str))

    return [
        list_lights,
        get_light_state,
        set_light_state,
        set_room_lights,
        set_group_lights,
        list_scenes,
        apply_scene,
    ]


def _clip(text: str) -> str:
    if len(text) <= _MAX_RESULT_CHARS:
        return text
    return (
        text[:_MAX_RESULT_CHARS]
        + f"\n... (truncated at {_MAX_RESULT_CHARS} characters; narrow the query "
        "or ask for fewer results)"
    )
