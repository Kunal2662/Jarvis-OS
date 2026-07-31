"""LLM factory helper.

The DI container already picks the correct adapter based on
``settings.llm_default_provider``. This module exists so tests and
integration points can build a provider from a config dict without going
through the container.
"""

from __future__ import annotations

from jarvis.core.exceptions import ConfigError
from jarvis.core.interfaces.llm_provider import ILLMProvider
from jarvis.core.types import LLMProviderName


def build_llm_provider(
    name: LLMProviderName,
    *,
    openai_settings,
    ollama_settings,
    gemini_settings=None,
) -> ILLMProvider:
    if name is LLMProviderName.OPENAI:
        from jarvis.infrastructure.llm.openai_provider import OpenAILLMProvider

        return OpenAILLMProvider(openai_settings)
    if name is LLMProviderName.OLLAMA:
        from jarvis.infrastructure.llm.ollama_provider import OllamaLLMProvider

        return OllamaLLMProvider(ollama_settings)
    if name is LLMProviderName.GEMINI:
        from jarvis.infrastructure.llm.gemini_provider import GeminiLLMProvider

        if gemini_settings is None:
            raise ConfigError("Gemini provider requested but no gemini_settings supplied.")
        return GeminiLLMProvider(gemini_settings)
    raise ConfigError(f"Unknown LLM provider: {name!r}")
