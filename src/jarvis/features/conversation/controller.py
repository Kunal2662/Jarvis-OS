"""Conversation controller — Qt-facing bridge to :class:`ChatService`
and, since M10's Conversational Orchestration Routing pass (see
``docs/ORCHESTRATION_ROUTING_LOGIC_CONTRACT.md``), optionally
:class:`~jarvis.agents.orchestrator.AgentOrchestrator`.

This is what the UI talks to. It:

* exposes Qt signals (``stream_started``, ``token``, ``stream_finished``,
  ``error``) that widgets can connect to;
* schedules the async streaming call on the running qasync loop;
* keeps track of the *active conversation id*;
* decides, per ``AgentSettings.conversation_routing``, which backend a
  call to :meth:`send` actually reaches -- the one place this decision
  is made, per the Logic Contract's own "the DI composition root is the
  only place the mode is read" acceptance criterion. ``ChatService``
  and ``AgentOrchestrator`` are both unmodified by this: this class is
  the composition-layer seam between them, not a change to either.

The controller **owns** no UI state — widgets subscribe via signals.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal, Slot

from jarvis.core.logging.logger import get_logger
from jarvis.utils.async_utils import fire_and_forget

if TYPE_CHECKING:
    from jarvis.core.config.settings import Settings
    from jarvis.core.interfaces.agent import IAgentOrchestrator
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
        settings: Settings,
        agent_orchestrator: IAgentOrchestrator | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        if settings.agent.conversation_routing == "orchestrator" and agent_orchestrator is None:
            # Fail at construction, naming the problem, not the first time
            # a user sends a message -- the same discipline this
            # codebase's connector factories already apply to a missing
            # required config key.
            raise ValueError(
                "AgentSettings.conversation_routing='orchestrator' requires an "
                "agent_orchestrator to be provided to ConversationController."
            )
        self._chat = chat_service
        self._conversations = conversation_service
        self._settings = settings
        self._orchestrator = agent_orchestrator
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

    async def _ensure_active_conversation(self, prompt: str) -> str:
        if self._active_id is None:
            summary = await self._conversations.create(title=prompt[:64])
            self._active_id = summary.id
            self.conversation_selected.emit(summary.id)
            await self._refresh_conversations()
        conv_id = self._active_id
        assert conv_id is not None
        return conv_id

    def _use_orchestrator(self) -> bool:
        """The one place `AgentSettings.conversation_routing` is read
        (Logic Contract AC6). ``"legacy"`` and ``"hybrid"`` both default
        to `ChatService` here -- `"hybrid"` exists so both paths are
        reachable through this controller, not so an ordinary `send()`
        call becomes non-deterministic."""
        return self._settings.agent.conversation_routing == "orchestrator"

    async def _stream(self, prompt: str) -> None:
        if self._use_orchestrator():
            await self._stream_via_orchestrator(prompt)
        else:
            await self._stream_via_chat_service(prompt)

    async def _stream_via_chat_service(self, prompt: str) -> None:
        conv_id = await self._ensure_active_conversation(prompt)
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

    async def _stream_via_orchestrator(self, prompt: str) -> None:
        """`AgentOrchestrator` has no `ConversationService` dependency
        of its own -- its LangGraph checkpointer tracks *agent* state
        keyed by `thread_id`, a different thing from chat history. This
        method is what makes the two ids the same string for one
        conversation (mirroring `SessionManager`'s own established
        pattern, per the Logic Contract) and persists the exchange
        through `ConversationService` itself, so the orchestrator path's
        persisted shape matches `ChatService`'s own exactly (Logic
        Contract AC4)."""
        assert self._orchestrator is not None  # send() only calls this when configured
        from jarvis.core.interfaces.agent import AgentRequest

        conv_id = await self._ensure_active_conversation(prompt)
        self.stream_started.emit(conv_id)
        await self._conversations.append(conv_id, "user", prompt)

        parts: list[str] = []
        try:
            request = AgentRequest(prompt=prompt, thread_id=conv_id)
            async for tok in self._orchestrator.stream(request):
                parts.append(tok)
                self.token.emit(tok)
        except Exception as err:
            _logger.exception("Orchestrator streaming failed.")
            self.error.emit(str(err))
            return
        finally:
            answer = "".join(parts).strip()
            if answer:
                await self._conversations.append(conv_id, "assistant", answer)
            self.stream_finished.emit(answer)
            await self._refresh_conversations()
