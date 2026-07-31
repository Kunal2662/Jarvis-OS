"""Ollama chat + embedding adapter using the async ``ollama`` client.

Talks to a local Ollama daemon (default ``http://127.0.0.1:11434``). No API
key required — this is the *local-first* provider.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import TYPE_CHECKING

from ollama import AsyncClient, ResponseError

from jarvis.core.exceptions import LLMProviderError
from jarvis.core.interfaces.llm_provider import ILLMProvider
from jarvis.core.logging.logger import get_logger
from jarvis.core.types import ChatMessage, ProviderStatus

if TYPE_CHECKING:
    from jarvis.core.config.settings import OllamaSettings

_logger = get_logger("jarvis.infrastructure.llm.ollama")


def _to_ollama_messages(messages: Sequence[ChatMessage]) -> list[dict[str, str]]:
    return [{"role": m.role, "content": m.content} for m in messages]


class OllamaLLMProvider(ILLMProvider):
    """Async Ollama adapter — streaming-first."""

    name: str = "ollama"

    def __init__(self, settings: OllamaSettings) -> None:
        self._settings = settings
        self._client: AsyncClient | None = None

    def _get_client(self) -> AsyncClient:
        if self._client is None:
            self._client = AsyncClient(host=self._settings.base_url)
        return self._client

    async def health(self) -> ProviderStatus:
        if not self._settings.enabled:
            return ProviderStatus(name=self.name, enabled=False, healthy=False, detail="disabled")
        try:
            client = self._get_client()
            await client.list()
            return ProviderStatus(name=self.name, enabled=True, healthy=True)
        except Exception as err:  # ollama uses various exception types
            return ProviderStatus(
                name=self.name,
                enabled=True,
                healthy=False,
                detail=f"{type(err).__name__}: {err}",
            )

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        parts: list[str] = []
        async for chunk in self.stream(
            messages, model=model, temperature=temperature, max_tokens=max_tokens
        ):
            parts.append(chunk)
        return "".join(parts)

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        client = self._get_client()
        options: dict[str, object] = {"temperature": temperature}
        if max_tokens is not None:
            options["num_predict"] = max_tokens
        try:
            stream = await client.chat(
                model=model or self._settings.model,
                messages=_to_ollama_messages(messages),
                stream=True,
                options=options,
            )
            async for part in stream:
                msg = (
                    part.get("message")
                    if isinstance(part, dict)
                    else getattr(part, "message", None)
                )
                if msg is None:
                    continue
                token = (
                    msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", None)
                )
                if token:
                    yield token
        except ResponseError as err:
            raise LLMProviderError(f"Ollama API error: {err}") from err
        except Exception as err:  # pragma: no cover
            _logger.exception("Unexpected Ollama stream failure.")
            raise LLMProviderError(f"Ollama failure: {err}") from err

    async def embed(
        self,
        texts: Sequence[str],
        *,
        model: str | None = None,
    ) -> list[list[float]]:
        client = self._get_client()
        target = model or self._settings.model
        try:
            out: list[list[float]] = []
            for text in texts:
                resp = await client.embeddings(model=target, prompt=text)
                embedding = (
                    resp.get("embedding")
                    if isinstance(resp, dict)
                    else getattr(resp, "embedding", None)
                )
                if embedding is None:
                    raise LLMProviderError("Ollama returned no embedding.")
                out.append(list(embedding))
            return out
        except ResponseError as err:
            raise LLMProviderError(f"Ollama embedding error: {err}") from err
