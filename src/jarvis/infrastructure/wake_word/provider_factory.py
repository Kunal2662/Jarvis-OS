"""Wake-word detector factory — same pluggable-registry pattern as TTS/STT."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from jarvis.core.interfaces.wake_word import IWakeWordDetector
from jarvis.core.types import WakeWordEngine

if TYPE_CHECKING:
    from jarvis.core.config.settings import WakeWordSettings

Builder = Callable[["WakeWordSettings"], IWakeWordDetector]

_REGISTRY: dict[WakeWordEngine, Builder] = {}


def register_wake_word_detector(engine: WakeWordEngine, builder: Builder) -> None:
    _REGISTRY[engine] = builder


def _build_none(wake: WakeWordSettings) -> IWakeWordDetector:
    from jarvis.infrastructure.wake_word.noop_detector import NoopWakeWordDetector

    return NoopWakeWordDetector()


def _build_porcupine(wake: WakeWordSettings) -> IWakeWordDetector:
    from jarvis.infrastructure.wake_word.porcupine_detector import (
        PorcupineWakeWordDetector,
    )

    return PorcupineWakeWordDetector(wake)


def _build_openwakeword(wake: WakeWordSettings) -> IWakeWordDetector:
    from jarvis.infrastructure.wake_word.openwakeword_detector import (
        OpenWakeWordDetector,
    )

    return OpenWakeWordDetector(wake)


register_wake_word_detector(WakeWordEngine.NONE, _build_none)
register_wake_word_detector(WakeWordEngine.PORCUPINE, _build_porcupine)
register_wake_word_detector(WakeWordEngine.OPENWAKEWORD, _build_openwakeword)


def build_wake_word_detector(wake: WakeWordSettings) -> IWakeWordDetector:
    if not wake.enabled:
        from jarvis.infrastructure.wake_word.noop_detector import NoopWakeWordDetector

        return NoopWakeWordDetector()
    builder = _REGISTRY.get(wake.engine, _build_none)
    return builder(wake)
