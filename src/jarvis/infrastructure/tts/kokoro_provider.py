"""Kokoro adapter — optional, higher-quality offline TTS.

Uses the ``kokoro`` / ``kokoro-onnx`` Python package. Import is deferred
so the app still runs (and every other provider still works) when the
package isn't installed; only selecting this backend requires it.
"""

from __future__ import annotations

import asyncio
import io
from typing import TYPE_CHECKING

from jarvis.core.exceptions import TTSProviderError
from jarvis.core.logging.logger import get_logger
from jarvis.core.types import ProviderStatus
from jarvis.infrastructure.tts.base import TTSProviderBase

if TYPE_CHECKING:
    from jarvis.core.config.settings import KokoroSettings, TTSSettings

_logger = get_logger("jarvis.infrastructure.tts.kokoro")


class KokoroTTSProvider(TTSProviderBase):
    """Optional offline TTS — more natural prosody than Piper, heavier model."""

    name: str = "kokoro"
    supports_streaming: bool = False

    def __init__(self, tts: TTSSettings, kokoro: KokoroSettings) -> None:
        self._tts = tts
        self._kokoro = kokoro
        self._pipeline = None

    def _load(self):
        if self._pipeline is not None:
            return self._pipeline
        try:
            from kokoro_onnx import Kokoro
        except ImportError as err:
            raise TTSProviderError(
                "Kokoro TTS selected but the 'kokoro-onnx' package isn't "
                "installed. Run `pip install kokoro-onnx`, or switch TTS "
                "provider in Settings."
            ) from err
        model_path = self._kokoro.model_path or "kokoro-v0_19.onnx"
        self._pipeline = Kokoro(model_path, "voices.bin")
        return self._pipeline

    async def health(self) -> ProviderStatus:
        if not self._tts.enabled or not self._kokoro.enabled:
            return ProviderStatus(name=self.name, enabled=False, healthy=False, detail="disabled")
        try:
            await asyncio.get_running_loop().run_in_executor(None, self._load)
            return ProviderStatus(name=self.name, enabled=True, healthy=True)
        except TTSProviderError as err:
            return ProviderStatus(name=self.name, enabled=True, healthy=False, detail=str(err))

    async def synthesize_to_bytes(
        self,
        text: str,
        *,
        voice: str | None = None,
        model: str | None = None,
    ) -> bytes:
        if not text.strip():
            return b""

        def _synth() -> bytes:
            import numpy as np
            import soundfile as sf

            pipeline = self._load()
            samples, sample_rate = pipeline.create(
                text,
                voice=voice or self._kokoro.voice,
                lang=self._kokoro.language,
            )
            buf = io.BytesIO()
            sf.write(buf, np.asarray(samples), sample_rate, format="WAV")
            return buf.getvalue()

        try:
            return await asyncio.get_running_loop().run_in_executor(None, _synth)
        except TTSProviderError:
            raise
        except Exception as err:
            raise TTSProviderError(f"Kokoro synthesis failed: {err}") from err
