"""Microphone recorder backed by ``sounddevice`` + ``numpy``.

Recording happens on a background thread that ``sounddevice`` manages
internally; we pull frames through a queue and expose them either as one
buffered chunk (``start`` → ``stop``) or as an async stream (``stream``).

All ``sounddevice`` / ``numpy`` imports are deferred to first use so this
module can be imported on Linux CI where PortAudio isn't installed.
"""

from __future__ import annotations

import asyncio
import queue
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from jarvis.core.exceptions import InfrastructureError
from jarvis.core.interfaces.audio import AudioChunk, IAudioRecorder
from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.core.config.settings import STTSettings, VoiceSettings

_logger = get_logger("jarvis.infrastructure.audio.recorder")


class SoundDeviceRecorder(IAudioRecorder):
    """Records 16-bit PCM mono at the STT-configured sample rate."""

    name: str = "sounddevice"

    def __init__(self, stt: STTSettings, voice: VoiceSettings) -> None:
        self._stt = stt
        self._voice = voice
        self._q: queue.Queue[bytes] = queue.Queue()
        self._stream = None  # sd.RawInputStream
        self._recording: bool = False

    # ------------------------------------------------------------------
    async def health(self) -> bool:
        try:
            self._sd()
            return True
        except Exception:
            return False

    async def start(self) -> None:
        if self._recording:
            return
        sd = self._sd()
        # Drain any stale frames.
        while not self._q.empty():
            self._q.get_nowait()

        def _callback(indata, _frames, _time, status) -> None:
            if status:
                _logger.debug("sounddevice status: {}", status)
            self._q.put(bytes(indata))

        device = self._voice.input_device or None
        self._stream = sd.RawInputStream(
            samplerate=self._stt.sample_rate,
            channels=1,
            dtype="int16",
            blocksize=int(self._stt.sample_rate * 0.05),  # 50 ms frames
            device=device,
            callback=_callback,
        )
        self._stream.start()
        self._recording = True
        _logger.info(
            "Recording started (sr={} Hz, device={}).",
            self._stt.sample_rate,
            device or "default",
        )

    async def stop(self) -> AudioChunk:
        if not self._recording or self._stream is None:
            return AudioChunk(b"", self._stt.sample_rate)
        self._stream.stop()
        self._stream.close()
        self._stream = None
        self._recording = False
        parts: list[bytes] = []
        while not self._q.empty():
            parts.append(self._q.get_nowait())
        data = b"".join(parts)
        _logger.info("Recording stopped ({} bytes captured).", len(data))
        return AudioChunk(data, self._stt.sample_rate)

    async def stream(self) -> AsyncIterator[AudioChunk]:
        await self.start()
        try:
            loop = asyncio.get_running_loop()
            while self._recording:
                frame = await loop.run_in_executor(None, self._q.get)
                yield AudioChunk(frame, self._stt.sample_rate)
        finally:
            if self._recording:
                await self.stop()

    # ------------------------------------------------------------------
    def _sd(self):
        try:
            import sounddevice as sd
        except OSError as err:
            raise InfrastructureError(
                "PortAudio not available. On Windows this ships in the "
                "sounddevice wheel; on Linux install libportaudio2."
            ) from err
        return sd
