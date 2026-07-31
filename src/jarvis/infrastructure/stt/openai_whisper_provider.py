"""Cloud Whisper STT via the OpenAI HTTP API (``/v1/audio/transcriptions``)."""

from __future__ import annotations

import io
import wave
from pathlib import Path
from typing import TYPE_CHECKING

from openai import APIError, AsyncOpenAI

from jarvis.core.exceptions import STTProviderError
from jarvis.core.interfaces.stt_provider import ISTTProvider
from jarvis.core.types import ProviderStatus

if TYPE_CHECKING:
    from jarvis.core.config.settings import OpenAISettings, STTSettings


class OpenAIWhisperSTTProvider(ISTTProvider):
    name: str = "openai_whisper"

    def __init__(self, stt: STTSettings, openai: OpenAISettings) -> None:
        self._stt = stt
        self._openai = openai
        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            key = self._openai.api_key.get_secret_value()
            if not key:
                raise STTProviderError(
                    "OpenAI Whisper selected but JARVIS_OPENAI_API_KEY is empty."
                )
            self._client = AsyncOpenAI(
                api_key=key,
                base_url=self._openai.base_url or None,
                organization=self._openai.org or None,
                max_retries=2,
            )
        return self._client

    async def health(self) -> ProviderStatus:
        if not self._stt.enabled:
            return ProviderStatus(name=self.name, enabled=False, healthy=False, detail="disabled")
        try:
            await self._get_client().models.list()
            return ProviderStatus(name=self.name, enabled=True, healthy=True)
        except Exception as err:
            return ProviderStatus(
                name=self.name, enabled=True, healthy=False, detail=f"{type(err).__name__}: {err}"
            )

    async def transcribe_file(self, audio_path: Path, *, language: str | None = None) -> str:
        client = self._get_client()
        try:
            with audio_path.open("rb") as fh:
                resp = await client.audio.transcriptions.create(
                    model="whisper-1",
                    file=fh,
                    language=language or self._stt.language,
                )
            return (resp.text or "").strip()
        except APIError as err:
            raise STTProviderError(f"OpenAI Whisper error: {err}") from err

    async def transcribe_bytes(
        self,
        audio: bytes,
        *,
        sample_rate: int,
        language: str | None = None,
    ) -> str:
        # Pack raw PCM into an in-memory WAV so we don't touch disk.
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio)
        buf.seek(0)
        buf.name = "audio.wav"  # openai SDK inspects .name for content-type

        client = self._get_client()
        try:
            resp = await client.audio.transcriptions.create(
                model="whisper-1",
                file=buf,
                language=language or self._stt.language,
            )
            return (resp.text or "").strip()
        except APIError as err:
            raise STTProviderError(f"OpenAI Whisper error: {err}") from err
