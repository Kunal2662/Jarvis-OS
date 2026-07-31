"""STT provider factory — selects the concrete adapter from settings.

Central place to slot in new STT backends (Deepgram, AssemblyAI, …).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from jarvis.core.exceptions import ConfigError
from jarvis.core.interfaces.stt_provider import ISTTProvider
from jarvis.core.types import STTBackend

if TYPE_CHECKING:
    from jarvis.core.config.settings import OpenAISettings, STTSettings


def build_stt_provider(
    stt: STTSettings,
    openai: OpenAISettings,
) -> ISTTProvider:
    backend = stt.backend
    if backend is STTBackend.WHISPER_LOCAL:
        from jarvis.infrastructure.stt.whisper_local_provider import (
            WhisperLocalSTTProvider,
        )

        return WhisperLocalSTTProvider(stt)
    if backend is STTBackend.OPENAI_WHISPER:
        from jarvis.infrastructure.stt.openai_whisper_provider import (
            OpenAIWhisperSTTProvider,
        )

        return OpenAIWhisperSTTProvider(stt, openai)
    if backend is STTBackend.DEEPGRAM:
        raise ConfigError(
            "Deepgram STT is reserved for a future milestone; enable "
            "whisper_local or openai_whisper for now."
        )
    raise ConfigError(f"Unknown STT backend: {backend!r}")
