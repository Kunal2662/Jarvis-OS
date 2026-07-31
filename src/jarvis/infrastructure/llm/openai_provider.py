"""OpenAI chat + embedding adapter using the official ``openai`` async SDK.

The user provides their own key via ``JARVIS_OPENAI_API_KEY``. This module
never falls back to hard-coded credentials.

* Streaming is the *default*; :meth:`complete` uses :meth:`stream` internally.
* Errors from the SDK are translated into :class:`LLMProviderError` so
  higher layers never depend on the ``openai`` package.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import TYPE_CHECKING

from openai import APIConnectionError, APIError, APITimeoutError, AsyncOpenAI, RateLimitError

from jarvis.core.exceptions import LLMProviderError
from jarvis.core.interfaces.llm_provider import ILLMProvider
from jarvis.core.logging.logger import get_logger
from jarvis.core.types import ChatMessage, ProviderStatus

if TYPE_CHECKING:
    from jarvis.core.config.settings import OpenAISettings

_logger = get_logger("jarvis.infrastructure.llm.openai")

_DEFAULT_TIMEOUT_S: float = 60.0
_EMBEDDING_MODEL: str = "text-embedding-3-small"


def _to_openai_messages(messages: Sequence[ChatMessage]) -> list[dict[str, str]]:
    """Convert our internal :class:`ChatMessage` to the OpenAI wire format."""
    out: list[dict[str, str]] = []
    for m in messages:
        item: dict[str, str] = {"role": m.role, "content": m.content}
        if m.name:
            item["name"] = m.name
        out.append(item)
    return out


class OpenAILLMProvider(ILLMProvider):
    """Async OpenAI adapter — streaming-first."""

    name: str = "openai"

    def __init__(self, settings: OpenAISettings) -> None:
        self._settings = settings
        self._client: AsyncOpenAI | None = None

    # ------------------------------------------------------------------
    # Client lazy-init  (avoids constructing httpx before we need it)
    # ------------------------------------------------------------------
    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            api_key = self._settings.api_key.get_secret_value()
            if not api_key:
                raise LLMProviderError(
                    "OpenAI provider selected but JARVIS_OPENAI_API_KEY is empty."
                )
            self._client = AsyncOpenAI(
                api_key=api_key,
                base_url=self._settings.base_url or None,
                organization=self._settings.org or None,
                timeout=_DEFAULT_TIMEOUT_S,
                max_retries=2,
            )
        return self._client

    # ------------------------------------------------------------------
    # Interface implementation
    # ------------------------------------------------------------------
    async def health(self) -> ProviderStatus:
        if not self._settings.enabled:
            return ProviderStatus(name=self.name, enabled=False, healthy=False, detail="disabled")
        try:
            client = self._get_client()
            # `models.list` is the cheapest authenticated call.
            await client.models.list()
            return ProviderStatus(name=self.name, enabled=True, healthy=True)
        except (APIConnectionError, APITimeoutError, APIError) as err:
            return ProviderStatus(
                name=self.name, enabled=True, healthy=False, detail=f"{type(err).__name__}: {err}"
            )
        except LLMProviderError as err:
            return ProviderStatus(name=self.name, enabled=True, healthy=False, detail=str(err))

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
        payload: dict[str, object] = {
            "model": model or self._settings.chat_model,
            "messages": _to_openai_messages(messages),
            "temperature": temperature,
            "stream": True,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        try:
            stream = await client.chat.completions.create(**payload)  # type: ignore[arg-type]
            async for event in stream:
                if not event.choices:
                    continue
                delta = event.choices[0].delta
                token = getattr(delta, "content", None)
                if token:
                    yield token
        except RateLimitError as err:
            raise LLMProviderError(f"OpenAI rate-limited: {err}") from err
        except (APIConnectionError, APITimeoutError) as err:
            raise LLMProviderError(f"OpenAI connection error: {err}") from err
        except APIError as err:
            raise LLMProviderError(f"OpenAI API error: {err}") from err
        except Exception as err:  # pragma: no cover — last-resort translation
            _logger.exception("Unexpected OpenAI stream failure.")
            raise LLMProviderError(f"OpenAI failure: {err}") from err

    async def embed(
        self,
        texts: Sequence[str],
        *,
        model: str | None = None,
    ) -> list[list[float]]:
        client = self._get_client()
        try:
            resp = await client.embeddings.create(
                model=model or _EMBEDDING_MODEL,
                input=list(texts),
            )
            return [item.embedding for item in resp.data]
        except (APIConnectionError, APITimeoutError, APIError) as err:
            raise LLMProviderError(f"OpenAI embedding error: {err}") from err
