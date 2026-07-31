"""OpenAI TTS adapter using the async ``openai`` client.

Returns the raw encoded audio bytes; playback is the audio-player's job.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from openai import APIError, AsyncOpenAI

from jarvis.core.exceptions import TTSProviderError
from jarvis.core.logging.logger import get_logger
from jarvis.core.types import ProviderStatus
from jarvis.infrastructure.tts.base import TTSProviderBase

if TYPE_CHECKING:
    from jarvis.core.config.settings import OpenAISettings, TTSSettings

_logger = get_logger("jarvis.infrastructure.tts.openai")


class OpenAITTSProvider(TTSProviderBase):
    name: str = "openai_tts"
    supports_streaming: bool = True

    def __init__(self, tts: TTSSettings, openai: OpenAISettings) -> None:
        self._tts = tts
        self._openai = openai
        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            key = self._openai.api_key.get_secret_value()
            if not key:
                raise TTSProviderError("OpenAI TTS selected but JARVIS_OPENAI_API_KEY is empty.")
            self._client = AsyncOpenAI(
                api_key=key,
                base_url=self._openai.base_url or None,
                organization=self._openai.org or None,
                max_retries=2,
            )
        return self._client

    async def health(self) -> ProviderStatus:
        if not self._tts.enabled:
            return ProviderStatus(name=self.name, enabled=False, healthy=False, detail="disabled")
        try:
            await self._get_client().models.list()
            return ProviderStatus(name=self.name, enabled=True, healthy=True)
        except Exception as err:
            return ProviderStatus(
                name=self.name, enabled=True, healthy=False, detail=f"{type(err).__name__}: {err}"
            )

    async def synthesize_to_bytes(
        self,
        text: str,
        *,
        voice: str | None = None,
        model: str | None = None,
    ) -> bytes:
        if not text.strip():
            return b""
        client = self._get_client()
        try:
            resp = await client.audio.speech.create(
                model=model or self._tts.model,
                voice=voice or self._tts.voice,
                input=text,
                response_format=self._tts.format,
                speed=self._tts.playback_speed,
            )
            # openai>=1.x returns an HttpxBinaryResponseContent
            data = await resp.aread() if hasattr(resp, "aread") else resp.read()
            return data
        except APIError as err:
            raise TTSProviderError(f"OpenAI TTS error: {err}") from err

    async def synthesize_stream(
        self,
        text: str,
        *,
        voice: str | None = None,
        model: str | None = None,
    ) -> AsyncIterator[bytes]:
        if not text.strip():
            return
        client = self._get_client()
        try:
            async with client.audio.speech.with_streaming_response.create(
                model=model or self._tts.model,
                voice=voice or self._tts.voice,
                input=text,
                response_format=self._tts.format,
                speed=self._tts.playback_speed,
            ) as resp:
                async for chunk in resp.iter_bytes():
                    if chunk:
                        yield chunk
        except APIError as err:
            raise TTSProviderError(f"OpenAI TTS streaming error: {err}") from err
