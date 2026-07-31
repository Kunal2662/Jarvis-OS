"""Fallback LLM provider — wraps a primary + secondary provider.

Used when ``Settings.llm_fallback_provider`` is set. The secondary
provider is only ever invoked after the primary raises
:class:`LLMProviderError` (timeout, rate limit, connection error, etc.)
— "use only when necessary" rather than a load-balanced or preferred
provider. ``health()`` reports the primary's status; the fallback is
invisible to callers unless it's actually needed.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence

from jarvis.core.exceptions import LLMProviderError
from jarvis.core.interfaces.llm_provider import ILLMProvider
from jarvis.core.logging.logger import get_logger
from jarvis.core.types import ChatMessage, ProviderStatus

_logger = get_logger("jarvis.infrastructure.llm.fallback")


class FallbackLLMProvider(ILLMProvider):
    def __init__(self, primary: ILLMProvider, fallback: ILLMProvider) -> None:
        self._primary = primary
        self._fallback = fallback
        self.name = primary.name

    async def health(self) -> ProviderStatus:
        return await self._primary.health()

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        try:
            return await self._primary.complete(
                messages, model=model, temperature=temperature, max_tokens=max_tokens
            )
        except LLMProviderError:
            _logger.warning(
                "Primary LLM provider {} failed; falling back to {}.",
                self._primary.name,
                self._fallback.name,
            )
            return await self._fallback.complete(
                messages, model=None, temperature=temperature, max_tokens=max_tokens
            )

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        try:
            async for token in self._primary.stream(
                messages, model=model, temperature=temperature, max_tokens=max_tokens
            ):
                yield token
            return
        except LLMProviderError:
            _logger.warning(
                "Primary LLM provider {} failed mid-stream; falling back to {}.",
                self._primary.name,
                self._fallback.name,
            )
        # Fallback runs as its own attempt — if the primary yielded partial
        # tokens before failing, the caller will see the fallback's reply
        # appended after them, so the fallback re-answers the same prompt.
        async for token in self._fallback.stream(
            messages, model=None, temperature=temperature, max_tokens=max_tokens
        ):
            yield token

    async def embed(self, texts: Sequence[str], *, model: str | None = None) -> list[list[float]]:
        try:
            return await self._primary.embed(texts, model=model)
        except LLMProviderError:
            _logger.warning(
                "Primary LLM provider {} failed embedding; falling back to {}.",
                self._primary.name,
                self._fallback.name,
            )
            return await self._fallback.embed(texts, model=None)
