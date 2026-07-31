"""Voice service — the framework-free voice conversation state machine.

This is the "VoiceController" from the audio/voice redesign spec (named
``VoiceService`` for backward compatibility with the DI container and
existing tests). It owns:

* The :class:`~jarvis.core.types.VoiceState` state machine.
* Listening (recorder → STT) — one-shot, same public API as before.
* Speaking, including **streaming TTS**: ``speak_stream`` starts playing
  audio for the first sentence while later sentences are still being
  synthesized (or even while the caller is still producing text, e.g.
  from a streaming LLM).
* **Interruption**: while speaking, a lightweight monitor listens for the
  user talking over JARVIS. The instant that happens, playback is
  cancelled and the service transitions ``SPEAKING -> INTERRUPTED ->
  LISTENING`` — no hotkey needed.
* **Wake word**: optional always-on keyword spotting that invokes a
  caller-supplied callback (typically "start listening") without the UI
  needing to know which engine (or none) is configured.

Everything here is Qt-free; :class:`jarvis.features.voice.controller.
VoiceController` is the thin Qt ViewModel that turns these into signals.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TYPE_CHECKING

from jarvis.core.exceptions import ServiceError
from jarvis.core.logging.logger import get_logger
from jarvis.core.types import VoiceState

if TYPE_CHECKING:
    from jarvis.core.config.settings import Settings
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.interfaces.audio import IAudioPlayer, IAudioRecorder
    from jarvis.core.interfaces.stt_provider import ISTTProvider
    from jarvis.core.interfaces.tts_provider import ITTSProvider
    from jarvis.core.interfaces.wake_word import IWakeWordDetector

_logger = get_logger("jarvis.services.voice")

# Sentence-boundary splitter used to chunk streaming LLM tokens into
# TTS-sized pieces without waiting for the whole reply.
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?:;\n])\s+")

StateListener = Callable[[VoiceState, str], "Awaitable[None] | None"]


def _rms(pcm16: bytes) -> float:
    """Normalized (0.0–1.0) RMS amplitude of 16-bit PCM audio."""
    if not pcm16:
        return 0.0
    import struct

    count = len(pcm16) // 2
    if count == 0:
        return 0.0
    samples = struct.unpack(f"<{count}h", pcm16[: count * 2])
    mean_sq = sum(s * s for s in samples) / count
    return (mean_sq**0.5) / 32768.0


class VoiceService:
    def __init__(
        self,
        stt: ISTTProvider,
        tts: ITTSProvider,
        recorder: IAudioRecorder,
        player: IAudioPlayer,
        settings: Settings,
        wake_word: IWakeWordDetector | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self._stt = stt
        self._tts = tts
        self._recorder = recorder
        self._player = player
        self._settings = settings
        self._wake_word = wake_word
        self._event_bus = event_bus

        self._recording: bool = False
        self._state: VoiceState = VoiceState.IDLE
        self._state_listeners: list[StateListener] = []
        self._barge_in_task: asyncio.Task | None = None
        self._interrupted: bool = False

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------
    @property
    def state(self) -> VoiceState:
        return self._state

    def on_state_changed(self, listener: StateListener) -> Callable[[], None]:
        """Subscribe to state transitions. Returns an unsubscribe callable."""
        self._state_listeners.append(listener)
        return lambda: (
            self._state_listeners.remove(listener) if listener in self._state_listeners else None
        )

    async def _set_state(self, state: VoiceState, detail: str = "") -> None:
        if state is self._state:
            return
        self._state = state
        _logger.debug("Voice state -> {} ({})", state.value, detail)
        for listener in list(self._state_listeners):
            try:
                result = listener(state, detail)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                _logger.exception("Voice state listener raised.")
        if self._event_bus is not None:
            from jarvis.core.events.events import VoiceStateChangedEvent

            await self._event_bus.publish(VoiceStateChangedEvent(state=state.value, detail=detail))

    # ------------------------------------------------------------------
    # Listening
    # ------------------------------------------------------------------
    async def start_listening(self) -> None:
        if not self._settings.stt.enabled:
            raise ServiceError("STT is disabled.")
        if self._recording:
            return
        await self._cancel_barge_in_monitor()
        await self._recorder.start()
        self._recording = True
        await self._set_state(VoiceState.LISTENING)

    async def stop_listening(self) -> str:
        """Stop recording and return the transcription (may be empty)."""
        if not self._recording:
            return ""
        chunk = await self._recorder.stop()
        self._recording = False
        if not chunk.data:
            await self._set_state(VoiceState.IDLE)
            return ""
        await self._set_state(VoiceState.THINKING, "transcribing")
        try:
            text = await self._stt.transcribe_bytes(
                chunk.data,
                sample_rate=chunk.sample_rate,
                language=self._settings.stt.language,
            )
        except Exception as err:
            _logger.exception("Transcription failed.")
            await self._set_state(VoiceState.ERROR, str(err))
            raise ServiceError(f"Transcription failed: {err}") from err
        if not text.strip():
            await self._set_state(VoiceState.IDLE)
        return text

    @property
    def is_listening(self) -> bool:
        return self._recording

    # ------------------------------------------------------------------
    # Speaking — single-shot (back-compat) and streaming
    # ------------------------------------------------------------------
    async def speak(self, text: str) -> None:
        if not self._settings.tts.enabled or not text.strip():
            return

        async def _one() -> AsyncIterator[str]:
            yield text

        await self.speak_stream(_one())

    async def speak_stream(self, text_chunks: AsyncIterator[str]) -> None:
        """Speak text as it arrives, sentence by sentence.

        ``text_chunks`` can be whole sentences, LLM tokens, or anything
        in between — chunks are buffered and re-split on sentence
        boundaries so TTS is never called on a half-formed word.
        """
        if not self._settings.tts.enabled:
            return

        self._interrupted = False
        await self._set_state(VoiceState.SPEAKING)
        await self._start_barge_in_monitor()

        buffer = ""
        try:
            async for piece in text_chunks:
                if self._interrupted:
                    break
                buffer += piece
                *complete, buffer = _SENTENCE_BOUNDARY.split(buffer) or [buffer]
                for sentence in complete:
                    if self._interrupted:
                        break
                    await self._speak_one(sentence)
            if not self._interrupted and buffer.strip():
                await self._speak_one(buffer)
        except Exception as err:
            _logger.exception("Speech synthesis/playback failed.")
            await self._set_state(VoiceState.ERROR, str(err))
            raise ServiceError(f"TTS failed: {err}") from err
        finally:
            await self._cancel_barge_in_monitor()
            if self._interrupted:
                await self._set_state(VoiceState.INTERRUPTED)
                await self._set_state(VoiceState.LISTENING)
            else:
                await self._set_state(VoiceState.IDLE)

    async def _speak_one(self, sentence: str) -> None:
        sentence = sentence.strip()
        if not sentence:
            return
        try:
            if getattr(self._tts, "supports_streaming", False):
                await self._player.play_stream(
                    self._tts.synthesize_stream(sentence),
                    mime=f"audio/{self._settings.tts.format}",
                )
            else:
                audio = await self._tts.synthesize_to_bytes(sentence)
                if audio:
                    await self._player.play_bytes(audio, mime=f"audio/{self._settings.tts.format}")
        except Exception as err:
            _logger.exception("TTS synthesis failed.")
            raise ServiceError(f"TTS synthesis failed: {err}") from err

    async def stop_speaking(self) -> None:
        await self._player.stop()

    # ------------------------------------------------------------------
    # Interruption (barge-in) — listens for the user talking over JARVIS
    # ------------------------------------------------------------------
    async def _start_barge_in_monitor(self) -> None:
        if not self._settings.voice.interrupt_enabled:
            return
        self._barge_in_task = asyncio.ensure_future(self._barge_in_loop())

    async def _cancel_barge_in_monitor(self) -> None:
        if self._barge_in_task is not None:
            self._barge_in_task.cancel()
            try:
                await self._barge_in_task
            except (asyncio.CancelledError, Exception):
                pass
            self._barge_in_task = None

    async def _barge_in_loop(self) -> None:
        threshold = self._settings.voice.interrupt_vad_threshold
        try:
            async for chunk in self._recorder.stream():
                if not getattr(self._player, "is_playing", True):
                    # Nothing playing (gap between sentences) — a stray
                    # noise here shouldn't cancel anything already done.
                    continue
                if _rms(chunk.data) >= threshold:
                    self._interrupted = True
                    await self._player.stop()
                    return
        except asyncio.CancelledError:
            raise
        except Exception:
            _logger.exception("Barge-in monitor failed; interruption disabled for this turn.")

    # ------------------------------------------------------------------
    # Wake word
    # ------------------------------------------------------------------
    async def start_wake_word(self, on_detected: Callable[[str], Awaitable[None] | None]) -> None:
        if self._wake_word is None or not self._settings.wake.enabled:
            return
        await self._wake_word.start(self._settings.wake.keywords, on_detected)

    async def stop_wake_word(self) -> None:
        if self._wake_word is not None:
            await self._wake_word.stop()
