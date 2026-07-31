"""Voice ViewModel (MVVM).

Bridges :class:`VoiceService` (the framework-free state machine) to Qt
signals so widgets (PTT button, voice orb, status chip) stay purely
presentational. Also owns the thin orchestration that only makes sense
at the UI layer:

* Feeding LLM tokens into ``speak_stream`` sentence-by-sentence as they
  arrive, instead of waiting for the full reply (perceived-latency win).
* Auto-resuming listening after JARVIS finishes speaking, when
  "continuous conversation" mode is enabled.
* Starting/stopping wake-word detection.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal, Slot

from jarvis.core.logging.logger import get_logger
from jarvis.core.types import VoiceState
from jarvis.utils.async_utils import fire_and_forget

if TYPE_CHECKING:
    from jarvis.core.config.settings import Settings
    from jarvis.services.voice_service import VoiceService

_logger = get_logger("jarvis.features.voice")


class VoiceController(QObject):
    """ViewModel exposed to the UI."""

    listening_started = Signal()
    listening_stopped = Signal()
    transcribed = Signal(str)  # final STT text
    speaking_started = Signal()
    speaking_stopped = Signal()
    state_changed = Signal(str, str)  # (VoiceState.value, detail)
    interrupted = Signal()
    error = Signal(str)

    def __init__(
        self,
        voice_service: VoiceService,
        settings: Settings,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = voice_service
        self._settings = settings
        self._speaking: bool = False
        self._token_queue: asyncio.Queue[str | None] | None = None
        self._speak_stream_task: asyncio.Task | None = None
        self._auto_relisten: bool = False

        self._service.on_state_changed(self._on_service_state_changed)

    # ------------------------------------------------------------------
    # Slots — recording
    # ------------------------------------------------------------------
    @Slot()
    def press_to_talk(self) -> None:
        fire_and_forget(self._press_to_talk())

    @Slot()
    def release_to_talk(self) -> None:
        fire_and_forget(self._release_to_talk())

    @Slot()
    def toggle_listening(self) -> None:
        if self._service.is_listening:
            fire_and_forget(self._release_to_talk())
        else:
            fire_and_forget(self._press_to_talk())

    # ------------------------------------------------------------------
    # Slots — speaking (single-shot, back-compat)
    # ------------------------------------------------------------------
    @Slot(str)
    def speak(self, text: str) -> None:
        if not text.strip():
            return
        fire_and_forget(self._speak(text))

    @Slot()
    def stop_speaking(self) -> None:
        fire_and_forget(self._service.stop_speaking())

    # ------------------------------------------------------------------
    # Slots — incremental speech driven by an LLM token stream
    # ------------------------------------------------------------------
    @Slot(str)
    def on_llm_stream_started(self, _conversation_id: str = "") -> None:
        """Call when a new assistant reply starts streaming."""
        if not self._settings.tts.speak_replies:
            return
        self._token_queue = asyncio.Queue()

        async def _consume() -> AsyncIterator[str]:
            assert self._token_queue is not None
            while True:
                item = await self._token_queue.get()
                if item is None:
                    return
                yield item

        self._speak_stream_task = fire_and_forget(self._speak_stream(_consume()))

    @Slot(str)
    def on_llm_token(self, token: str) -> None:
        if self._token_queue is not None:
            self._token_queue.put_nowait(token)

    @Slot(str)
    def on_llm_stream_finished(self, _full_text: str = "") -> None:
        if self._token_queue is not None:
            self._token_queue.put_nowait(None)
            self._token_queue = None

    # ------------------------------------------------------------------
    # Slots — continuous conversation / wake word
    # ------------------------------------------------------------------
    @Slot(bool)
    def set_continuous_conversation(self, enabled: bool) -> None:
        self._auto_relisten = enabled

    @Slot()
    def start_wake_word(self) -> None:
        fire_and_forget(self._service.start_wake_word(self._on_wake_word))

    @Slot()
    def stop_wake_word(self) -> None:
        fire_and_forget(self._service.stop_wake_word())

    async def _on_wake_word(self, _keyword: str) -> None:
        if not self._service.is_listening and not self._speaking:
            await self._press_to_talk()

    # ------------------------------------------------------------------
    # Async helpers
    # ------------------------------------------------------------------
    async def _press_to_talk(self) -> None:
        try:
            await self._service.start_listening()
            self.listening_started.emit()
        except Exception as err:
            self.error.emit(str(err))

    async def _release_to_talk(self) -> None:
        try:
            text = await self._service.stop_listening()
            self.listening_stopped.emit()
            if text:
                self.transcribed.emit(text)
        except Exception as err:
            self.error.emit(str(err))

    async def _speak(self, text: str) -> None:
        if self._speaking:
            await self._service.stop_speaking()
        self._speaking = True
        self.speaking_started.emit()
        try:
            await self._service.speak(text)
        except Exception as err:
            self.error.emit(str(err))
        finally:
            self._speaking = False
            self.speaking_stopped.emit()
            await self._maybe_auto_relisten()

    async def _speak_stream(self, token_iter) -> None:
        self._speaking = True
        self.speaking_started.emit()
        try:
            await self._service.speak_stream(token_iter)
        except Exception as err:
            self.error.emit(str(err))
        finally:
            self._speaking = False
            self.speaking_stopped.emit()
            await self._maybe_auto_relisten()

    async def _maybe_auto_relisten(self) -> None:
        if self._auto_relisten and self._settings.voice.continuous_conversation:
            await self._press_to_talk()

    def _on_service_state_changed(self, state: VoiceState, detail: str) -> None:
        self.state_changed.emit(state.value, detail)
        if state is VoiceState.INTERRUPTED:
            self.interrupted.emit()
