"""LLM provider port."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Protocol, runtime_checkable

from jarvis.core.types import ChatMessage, ProviderStatus


@runtime_checkable
class ILLMProvider(Protocol):
    """Abstract chat-LLM provider.

    Implementations must be safe to share across coroutines (a single provider
    instance is registered as a DI singleton).
    """

    name: str

    async def health(self) -> ProviderStatus: ...

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str: ...

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]: ...

    async def embed(
        self, texts: Sequence[str], *, model: str | None = None
    ) -> list[list[float]]: ...
