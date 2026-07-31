"""Deterministic in-memory fake for :class:`ILLMProvider`."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence

from jarvis.core.exceptions import LLMProviderError
from jarvis.core.interfaces.llm_provider import ILLMProvider
from jarvis.core.types import ChatMessage, ProviderStatus


class FakeLLM(ILLMProvider):
    def __init__(
        self,
        canned: str = "Hello from the fake LLM.",
        *,
        name: str = "fake",
        fail: bool = False,
    ) -> None:
        self.name = name
        self._canned = canned
        self._fail = fail
        self.calls: list[list[ChatMessage]] = []

    async def health(self) -> ProviderStatus:
        return ProviderStatus(name=self.name, enabled=True, healthy=not self._fail)

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        self.calls.append(list(messages))
        if self._fail:
            raise LLMProviderError(f"{self.name} is unavailable (simulated).")
        return self._canned

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        self.calls.append(list(messages))
        if self._fail:
            raise LLMProviderError(f"{self.name} is unavailable (simulated).")
        for token in self._canned.split(" "):
            yield token + " "

    async def embed(
        self,
        texts: Sequence[str],
        *,
        model: str | None = None,
    ) -> list[list[float]]:
        if self._fail:
            raise LLMProviderError(f"{self.name} is unavailable (simulated).")
        return [[0.0] * 4 for _ in texts]
