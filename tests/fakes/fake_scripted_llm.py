"""Deterministic fake for :class:`ILLMProvider` used by agent-graph tests.

Unlike :class:`~tests.fakes.fake_llm.FakeLLM` (one canned answer for every
call), the agent orchestrator calls the same ``ILLMProvider`` from four
different nodes (planner, tool_selector, critic, responder) with four
different prompts in one run. ``ScriptedFakeLLM`` picks its canned answer
by matching a substring anchor unique to each node's prompt template (see
``agents/nodes/*.py`` and ``agents/prompting.py``), so a single fake
instance can drive a whole graph run deterministically.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence

from jarvis.core.exceptions import LLMProviderError
from jarvis.core.interfaces.llm_provider import ILLMProvider
from jarvis.core.types import ChatMessage, ProviderStatus


class ScriptedFakeLLM(ILLMProvider):
    def __init__(
        self,
        responses: dict[str, str],
        *,
        default: str = "",
        name: str = "fake-scripted",
        fail: bool = False,
        delay: float = 0.0,
    ) -> None:
        self.name = name
        self._responses = responses
        self._default = default
        self._fail = fail
        self._delay = delay
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
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._fail:
            raise LLMProviderError(f"{self.name} is unavailable (simulated).")
        prompt = messages[-1].content if messages else ""
        for anchor, response in self._responses.items():
            if anchor in prompt:
                return response
        return self._default

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        text = await self.complete(
            messages, model=model, temperature=temperature, max_tokens=max_tokens
        )
        for token in text.split(" "):
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
