"""Text-to-speech provider port.

Every concrete adapter (Piper, Kokoro, Edge TTS, ElevenLabs, OpenAI, and
any future provider) implements this single interface. No provider-
specific branching may exist outside :mod:`jarvis.infrastructure.tts` —
the rest of the app (services, UI) only ever talks to ``ITTSProvider``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Protocol, runtime_checkable

from jarvis.core.types import ProviderStatus


@runtime_checkable
class ITTSProvider(Protocol):
    """Abstract TTS provider."""

    name: str

    #: True when :meth:`synthesize_stream` yields audio incrementally
    #: (chunk-by-chunk) instead of buffering the whole utterance first.
    #: The voice pipeline uses this to decide whether it can start
    #: playback before synthesis has fully finished.
    supports_streaming: bool

    async def health(self) -> ProviderStatus: ...

    async def synthesize_to_file(
        self,
        text: str,
        output_path: Path,
        *,
        voice: str | None = None,
        model: str | None = None,
    ) -> Path: ...

    async def synthesize_to_bytes(
        self,
        text: str,
        *,
        voice: str | None = None,
        model: str | None = None,
    ) -> bytes: ...

    def synthesize_stream(
        self,
        text: str,
        *,
        voice: str | None = None,
        model: str | None = None,
    ) -> AsyncIterator[bytes]:
        """Yield playable audio chunks as they become available.

        Providers without true incremental synthesis may implement this
        by yielding the full buffer produced by :meth:`synthesize_to_bytes`
        as a single chunk — callers must not assume low latency from the
        mere presence of this method, only from ``supports_streaming``.
        """
        ...
