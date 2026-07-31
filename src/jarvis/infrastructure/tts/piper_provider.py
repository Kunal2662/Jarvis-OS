"""Piper adapter — the primary, fully-offline TTS backend.

Piper (https://github.com/rhasspy/piper) ships either as a standalone
native binary or as the ``piper-tts`` Python package. We shell out to the
binary because that's the lowest-friction install path across Windows/
macOS/Linux and keeps this adapter dependency-free at import time — the
binary is only required the first time someone actually speaks.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from jarvis.core.exceptions import TTSProviderError
from jarvis.core.logging.logger import get_logger
from jarvis.core.types import ProviderStatus
from jarvis.infrastructure.tts.base import TTSProviderBase

if TYPE_CHECKING:
    from jarvis.core.config.settings import PiperSettings, TTSSettings

_logger = get_logger("jarvis.infrastructure.tts.piper")


class PiperTTSProvider(TTSProviderBase):
    """Offline, low-latency, no API key, no network required."""

    name: str = "piper"
    supports_streaming: bool = False  # Piper renders a full WAV per call

    def __init__(self, tts: TTSSettings, piper: PiperSettings) -> None:
        self._tts = tts
        self._piper = piper

    def _executable(self) -> str:
        exe = self._piper.executable or "piper"
        path = shutil.which(exe)
        if path is None and not Path(exe).exists():
            raise TTSProviderError(
                f"Piper executable {exe!r} not found on PATH. Install it "
                "from https://github.com/rhasspy/piper/releases and set "
                "JARVIS_PIPER_EXECUTABLE to its path, or switch TTS "
                "provider in Settings."
            )
        return path or exe

    async def health(self) -> ProviderStatus:
        if not self._tts.enabled or not self._piper.enabled:
            return ProviderStatus(name=self.name, enabled=False, healthy=False, detail="disabled")
        try:
            self._executable()
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
        exe = self._executable()
        args = [exe, "--output_file", "-"]
        model_name = model or voice or self._piper.voice
        if self._piper.model_path:
            args += ["--model", self._piper.model_path]
        elif model_name:
            args += ["--model", model_name]

        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate(text.encode("utf-8"))
        except FileNotFoundError as err:
            raise TTSProviderError(f"Piper executable failed to launch: {err}") from err
        except OSError as err:
            raise TTSProviderError(f"Piper process error: {err}") from err

        if proc.returncode != 0:
            raise TTSProviderError(
                f"Piper exited with code {proc.returncode}: "
                f"{stderr.decode('utf-8', errors='replace')[:500]}"
            )
        if not stdout:
            raise TTSProviderError("Piper produced no audio output.")
        return stdout
