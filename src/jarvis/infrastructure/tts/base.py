"""Shared base class for TTS provider adapters.

Concrete adapters only need to implement :meth:`health` and
:meth:`synthesize_to_bytes`. ``synthesize_to_file`` and the default
``synthesize_stream`` (single-chunk) are provided here so every adapter
behaves identically for callers that don't care about incremental
streaming. Providers with genuine incremental synthesis (Edge TTS,
ElevenLabs) override ``synthesize_stream`` directly and set
``supports_streaming = True``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from jarvis.core.interfaces.tts_provider import ITTSProvider
from jarvis.core.types import ProviderStatus


class TTSProviderBase(ITTSProvider):
    """Common scaffolding shared by every TTS adapter."""

    name: str = "base_tts"
    supports_streaming: bool = False

    async def health(self) -> ProviderStatus:  # pragma: no cover - overridden
        raise NotImplementedError

    async def synthesize_to_bytes(
        self,
        text: str,
        *,
        voice: str | None = None,
        model: str | None = None,
    ) -> bytes:  # pragma: no cover - overridden
        raise NotImplementedError

    async def synthesize_to_file(
        self,
        text: str,
        output_path: Path,
        *,
        voice: str | None = None,
        model: str | None = None,
    ) -> Path:
        data = await self.synthesize_to_bytes(text, voice=voice, model=model)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(data)
        return output_path

    async def synthesize_stream(
        self,
        text: str,
        *,
        voice: str | None = None,
        model: str | None = None,
    ) -> AsyncIterator[bytes]:
        """Default: synthesize the whole utterance, then yield it once.

        This keeps every provider usable by the streaming voice pipeline
        even before it has "real" incremental synthesis — the pipeline
        just won't get a latency win from providers that fall back to
        this implementation.
        """
        data = await self.synthesize_to_bytes(text, voice=voice, model=model)
        if data:
            yield data
