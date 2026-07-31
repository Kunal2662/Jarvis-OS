"""Audio I/O ports.

Separating recorder from player keeps the SRP intact and makes it trivial
to swap sounddevice for an alternative (PyAudio, WASAPI, WebRTC) later.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class AudioChunk:
    data: bytes  # raw PCM
    sample_rate: int
    channels: int = 1
    sample_width: int = 2  # bytes per sample (16-bit = 2)


@runtime_checkable
class IAudioRecorder(Protocol):
    """Captures audio from the default (or configured) input device."""

    name: str

    async def start(self) -> None: ...
    async def stop(self) -> AudioChunk: ...
    async def stream(self) -> AsyncIterator[AudioChunk]: ...
    async def health(self) -> bool: ...


@runtime_checkable
class IAudioPlayer(Protocol):
    """Plays audio bytes on the default (or configured) output device."""

    name: str

    async def play_bytes(self, data: bytes, *, mime: str = "audio/mpeg") -> None: ...

    async def play_stream(
        self,
        chunks: AsyncIterator[bytes],
        *,
        mime: str = "audio/mpeg",
    ) -> None:
        """Play a sequence of audio chunks back-to-back as they arrive.

        Implementations must check for cancellation (:meth:`stop`) between
        — and ideally during — chunks so interruption is near-instant even
        when the producer (streaming TTS) is still generating audio.
        """
        ...

    async def stop(self) -> None: ...
    async def health(self) -> bool: ...

    @property
    def is_playing(self) -> bool: ...
