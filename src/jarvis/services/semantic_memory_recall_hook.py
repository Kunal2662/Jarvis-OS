"""Semantic memory-recall hook.

Implements :class:`IMemoryRecallHook` by querying :class:`MemoryService`
and returning up to ``top_k`` matching memories as ``system`` messages
that :class:`ChatService.stream` prepends to the LLM call.

The wire-up is a **drop-in replacement** for :class:`NoopMemoryRecall`;
`ChatService` itself is untouched.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from jarvis.core.interfaces.memory import IMemoryRecallHook
from jarvis.core.logging.logger import get_logger
from jarvis.core.types import ChatMessage

if TYPE_CHECKING:
    from jarvis.services.memory_service import MemoryService

_logger = get_logger("jarvis.services.memory_recall")


class SemanticMemoryRecallHook(IMemoryRecallHook):
    def __init__(
        self,
        memory_service: MemoryService,
        *,
        top_k: int = 4,
        min_score: float = 0.15,
        prefix: str = "Relevant memory: ",
    ) -> None:
        self._svc = memory_service
        self._top_k = top_k
        self._min_score = min_score
        self._prefix = prefix

    async def recall(self, conversation_id: str, prompt: str) -> Sequence[ChatMessage]:
        try:
            memories = await self._svc.recall(prompt, top_k=self._top_k, min_score=self._min_score)
        except Exception as err:
            _logger.exception("Memory recall raised — returning empty ({}).", err)
            return ()
        if not memories:
            return ()
        return tuple(
            ChatMessage(role="system", content=f"{self._prefix}{m.content}") for m in memories
        )
