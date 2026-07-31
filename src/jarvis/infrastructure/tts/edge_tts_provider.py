"""Microsoft Edge TTS adapter — free, online, genuinely streamed audio.

Uses the ``edge-tts`` package, which talks to the same neural-voice
service that powers Microsoft Edge's "Read aloud" feature. No API key is
required. Audio arrives as MP3 chunks over a websocket, which we forward
as-is — this is the provider best suited to the "start speaking before
the whole sentence is synthesized" requirement.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from jarvis.core.exceptions import TTSProviderError
from jarvis.core.logging.logger import get_logger
from jarvis.core.types import ProviderStatus
from jarvis.infrastructure.tts.base import TTSProviderBase

if TYPE_CHECKING:
    from jarvis.core.config.settings import EdgeTTSSettings, TTSSettings

_logger = get_logger("jarvis.infrastructure.tts.edge")


class EdgeTTSProvider(TTSProviderBase):
    name: str = "edge_tts"
    supports_streaming: bool = True

    def __init__(self, tts: TTSSettings, edge: EdgeTTSSettings) -> None:
        self._tts = tts
        self._edge = edge

    def _module(self):
        try:
            import edge_tts
        except ImportError as err:
            raise TTSProviderError(
                "Edge TTS selected but the 'edge-tts' package isn't "
                "installed. Run `pip install edge-tts`, or switch TTS "
                "provider in Settings."
            ) from err
        return edge_tts

    async def health(self) -> ProviderStatus:
        if not self._tts.enabled or not self._edge.enabled:
            return ProviderStatus(name=self.name, enabled=False, healthy=False, detail="disabled")
        try:
            self._module()
            return ProviderStatus(name=self.name, enabled=True, healthy=True)
        except TTSProviderError as err:
            return ProviderStatus(name=self.name, enabled=True, healthy=False, detail=str(err))

    async def synthesize_stream(
        self,
        text: str,
        *,
        voice: str | None = None,
        model: str | None = None,
    ) -> AsyncIterator[bytes]:
        if not text.strip():
            return
        edge_tts = self._module()
        communicate = edge_tts.Communicate(
            text,
            voice=voice or self._edge.voice,
            rate=self._edge.rate,
            pitch=self._edge.pitch_hz,
        )
        try:
            async for event in communicate.stream():
                if event.get("type") == "audio":
                    data = event.get("data")
                    if data:
                        yield data
        except Exception as err:
            raise TTSProviderError(f"Edge TTS streaming failed: {err}") from err

    async def synthesize_to_bytes(
        self,
        text: str,
        *,
        voice: str | None = None,
        model: str | None = None,
    ) -> bytes:
        parts = [chunk async for chunk in self.synthesize_stream(text, voice=voice, model=model)]
        return b"".join(parts)
