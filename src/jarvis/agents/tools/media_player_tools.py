"""Agent tools wrapping
:class:`~jarvis.services.media_player_service.MediaPlayerService`
(Milestone 12 Appliance Control -- Media Player Core Slice).

**Five transport tools, one per verb**, mirroring
``vacuum_humidifier_tools.py``'s vacuum half: independent actions, not
attributes that combine, so no merged mutation tool exists for them.

**One merged state tool** for volume/mute/source, mirroring
``thermostat_tools.py``'s shape: these three combine into one user
intent ("mute it and switch to Spotify").

**Every tool calls the same ``MediaPlayerService`` the REST route
does**, so both trip the same permission check: reads are ungated, and
mutations (transport and merged state alike) require the
``smart_home`` grant for ``core:media_players``. No tool reaches
``ConnectivityService`` or a connector directly. No mutation tool
requires confirmation -- ordinary playback control carries no
comparable risk to ``unlock_device`` (Logic Contract §19).
"""

from __future__ import annotations

import json
from collections.abc import Awaitable
from typing import TYPE_CHECKING, Any

from langchain_core.tools import BaseTool, tool

from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.services.media_player_service import MediaPlayerService

_logger = get_logger("jarvis.agents.tools.media_player")

_MAX_RESULT_CHARS = 4_000


async def _run_transport(tool_name: str, verb: str, call: Awaitable[dict[str, Any]]) -> str:
    """Shared by the five transport tools -- they are structurally
    identical (call one `MediaPlayerService` method, catch, format),
    so factoring this out keeps `build_media_player_tools` itself short
    rather than repeating the same try/except five times."""
    try:
        result = await call
    except Exception as err:
        _logger.warning("{} tool failed: {}", tool_name, err)
        return f"Couldn't {verb} that media player: {err}"
    return _clip(json.dumps(result, indent=2, default=str))


def build_media_player_tools(service: MediaPlayerService) -> list[BaseTool]:
    @tool
    async def list_media_players(home_id: str = "", room_id: str = "") -> str:
        """List known media players, optionally filtered by home_id or
        room_id. Entries show last-known DB fields only; call
        get_media_player_state for one device's live state."""
        try:
            rows = await service.list_media_players(
                home_id=home_id or None, room_id=room_id or None
            )
        except Exception as err:
            _logger.warning("list_media_players tool failed: {}", err)
            return f"Couldn't list media players: {err}"
        if not rows:
            return "No media players match that filter."
        return _clip(json.dumps(rows, indent=2, default=str))

    @tool
    async def get_media_player_state(device_id: str) -> str:
        """Get one media player's live reading by device id: playback
        state, availability, volume, mute, source (and the sources it
        supports), and what's currently playing (title/artist). Use
        list_media_players first to find the device id."""
        try:
            state = await service.get_media_player_state(device_id)
        except Exception as err:
            _logger.warning("get_media_player_state tool failed: {}", err)
            return f"Couldn't read that media player's state: {err}"
        return _clip(json.dumps(state, indent=2, default=str))

    @tool
    async def media_play(device_id: str) -> str:
        """Start or resume playback on a media player by device id.
        Takes real effect on the device."""
        return await _run_transport("media_play", "play", service.play(device_id))

    @tool
    async def media_pause(device_id: str) -> str:
        """Pause playback on a media player by device id. Takes real
        effect on the device."""
        return await _run_transport("media_pause", "pause", service.pause(device_id))

    @tool
    async def media_stop(device_id: str) -> str:
        """Stop playback on a media player by device id. Takes real
        effect on the device."""
        return await _run_transport("media_stop", "stop", service.stop(device_id))

    @tool
    async def media_next(device_id: str) -> str:
        """Skip to the next track on a media player by device id.
        Takes real effect on the device."""
        return await _run_transport("media_next", "skip", service.next_track(device_id))

    @tool
    async def media_previous(device_id: str) -> str:
        """Go back to the previous track on a media player by device
        id. Takes real effect on the device."""
        return await _run_transport(
            "media_previous", "go back on", service.previous_track(device_id)
        )

    @tool
    async def set_media_player_state(
        device_id: str,
        volume: float | None = None,
        muted: bool | None = None,
        source: str = "",
    ) -> str:
        """Set a media player's volume (0.0-1.0), mute state, and/or
        source in one call. Supply at least one of them. volume must be
        the device's native 0.0-1.0 scale, not a percentage. source
        must be one the device reports as supported (see
        get_media_player_state). Takes real effect on the device."""
        try:
            result = await service.set_media_player_state(
                device_id, volume=volume, muted=muted, source=source or None
            )
        except Exception as err:
            _logger.warning("set_media_player_state tool failed: {}", err)
            return f"Couldn't change that media player: {err}"
        return _clip(json.dumps(result, indent=2, default=str))

    return [
        list_media_players,
        get_media_player_state,
        media_play,
        media_pause,
        media_stop,
        media_next,
        media_previous,
        set_media_player_state,
    ]


def _clip(text: str) -> str:
    if len(text) <= _MAX_RESULT_CHARS:
        return text
    return (
        text[:_MAX_RESULT_CHARS]
        + f"\n... (truncated at {_MAX_RESULT_CHARS} characters; narrow the query "
        "or ask for fewer results)"
    )
