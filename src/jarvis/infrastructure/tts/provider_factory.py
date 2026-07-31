"""TTS provider factory — a pluggable registry keyed by :class:`TTSBackend`.

Design
------
Instead of an ``if/elif`` chain, backends are registered in ``_REGISTRY``
as ``(backend, builder)`` pairs. Adding a brand-new future provider means:

1. Add a value to :class:`jarvis.core.types.TTSBackend`.
2. Write the adapter (implements :class:`ITTSProvider`, e.g. via
   :class:`jarvis.infrastructure.tts.base.TTSProviderBase`).
3. Call :func:`register_tts_provider` with the new backend + a builder
   function.

No other file — not the UI, not the voice service — needs to change.
Builders import their adapter module lazily so selecting one backend
never requires every other backend's optional dependency to be
installed.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from jarvis.core.exceptions import ConfigError
from jarvis.core.interfaces.tts_provider import ITTSProvider
from jarvis.core.types import TTSBackend

if TYPE_CHECKING:
    from jarvis.core.config.settings import Settings

Builder = Callable[["Settings"], ITTSProvider]

_REGISTRY: dict[TTSBackend, Builder] = {}


def register_tts_provider(backend: TTSBackend, builder: Builder) -> None:
    """Register (or override) the builder used for *backend*."""
    _REGISTRY[backend] = builder


def _build_piper(settings: Settings) -> ITTSProvider:
    from jarvis.infrastructure.tts.piper_provider import PiperTTSProvider

    return PiperTTSProvider(settings.tts, settings.piper)


def _build_kokoro(settings: Settings) -> ITTSProvider:
    from jarvis.infrastructure.tts.kokoro_provider import KokoroTTSProvider

    return KokoroTTSProvider(settings.tts, settings.kokoro)


def _build_edge_tts(settings: Settings) -> ITTSProvider:
    from jarvis.infrastructure.tts.edge_tts_provider import EdgeTTSProvider

    return EdgeTTSProvider(settings.tts, settings.edge_tts)


def _build_elevenlabs(settings: Settings) -> ITTSProvider:
    from jarvis.infrastructure.tts.elevenlabs_provider import ElevenLabsTTSProvider

    return ElevenLabsTTSProvider(settings.tts, settings.elevenlabs)


def _build_openai(settings: Settings) -> ITTSProvider:
    from jarvis.infrastructure.tts.openai_tts_provider import OpenAITTSProvider

    return OpenAITTSProvider(settings.tts, settings.openai)


register_tts_provider(TTSBackend.PIPER, _build_piper)
register_tts_provider(TTSBackend.KOKORO, _build_kokoro)
register_tts_provider(TTSBackend.EDGE_TTS, _build_edge_tts)
register_tts_provider(TTSBackend.ELEVENLABS, _build_elevenlabs)
register_tts_provider(TTSBackend.OPENAI, _build_openai)


def build_tts_provider(settings: Settings) -> ITTSProvider:
    """Build the configured TTS provider from ``settings.tts.backend``."""
    backend = settings.tts.backend
    builder = _REGISTRY.get(backend)
    if builder is None:
        raise ConfigError(
            f"Unknown TTS backend: {backend!r}. Registered backends: "
            f"{[b.value for b in _REGISTRY]}"
        )
    return builder(settings)
