"""Google AI Studio / Gemini adapter.

Talks directly to the Generative Language REST API
(``generativelanguage.googleapis.com``) over ``httpx`` — already a
project dependency — rather than pulling in the ``google-genai`` SDK, to
keep this adapter small and consistent with the ElevenLabs TTS adapter's
approach.

This provider is intended to be used as a **secondary/fallback**
provider (see ``Settings.llm_fallback_provider``) rather than the
default — it's only invoked when the primary provider's call fails.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import TYPE_CHECKING

import httpx

from jarvis.core.exceptions import LLMProviderError
from jarvis.core.interfaces.llm_provider import ILLMProvider
from jarvis.core.logging.logger import get_logger
from jarvis.core.types import ChatMessage, ProviderStatus

if TYPE_CHECKING:
    from jarvis.core.config.settings import GeminiSettings

_logger = get_logger("jarvis.infrastructure.llm.gemini")

_DEFAULT_TIMEOUT_S: float = 60.0

# Gemini has no "system" role; system messages are sent via a separate
# `systemInstruction` field, and everything else maps user->user,
# assistant->model.
_ROLE_MAP = {"user": "user", "assistant": "model"}


def _to_gemini_payload(messages: Sequence[ChatMessage]) -> tuple[dict | None, list[dict]]:
    system_instruction: dict | None = None
    contents: list[dict] = []
    for m in messages:
        if m.role == "system":
            # Gemini only supports one system instruction; concatenate if
            # more than one system message is present.
            text = m.content
            if system_instruction is None:
                system_instruction = {"parts": [{"text": text}]}
            else:
                system_instruction["parts"][0]["text"] += "\n\n" + text
            continue
        role = _ROLE_MAP.get(m.role, "user")
        contents.append({"role": role, "parts": [{"text": m.content}]})
    return system_instruction, contents


class GeminiLLMProvider(ILLMProvider):
    """Async Gemini adapter over the REST API — streaming-first."""

    name: str = "gemini"

    def __init__(self, settings: GeminiSettings) -> None:
        self._settings = settings

    def _require_key(self) -> str:
        key = self._settings.api_key.get_secret_value()
        if not key:
            raise LLMProviderError("Gemini provider selected but JARVIS_GEMINI_API_KEY is empty.")
        return key

    async def health(self) -> ProviderStatus:
        if not self._settings.enabled:
            return ProviderStatus(name=self.name, enabled=False, healthy=False, detail="disabled")
        try:
            key = self._require_key()
        except LLMProviderError as err:
            return ProviderStatus(name=self.name, enabled=True, healthy=False, detail=str(err))
        try:
            async with httpx.AsyncClient(base_url=self._settings.base_url, timeout=10) as client:
                resp = await client.get("/models", params={"key": key})
                resp.raise_for_status()
            return ProviderStatus(name=self.name, enabled=True, healthy=True)
        except httpx.HTTPStatusError as err:
            detail = self._extract_error(err.response)
            return ProviderStatus(name=self.name, enabled=True, healthy=False, detail=detail)
        except httpx.HTTPError as err:
            return ProviderStatus(
                name=self.name, enabled=True, healthy=False, detail=f"{type(err).__name__}: {err}"
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
        key = self._require_key()
        model_name = model or self._settings.chat_model
        system_instruction, contents = _to_gemini_payload(messages)

        generation_config: dict[str, object] = {"temperature": temperature}
        if max_tokens is not None:
            generation_config["maxOutputTokens"] = max_tokens

        payload: dict[str, object] = {
            "contents": contents,
            "generationConfig": generation_config,
        }
        if system_instruction is not None:
            payload["systemInstruction"] = system_instruction

        url = f"/models/{model_name}:streamGenerateContent"
        try:
            async with (
                httpx.AsyncClient(
                    base_url=self._settings.base_url, timeout=_DEFAULT_TIMEOUT_S
                ) as client,
                client.stream(
                    "POST",
                    url,
                    params={"key": key, "alt": "sse"},
                    json=payload,
                ) as resp,
            ):
                if resp.status_code >= 400:
                    body = await resp.aread()
                    detail = self._extract_error_bytes(body)
                    raise LLMProviderError(f"Gemini API error ({resp.status_code}): {detail}")
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[len("data:") :].strip()
                    if not data or data == "[DONE]":
                        continue
                    token = self._extract_token(data)
                    if token:
                        yield token
        except httpx.HTTPError as err:
            raise LLMProviderError(f"Gemini connection error: {err}") from err

    async def embed(
        self,
        texts: Sequence[str],
        *,
        model: str | None = None,
    ) -> list[list[float]]:
        key = self._require_key()
        model_name = model or self._settings.embedding_model
        out: list[list[float]] = []
        try:
            async with httpx.AsyncClient(
                base_url=self._settings.base_url, timeout=_DEFAULT_TIMEOUT_S
            ) as client:
                for text in texts:
                    resp = await client.post(
                        f"/models/{model_name}:embedContent",
                        params={"key": key},
                        json={"content": {"parts": [{"text": text}]}},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    out.append(data.get("embedding", {}).get("values", []))
            return out
        except httpx.HTTPStatusError as err:
            raise LLMProviderError(
                f"Gemini embedding error: {self._extract_error(err.response)}"
            ) from err
        except httpx.HTTPError as err:
            raise LLMProviderError(f"Gemini embedding connection error: {err}") from err

    # ------------------------------------------------------------------
    @staticmethod
    def _extract_token(sse_json_line: str) -> str:
        import json

        try:
            obj = json.loads(sse_json_line)
        except ValueError:
            return ""
        try:
            candidates = obj.get("candidates", [])
            if not candidates:
                return ""
            parts = candidates[0].get("content", {}).get("parts", [])
            return "".join(p.get("text", "") for p in parts)
        except (AttributeError, TypeError):
            return ""

    @staticmethod
    def _extract_error(response: httpx.Response) -> str:
        try:
            body = response.json()
            return body.get("error", {}).get("message", response.text)[:300]
        except ValueError:
            return response.text[:300]

    @staticmethod
    def _extract_error_bytes(body: bytes) -> str:
        import json

        try:
            parsed = json.loads(body)
            if isinstance(parsed, list) and parsed:
                parsed = parsed[0]
            return str(parsed.get("error", {}).get("message", parsed))[:300]
        except (ValueError, AttributeError):
            return body.decode("utf-8", errors="replace")[:300]
