"""Unit tests for :class:`ApiSuggester` -- Milestone 5, smart API detection."""

from __future__ import annotations

from jarvis.features.api_center.registry import builtin_templates
from jarvis.features.api_center.suggester import ApiSuggester, SuggestionContext


def _names(suggestions) -> list[str]:
    return [s.name for s in suggestions]


def test_prefix_match_open() -> None:
    suggester = ApiSuggester()
    results = _names(suggester.suggest("Open", builtin_templates()))
    for expected in ("OpenAI", "OpenRouter", "OpenWeather", "OpenStreetMap"):
        assert expected in results


def test_prefix_match_gem() -> None:
    suggester = ApiSuggester()
    assert _names(suggester.suggest("Gem", builtin_templates()))[0] == "Google Gemini"


def test_substring_match_git() -> None:
    suggester = ApiSuggester()
    assert "GitHub" in _names(suggester.suggest("Git", builtin_templates()))


def test_prefix_match_gro() -> None:
    suggester = ApiSuggester()
    assert _names(suggester.suggest("Gro", builtin_templates()))[0] == "Groq"


def test_substring_match_cla() -> None:
    suggester = ApiSuggester()
    assert "Anthropic Claude" in _names(suggester.suggest("Cla", builtin_templates()))


def test_prefix_match_lm() -> None:
    suggester = ApiSuggester()
    assert "LM Studio" in _names(suggester.suggest("LM", builtin_templates()))


def test_substring_match_home() -> None:
    suggester = ApiSuggester()
    assert "Home Assistant" in _names(suggester.suggest("Home", builtin_templates()))


def test_typo_tolerance() -> None:
    suggester = ApiSuggester()
    assert "Anthropic Claude" in _names(suggester.suggest("Antropic", builtin_templates()))


def test_empty_query_returns_favorites_and_recents_first() -> None:
    suggester = ApiSuggester()
    templates = builtin_templates()
    context = SuggestionContext(favorite_names=("Groq",), recent_names=("OpenAI",))
    results = suggester.suggest("", templates, context=context, limit=3)
    assert results[0].name == "Groq"


def test_no_match_returns_empty() -> None:
    suggester = ApiSuggester()
    assert suggester.suggest("zzzznotanapi", builtin_templates()) == []
