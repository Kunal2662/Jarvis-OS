"""ElevenLabs adapter — premium online TTS with true audio streaming.

Talks directly to the ElevenLabs REST API over ``httpx`` (already a
project dependency) rather than pulling in the official SDK, keeping the
adapter small and dependency-light.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

import httpx

from jarvis.core.exceptions import TTSProviderError
from jarvis.core.logging.logger import get_logger
from jarvis.core.types import ProviderStatus
from jarvis.infrastructure.tts.base import TTSProviderBase

if TYPE_CHECKING:
    from jarvis.core.config.settings import ElevenLabsSettings, TTSSettings

_logger = get_logger("jarvis.infrastructure.tts.elevenlabs")


class ElevenLabsTTSProvider(TTSProviderBase):
    name: str = "elevenlabs"
    supports_streaming: bool = True

    def __init__(self, tts: TTSSettings, elevenlabs: ElevenLabsSettings) -> None:
        self._tts = tts
        self._eleven = elevenlabs

    def _require_key(self) -> str:
        key = self._eleven.api_key.get_secret_value()
        if not key:
            raise TTSProviderError(
                "ElevenLabs TTS selected but JARVIS_ELEVENLABS_API_KEY is "
                "empty. Add a key in Settings → API Keys, or switch TTS "
                "provider."
            )
        return key

    async def health(self) -> ProviderStatus:
        if not self._tts.enabled or not self._eleven.enabled:
            return ProviderStatus(name=self.name, enabled=False, healthy=False, detail="disabled")
        try:
            key = self._require_key()
        except TTSProviderError as err:
            return ProviderStatus(name=self.name, enabled=True, healthy=False, detail=str(err))
        try:
            async with httpx.AsyncClient(base_url=self._eleven.base_url, timeout=10) as client:
                resp = await client.get("/v1/user", headers={"xi-api-key": key})
                resp.raise_for_status()
            return ProviderStatus(name=self.name, enabled=True, healthy=True)
        except Exception as err:
            return ProviderStatus(
                name=self.name, enabled=True, healthy=False, detail=f"{type(err).__name__}: {err}"
            )

    async def synthesize_stream(
        self,
        text: str,
        *,
        voice: str | None = None,
        model: str | None = None,
    ) -> AsyncIterator[bytes]:
        if not text.strip():
            return
        key = self._require_key()
        voice_id = voice or self._eleven.voice_id
        payload = {
            "text": text,
            "model_id": model or self._eleven.model,
        }
        url = f"{self._eleven.base_url}/v1/text-to-speech/{voice_id}/stream"
        try:
            async with (
                httpx.AsyncClient(timeout=30) as client,
                client.stream(
                    "POST",
                    url,
                    json=payload,
                    headers={"xi-api-key": key, "accept": "audio/mpeg"},
                ) as resp,
            ):
                resp.raise_for_status()
                async for chunk in resp.aiter_bytes():
                    if chunk:
                        yield chunk
        except httpx.HTTPError as err:
            raise TTSProviderError(f"ElevenLabs TTS error: {err}") from err

    async def synthesize_to_bytes(
        self,
        text: str,
        *,
        voice: str | None = None,
        model: str | None = None,
    ) -> bytes:
        parts = [chunk async for chunk in self.synthesize_stream(text, voice=voice, model=model)]
        return b"".join(parts)
