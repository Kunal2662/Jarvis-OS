"""Built-in API templates (Milestone 5, section 10B).

Each template is a factory that returns a fresh :class:`ApiDefinition` with
sane defaults (base URL, auth type, category) but no secrets filled in --
the user still has to paste their own key/token before it can be enabled.
"""

from __future__ import annotations

from jarvis.domain.api_center.models import ApiAuthType, ApiCategory, ApiDefinition


def _template(
    name: str,
    provider: str,
    category: ApiCategory,
    auth_type: ApiAuthType,
    base_url: str,
    description: str,
) -> ApiDefinition:
    return ApiDefinition(
        name=name,
        provider=provider,
        category=category,
        auth_type=auth_type,
        base_url=base_url,
        description=description,
        is_builtin=True,
    )


def builtin_templates() -> list[ApiDefinition]:
    """Fresh instances of all 14 built-in API templates, in brief-order."""
    return [
        _template(
            "Google Gemini",
            "Google",
            ApiCategory.LLM,
            ApiAuthType.API_KEY,
            "https://generativelanguage.googleapis.com",
            "Google's Gemini family of LLMs.",
        ),
        _template(
            "OpenAI",
            "OpenAI",
            ApiCategory.LLM,
            ApiAuthType.API_KEY,
            "https://api.openai.com/v1",
            "GPT models, embeddings and Whisper.",
        ),
        _template(
            "Anthropic Claude",
            "Anthropic",
            ApiCategory.LLM,
            ApiAuthType.API_KEY,
            "https://api.anthropic.com",
            "Claude models via the Messages API.",
        ),
        _template(
            "OpenRouter",
            "OpenRouter",
            ApiCategory.LLM,
            ApiAuthType.API_KEY,
            "https://openrouter.ai/api/v1",
            "Unified router across many LLM providers.",
        ),
        _template(
            "Groq",
            "Groq",
            ApiCategory.LLM,
            ApiAuthType.API_KEY,
            "https://api.groq.com/openai/v1",
            "Ultra-low-latency LLM inference.",
        ),
        _template(
            "Ollama",
            "Ollama",
            ApiCategory.LLM,
            ApiAuthType.NONE,
            "http://localhost:11434",
            "Local, self-hosted open-weight models.",
        ),
        _template(
            "LM Studio",
            "LM Studio",
            ApiCategory.LLM,
            ApiAuthType.NONE,
            "http://localhost:1234/v1",
            "Local model server with an OpenAI-compatible API.",
        ),
        _template(
            "Google PageSpeed",
            "Google",
            ApiCategory.PERFORMANCE,
            ApiAuthType.API_KEY,
            "https://www.googleapis.com/pagespeedonline/v5",
            "Web performance/Lighthouse scoring.",
        ),
        _template(
            "Serper API",
            "Serper",
            ApiCategory.SEARCH,
            ApiAuthType.API_KEY,
            "https://google.serper.dev",
            "Google Search results API.",
        ),
        _template(
            "GitHub",
            "GitHub",
            ApiCategory.DEVELOPER_TOOLS,
            ApiAuthType.BEARER_TOKEN,
            "https://api.github.com",
            "Repos, issues, PRs and Actions.",
        ),
        _template(
            "Home Assistant",
            "Home Assistant",
            ApiCategory.SMART_HOME,
            ApiAuthType.BEARER_TOKEN,
            "http://homeassistant.local:8123/api",
            "Local smart-home automation hub.",
        ),
        _template(
            "OpenWeather",
            "OpenWeather",
            ApiCategory.WEATHER,
            ApiAuthType.API_KEY,
            "https://api.openweathermap.org/data/2.5",
            "Current weather and forecasts.",
        ),
        _template(
            "OpenStreetMap",
            "OpenStreetMap",
            ApiCategory.MAPPING,
            ApiAuthType.NONE,
            "https://nominatim.openstreetmap.org",
            "Free, open geocoding and map data.",
        ),
        _template(
            "Tesseract OCR",
            "Tesseract",
            ApiCategory.VISION_OCR,
            ApiAuthType.NONE,
            "local://tesseract",
            "Local optical character recognition engine.",
        ),
    ]


BUILTIN_NAMES: tuple[str, ...] = tuple(t.name for t in builtin_templates())
