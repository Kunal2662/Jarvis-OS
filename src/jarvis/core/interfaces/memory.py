"""Memory-recall hook — reserved integration point for Milestone 3.

The point of this file is to define, *today*, the exact shape of the
callable that :class:`ChatService.stream` will invoke to augment the
prompt with relevant memories. Milestone 3 will ship a concrete
implementation backed by ``MemoryService`` + ChromaDB; until then a
:class:`NoopMemoryRecall` is injected so the pipeline works unchanged.

Reserving the hook now means Milestone 3 becomes a **drop-in** —
``ChatService`` will not need to be touched.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from jarvis.core.types import ChatMessage


@runtime_checkable
class IMemoryRecallHook(Protocol):
    """Return system-level memories to prepend to a user prompt.

    Implementations must be fast (<200 ms typical); if the underlying store
    is unavailable, return an empty list — never raise.
    """

    async def recall(self, conversation_id: str, prompt: str) -> Sequence[ChatMessage]: ...


class NoopMemoryRecall(IMemoryRecallHook):
    """Default hook — never returns any memories."""

    async def recall(self, conversation_id: str, prompt: str) -> Sequence[ChatMessage]:
        return ()
