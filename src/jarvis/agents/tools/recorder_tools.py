"""Agent tools wrapping
:class:`~jarvis.services.recorder_service.RecorderService` (M7
Recorder).

**Four tools -- the minimum coherent surface** (Logic Contract §16):
``start_recording``/``stop_recording``/``cancel_recording``/
``list_recordings``. No ``get_recording`` tool -- ``list_recordings``
already covers "what's active/recent," matching the minimum-surface
precedent every prior M7 slice's own tool set follows.

**Records JARVIS's own OS-automation actions only.** This does not
capture raw keyboard/mouse input, and does not capture agent-tool
invocations -- only actions dispatched through the existing
automation engine (`AutomationService.run_command`) while a recording
is active are ever candidates for capture (Logic Contract §6).

**Not confirmation-gated.** None of these tools are added to
``AgentSettings.confirm_required_tools`` -- starting/stopping/
cancelling a recording does not itself execute anything; the
resulting workflow's own future execution is independently,
separately gated at run time, unaffected by whether recording itself
required confirmation (Logic Contract §12).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool, tool

from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.services.recorder_service import RecorderService

_logger = get_logger("jarvis.agents.tools.recorder")

_MAX_RESULT_CHARS = 4_000


def build_recorder_tools(recorder: RecorderService) -> list[BaseTool]:
    @tool
    async def start_recording() -> str:
        """Start recording JARVIS's own OS-automation actions (not
        raw keyboard/mouse input, and not agent-tool calls) so they
        can later be saved as a reusable workflow. Only one recording
        can be active at a time."""
        try:
            result = await recorder.start_recording()
        except Exception as err:
            _logger.warning("start_recording tool failed: {}", err)
            return f"Couldn't start recording: {err}"
        return _clip(json.dumps(result, indent=2, default=str))

    @tool
    async def stop_recording(session_id: str, name: str, *, description: str = "") -> str:
        """Stop an active recording and save everything captured
        (that JARVIS understood) as a new standalone workflow with the
        given name. Fails if nothing supported was captured during the
        session."""
        try:
            result = await recorder.stop_recording(session_id, name=name, description=description)
        except Exception as err:
            _logger.warning("stop_recording tool failed: {}", err)
            return f"Couldn't stop recording: {err}"
        return _clip(json.dumps(result, indent=2, default=str))

    @tool
    async def cancel_recording(session_id: str) -> str:
        """Discard an active recording -- no workflow is created. The
        actions that occurred are still visible in ordinary execution
        history, just not turned into a workflow."""
        try:
            result = await recorder.cancel_recording(session_id)
        except Exception as err:
            _logger.warning("cancel_recording tool failed: {}", err)
            return f"Couldn't cancel recording: {err}"
        return _clip(json.dumps(result, indent=2, default=str))

    @tool
    async def list_recordings() -> str:
        """List every recording session (active, completed, and
        cancelled), most recent first."""
        try:
            rows = await recorder.list_recordings()
        except Exception as err:
            _logger.warning("list_recordings tool failed: {}", err)
            return f"Couldn't list recordings: {err}"
        if not rows:
            return "No recordings exist yet."
        return _clip(json.dumps(rows, indent=2, default=str))

    return [
        start_recording,
        stop_recording,
        cancel_recording,
        list_recordings,
    ]


def _clip(text: str) -> str:
    if len(text) <= _MAX_RESULT_CHARS:
        return text
    return (
        text[:_MAX_RESULT_CHARS]
        + f"\n... (truncated at {_MAX_RESULT_CHARS} characters; narrow the query "
        "or ask for fewer results)"
    )
