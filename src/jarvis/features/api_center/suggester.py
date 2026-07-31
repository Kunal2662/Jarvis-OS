"""Smart API Detection -- autocomplete, partial search, typo tolerance,
recents and favorites, exactly as spec'd in 10B.

Matching strategy (checked in order, first non-empty wins per candidate):

1. Prefix match (case-insensitive) on name/provider -- "Open" -> OpenAI,
   OpenRouter, OpenWeather, OpenStreetMap.
2. Substring match anywhere in name/provider -- "Git" -> GitHub.
3. Typo-tolerant match via :func:`difflib.SequenceMatcher` ratio -- lets
   "Antropic" still surface Anthropic Claude.

Recency and favorites are tracked by the caller (``ApiCenterService``) and
passed in here purely to bias ordering -- the suggester itself holds no
state, so it stays trivially unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from jarvis.domain.api_center.models import ApiDefinition, ApiSuggestion

_TYPO_THRESHOLD = 0.6


@dataclass(frozen=True, slots=True)
class SuggestionContext:
    recent_names: tuple[str, ...] = ()
    favorite_names: tuple[str, ...] = ()


class ApiSuggester:
    def suggest(
        self,
        query: str,
        candidates: list[ApiDefinition],
        *,
        context: SuggestionContext | None = None,
        limit: int = 8,
    ) -> list[ApiSuggestion]:
        context = context or SuggestionContext()
        query = query.strip().lower()

        if not query:
            return self._default_order(candidates, context, limit)

        scored: list[tuple[float, ApiDefinition]] = []
        for api in candidates:
            score = self._score(query, api)
            if score <= 0:
                continue
            if api.name in context.favorite_names:
                score += 0.5
            if api.name in context.recent_names:
                score += 0.25
            scored.append((score, api))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [
            ApiSuggestion(name=a.name, provider=a.provider, category=a.category, score=s)
            for s, a in scored[:limit]
        ]

    def _default_order(
        self, candidates: list[ApiDefinition], context: SuggestionContext, limit: int
    ) -> list[ApiSuggestion]:
        def _key(api: ApiDefinition) -> tuple[int, int, str]:
            fav = 0 if api.name in context.favorite_names else 1
            recent = 0 if api.name in context.recent_names else 1
            return (fav, recent, api.name)

        ordered = sorted(candidates, key=_key)[:limit]
        return [
            ApiSuggestion(name=a.name, provider=a.provider, category=a.category, score=1.0)
            for a in ordered
        ]

    def _score(self, query: str, api: ApiDefinition) -> float:
        name = api.name.lower()
        provider = api.provider.lower()

        if name.startswith(query) or provider.startswith(query):
            return 1.0
        if query in name or query in provider:
            return 0.8
        ratio = max(
            SequenceMatcher(None, query, name).ratio(),
            SequenceMatcher(None, query, provider).ratio(),
        )
        return ratio if ratio >= _TYPO_THRESHOLD else 0.0
