"""Local Whisper STT adapter using the ``openai-whisper`` package.

The model is loaded lazily on first use and cached in memory. All I/O
happens on a thread pool so recording + UI + streaming stay responsive.
"""

from __future__ import annotations

import asyncio
import wave
from pathlib import Path
from typing import TYPE_CHECKING

from jarvis.core.exceptions import STTProviderError
from jarvis.core.interfaces.stt_provider import ISTTProvider
from jarvis.core.logging.logger import get_logger
from jarvis.core.types import ProviderStatus

if TYPE_CHECKING:
    from jarvis.core.config.settings import STTSettings

_logger = get_logger("jarvis.infrastructure.stt.whisper_local")


class WhisperLocalSTTProvider(ISTTProvider):
    """Local Whisper (``openai-whisper``) — CPU or CUDA."""

    name: str = "whisper_local"

    def __init__(self, settings: STTSettings) -> None:
        self._settings = settings
        self._model = None

    # ------------------------------------------------------------------
    async def health(self) -> ProviderStatus:
        if not self._settings.enabled:
            return ProviderStatus(name=self.name, enabled=False, healthy=False, detail="disabled")
        try:
            self._import_whisper()
            return ProviderStatus(name=self.name, enabled=True, healthy=True)
        except STTProviderError as err:
            return ProviderStatus(name=self.name, enabled=True, healthy=False, detail=str(err))

    async def transcribe_file(self, audio_path: Path, *, language: str | None = None) -> str:
        model = await self._get_model()

        def _run() -> str:
            result = model.transcribe(
                str(audio_path),
                language=language or self._settings.language,
                fp16=False,
            )
            return (result.get("text") or "").strip()

        try:
            return await asyncio.get_running_loop().run_in_executor(None, _run)
        except Exception as err:
            raise STTProviderError(f"Whisper transcription failed: {err}") from err

    async def transcribe_bytes(
        self,
        audio: bytes,
        *,
        sample_rate: int,
        language: str | None = None,
    ) -> str:
        if not audio:
            return ""
        # Whisper prefers a WAV on disk; we cheat with an in-memory WAV
        # written to a tempfile so we get the fastest path through librosa.
        import tempfile

        def _write_wav() -> Path:
            fd, path = tempfile.mkstemp(prefix="jarvis-stt-", suffix=".wav")
            with wave.open(path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(audio)
            import os

            os.close(fd)
            return Path(path)

        path = await asyncio.get_running_loop().run_in_executor(None, _write_wav)
        try:
            return await self.transcribe_file(path, language=language)
        finally:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

    async def preload(self) -> None:
        """Warm the model eagerly (Milestone 3.1 perf item — was previously
        loaded lazily on first call only). Safe to call repeatedly; a
        loaded model is reused. Raises :class:`STTProviderError` on
        failure so the caller can decide whether that's fatal.
        """
        await self._get_model()

    # ------------------------------------------------------------------
    async def _get_model(self):
        if self._model is not None:
            return self._model
        whisper = self._import_whisper()

        def _load():
            device = None if self._settings.device == "auto" else self._settings.device
            return whisper.load_model(self._settings.model, device=device)

        try:
            self._model = await asyncio.get_running_loop().run_in_executor(None, _load)
            _logger.info("Loaded Whisper model '{}'.", self._settings.model)
            return self._model
        except Exception as err:
            raise STTProviderError(f"Cannot load Whisper model: {err}") from err

    @staticmethod
    def _import_whisper():
        try:
            import whisper

            return whisper
        except ImportError as err:  # pragma: no cover
            raise STTProviderError(
                "openai-whisper not installed. Add `openai-whisper` to requirements.txt."
            ) from err
