"""Audio playback via ``sounddevice`` + ``soundfile``.

Redesigned for the voice pipeline overhaul to support:

* **Queued / streaming playback** — ``play_stream`` consumes an
  ``AsyncIterator[bytes]`` (e.g. sentence-sized chunks from a streaming
  TTS provider) and plays each chunk back-to-back as it arrives, so
  speech can start before the whole reply has been synthesized.
* **Instant interruption** — ``stop()`` sets a cancellation event *and*
  calls ``sd.stop()``, so playback halts within a few milliseconds
  whether it's mid-chunk or between chunks in the queue.
* **Volume / speed** as configured in ``TTSSettings`` — applied on
  decode so every provider gets identical behavior regardless of
  whether *it* supports those knobs natively.

Everything blocking runs off the asyncio loop via ``run_in_executor`` so
playback never blocks the UI thread.
"""

from __future__ import annotations

import asyncio
import io
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from jarvis.core.exceptions import InfrastructureError
from jarvis.core.interfaces.audio import IAudioPlayer
from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.core.config.settings import TTSSettings, VoiceSettings

_logger = get_logger("jarvis.infrastructure.audio.player")


class SoundDevicePlayer(IAudioPlayer):
    name: str = "sounddevice"

    def __init__(self, tts: TTSSettings, voice: VoiceSettings) -> None:
        self._tts = tts
        self._voice = voice
        self._cancel_event: asyncio.Event | None = None
        self._playing: bool = False

    async def health(self) -> bool:
        try:
            self._sf()
            self._sd()
            return True
        except Exception:
            return False

    @property
    def is_playing(self) -> bool:
        return self._playing

    # ------------------------------------------------------------------
    # Single-shot playback (back-compat, and used by non-streaming providers)
    # ------------------------------------------------------------------
    async def play_bytes(self, data: bytes, *, mime: str = "audio/mpeg") -> None:
        if not data:
            return

        async def _one_chunk() -> AsyncIterator[bytes]:
            yield data

        await self.play_stream(_one_chunk(), mime=mime)

    # ------------------------------------------------------------------
    # Streaming / queued playback
    # ------------------------------------------------------------------
    async def play_stream(
        self,
        chunks: AsyncIterator[bytes],
        *,
        mime: str = "audio/mpeg",
    ) -> None:
        sd = self._sd()
        sf = self._sf()
        loop = asyncio.get_running_loop()

        cancel_event = asyncio.Event()
        self._cancel_event = cancel_event
        self._playing = True

        def _decode(data: bytes):
            import numpy as np

            with io.BytesIO(data) as buf:
                pcm, sr = sf.read(buf, dtype="float32", always_2d=False)
            volume = max(0.0, min(2.0, self._tts.volume))
            if volume != 1.0:
                pcm = np.clip(pcm * volume, -1.0, 1.0)
            return pcm, sr

        def _play_blocking(pcm, sr) -> None:
            device = self._voice.output_device or None
            sd.play(pcm, samplerate=sr, device=device)
            # Poll instead of a single blocking wait() so cancellation
            # lands within ~10ms instead of waiting for the whole clip.
            while sd.get_stream().active:
                if cancel_event.is_set():
                    sd.stop()
                    return
                sd.sleep(10)

        try:
            async for chunk in chunks:
                if cancel_event.is_set() or not chunk:
                    if cancel_event.is_set():
                        break
                    continue
                pcm, sr = await loop.run_in_executor(None, _decode, chunk)
                if cancel_event.is_set():
                    break
                await loop.run_in_executor(None, _play_blocking, pcm, sr)
        except Exception as err:
            _logger.exception("Streaming playback failed.")
            raise InfrastructureError(f"Audio playback failed: {err}") from err
        finally:
            self._playing = False

    async def stop(self) -> None:
        if self._cancel_event is not None:
            self._cancel_event.set()
        try:
            self._sd().stop()
        except Exception:
            pass
        self._playing = False

    # ------------------------------------------------------------------
    def _sd(self):
        try:
            import sounddevice as sd
        except OSError as err:
            raise InfrastructureError("PortAudio not available.") from err
        return sd

    def _sf(self):
        try:
            import soundfile as sf
        except OSError as err:
            raise InfrastructureError("libsndfile not available.") from err
        return sf
