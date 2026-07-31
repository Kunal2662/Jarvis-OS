"""Conversation controller — Qt-facing bridge to :class:`ChatService`.

This is what the UI talks to. It:

* exposes Qt signals (``stream_started``, ``token``, ``stream_finished``,
  ``error``) that widgets can connect to;
* schedules the async streaming call on the running qasync loop;
* keeps track of the *active conversation id*.

The controller **owns** no UI state — widgets subscribe via signals.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal, Slot

from jarvis.core.logging.logger import get_logger
from jarvis.utils.async_utils import fire_and_forget

if TYPE_CHECKING:
    from jarvis.services.chat_service import ChatService
    from jarvis.services.conversation_service import (
        ConversationService,
    )

_logger = get_logger("jarvis.features.conversation")


class ConversationController(QObject):
    # ---- Streaming lifecycle ----------------------------------------
    stream_started = Signal(str)  # emitted with conversation_id
    token = Signal(str)  # each token as it arrives
    stream_finished = Signal(str)  # full assistant text
    error = Signal(str)

    # ---- Conversation list --------------------------------------------
    conversations_loaded = Signal(list)  # list[ConversationSummary]
    conversation_selected = Signal(str)  # conversation_id

    def __init__(
        self,
        chat_service: ChatService,
        conversation_service: ConversationService,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._chat = chat_service
        self._conversations = conversation_service
        self._active_id: str | None = None
        self._task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Public slots
    # ------------------------------------------------------------------
    @Slot()
    def refresh_conversations(self) -> None:
        fire_and_forget(self._refresh_conversations())

    @Slot()
    def new_conversation(self) -> None:
        fire_and_forget(self._new_conversation())

    @Slot(str)
    def select_conversation(self, conversation_id: str) -> None:
        self._active_id = conversation_id
        self.conversation_selected.emit(conversation_id)

    @Slot(str)
    def send(self, prompt: str) -> None:
        if not prompt.strip():
            return
        if self._task and not self._task.done():
            _logger.warning("A stream is already in progress; ignoring send.")
            return
        self._task = fire_and_forget(self._stream(prompt))

    # ------------------------------------------------------------------
    # Async helpers
    # ------------------------------------------------------------------
    async def _refresh_conversations(self) -> None:
        try:
            convs = await self._conversations.list()
            self.conversations_loaded.emit(convs)
        except Exception as err:
            _logger.exception("Failed to load conversations.")
            self.error.emit(str(err))

    async def _new_conversation(self) -> None:
        try:
            summary = await self._conversations.create()
            self._active_id = summary.id
            self.conversation_selected.emit(summary.id)
            await self._refresh_conversations()
        except Exception as err:
            _logger.exception("Failed to create conversation.")
            self.error.emit(str(err))

    async def _stream(self, prompt: str) -> None:
        if self._active_id is None:
            summary = await self._conversations.create(title=prompt[:64])
            self._active_id = summary.id
            self.conversation_selected.emit(summary.id)
            await self._refresh_conversations()

        conv_id = self._active_id
        assert conv_id is not None
        self.stream_started.emit(conv_id)
        parts: list[str] = []
        try:
            async for tok in self._chat.stream(conv_id, prompt):
                parts.append(tok)
                self.token.emit(tok)
        except Exception as err:
            _logger.exception("Streaming failed.")
            self.error.emit(str(err))
            return
        finally:
            self.stream_finished.emit("".join(parts))
            await self._refresh_conversations()
