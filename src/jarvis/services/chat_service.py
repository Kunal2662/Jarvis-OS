"""Chat service — orchestrates LLM calls with persisted conversation history.

Milestone 1 responsibilities:

* Build the message list from the system prompt + persisted history + new
  user message.
* Stream tokens from the injected :class:`ILLMProvider`.
* Persist the completed assistant message once streaming ends.

Milestone 2 addition — :class:`IMemoryRecallHook` is injected so that
Milestone 3 can transparently start prepending relevant memories without
changing this service's public API. The default hook is a no-op.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from jarvis.core.exceptions import ServiceError
from jarvis.core.interfaces.memory import IMemoryRecallHook, NoopMemoryRecall
from jarvis.core.logging.logger import get_logger
from jarvis.core.types import ChatMessage

if TYPE_CHECKING:
    from jarvis.core.config.settings import Settings
    from jarvis.core.interfaces.llm_provider import ILLMProvider
    from jarvis.services.conversation_service import ConversationService

_logger = get_logger("jarvis.services.chat")


class ChatService:
    def __init__(
        self,
        llm: ILLMProvider,
        conversations: ConversationService,
        settings: Settings,
        memory_recall: IMemoryRecallHook | None = None,
    ) -> None:
        self._llm = llm
        self._conversations = conversations
        self._settings = settings
        self._memory_recall: IMemoryRecallHook = memory_recall or NoopMemoryRecall()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def ask(self, conversation_id: str, prompt: str) -> str:
        chunks: list[str] = []
        async for token in self.stream(conversation_id, prompt):
            chunks.append(token)
        return "".join(chunks)

    async def stream(self, conversation_id: str, prompt: str) -> AsyncIterator[str]:
        prompt = prompt.strip()
        if not prompt:
            raise ServiceError("Prompt is empty.")

        # 1. Persist user message.
        await self._conversations.append(conversation_id, "user", prompt)

        # 2. Build the message list:
        #    [system_prompt] + [memory recall] + [persisted history]
        memories = list(await self._memory_recall.recall(conversation_id, prompt))
        history = await self._conversations.history(conversation_id)
        messages: list[ChatMessage] = [
            ChatMessage(role="system", content=self._settings.ui.system_prompt),
            *memories,
            *history,
        ]

        # 3. Stream + capture.
        parts: list[str] = []
        try:
            async for token in self._llm.stream(messages):
                parts.append(token)
                yield token
        except Exception:
            _logger.exception("LLM stream failed; discarding partial answer.")
            raise

        answer = "".join(parts).strip()
        if answer:
            await self._conversations.append(conversation_id, "assistant", answer)
