"""Agent tools wrapping :class:`~jarvis.services.voice_service.VoiceService`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool, tool

from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.services.voice_service import VoiceService

_logger = get_logger("jarvis.agents.tools.voice")


def build_voice_tools(voice: VoiceService) -> list[BaseTool]:
    @tool
    async def speak_text(text: str) -> str:
        """Speak text aloud to the user via text-to-speech, independent of
        the agent's own final answer (useful for an interim status update
        during a long-running task)."""
        try:
            await voice.speak(text)
        except Exception as err:
            _logger.warning("speak_text tool failed: {}", err)
            return f"Failed to speak: {err}"
        return "Spoken."

    return [speak_text]
