"""Agent tools wrapping
:class:`~jarvis.services.camera_service.CameraService` (Milestone 12
Smart Cameras -- Core Camera Slice).

Six tools, one per verb, mirroring ``smart_lock_tools.py``'s structure
exactly -- a camera has four independent commands, not attributes that
combine, so no merged mutation tool exists.

**``camera_turn_off``/``disable_camera_motion_detection`` require
interactive confirmation by default** (``core/config/settings.py``'s
``confirm_required_tools``) -- both **reduce** a home's surveillance
posture, the same risk tier ``unlock_device``/``turn_siren_on``/
``disarm`` already occupy; ``camera_turn_on``/
``enable_camera_motion_detection`` (which increase it) do not, mirroring
``lock_device``/``arm_home`` never needing it either. This tool file
does not implement the confirmation check itself -- that happens in the
graph's existing ``AgentPermissionGate``, reached before any tool call
executes.

**No tool authorizes anything, and no tool bypasses the permission
gate.** Every tool below calls the same ``CameraService`` method the
REST route does, so both trip the same ``smart_home`` ``PermissionModel``
check -- including reads, which ``CameraService`` gates the same way
``SensorService`` does (Logic Contract §4).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool, tool

from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.services.camera_service import CameraService

_logger = get_logger("jarvis.agents.tools.camera")

_MAX_RESULT_CHARS = 4_000


def build_camera_tools(cameras: CameraService) -> list[BaseTool]:
    @tool
    async def list_cameras(home_id: str = "", room_id: str = "") -> str:
        """List known cameras, optionally filtered by home_id or
        room_id. Each entry's last-known state may be stale; call
        get_camera_state for one camera's live reading."""
        try:
            rows = await cameras.list_cameras(home_id=home_id or None, room_id=room_id or None)
        except Exception as err:
            _logger.warning("list_cameras tool failed: {}", err)
            return f"Couldn't list cameras: {err}"
        if not rows:
            return "No cameras match that filter."
        return _clip(json.dumps(rows, indent=2, default=str))

    @tool
    async def get_camera_state(device_id: str) -> str:
        """Get one camera's live state (e.g. idle/recording/streaming),
        motion-detection status, and availability by device id. Use
        list_cameras first to find the device id."""
        try:
            state = await cameras.get_camera_state(device_id)
        except Exception as err:
            _logger.warning("get_camera_state tool failed: {}", err)
            return f"Couldn't read that camera's state: {err}"
        return _clip(json.dumps(state, indent=2, default=str))

    @tool
    async def camera_turn_on(device_id: str) -> str:
        """Turn a camera on by device id. Takes real effect on the
        device."""
        try:
            result = await cameras.turn_on(device_id)
        except Exception as err:
            _logger.warning("camera_turn_on tool failed: {}", err)
            return f"Couldn't turn that camera on: {err}"
        return _clip(json.dumps(result, indent=2, default=str))

    @tool
    async def camera_turn_off(device_id: str) -> str:
        """Turn a camera off by device id. Reduces this home's
        surveillance coverage -- this tool requires interactive user
        confirmation before it runs, and always confirm with the user
        yourself regardless."""
        try:
            result = await cameras.turn_off(device_id)
        except Exception as err:
            _logger.warning("camera_turn_off tool failed: {}", err)
            return f"Couldn't turn that camera off: {err}"
        return _clip(json.dumps(result, indent=2, default=str))

    @tool
    async def enable_camera_motion_detection(device_id: str) -> str:
        """Enable motion detection on a camera by device id. Takes
        real effect on the device -- not every camera integration
        supports this."""
        try:
            result = await cameras.enable_motion_detection(device_id)
        except Exception as err:
            _logger.warning("enable_camera_motion_detection tool failed: {}", err)
            return f"Couldn't enable motion detection on that camera: {err}"
        return _clip(json.dumps(result, indent=2, default=str))

    @tool
    async def disable_camera_motion_detection(device_id: str) -> str:
        """Disable motion detection on a camera by device id. Reduces
        this home's surveillance coverage -- this tool requires
        interactive user confirmation before it runs, and always
        confirm with the user yourself regardless."""
        try:
            result = await cameras.disable_motion_detection(device_id)
        except Exception as err:
            _logger.warning("disable_camera_motion_detection tool failed: {}", err)
            return f"Couldn't disable motion detection on that camera: {err}"
        return _clip(json.dumps(result, indent=2, default=str))

    return [
        list_cameras,
        get_camera_state,
        camera_turn_on,
        camera_turn_off,
        enable_camera_motion_detection,
        disable_camera_motion_detection,
    ]


def _clip(text: str) -> str:
    if len(text) <= _MAX_RESULT_CHARS:
        return text
    return (
        text[:_MAX_RESULT_CHARS]
        + f"\n... (truncated at {_MAX_RESULT_CHARS} characters; narrow the query "
        "or ask for fewer results)"
    )
