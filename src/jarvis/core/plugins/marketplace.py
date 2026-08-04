"""Marketplace Foundation -- Milestone 9 Task Group D, Phase 8.

The discoverable browse/search layer over a plugin index --
``docs/MASTER_ROADMAP.md`` section 8's own words for the Plugin Store:
*"no hosted infra for v1; a signed JSON index on GitHub
({name, description, author, versions[], sdk_range, homepage}),
community-curated via PRs."* :class:`LocalPluginRepository` is the
real, complete v1 implementation of exactly that shape -- reading a
local JSON file, since no hosted index exists yet to fetch from.

**Future cloud compatibility without implementing cloud services yet.**
:class:`IPluginRepository` is the one seam a future
``GitHubPluginRepository``/``CloudPluginRepository`` -- fetching the
identical JSON shape over HTTP instead of from a local path -- plugs
into. Nothing above this seam (:class:`Marketplace`'s browse/search/
categories/ratings) would change; that is the whole point of the
abstraction existing now rather than being added when the second
implementation actually gets written.

**Ratings/reviews are genuinely functional today, not a stub
interface.** :class:`InMemoryReviewStore` really accepts, lists, and
averages reviews for the runtime's own lifetime -- it just does not
persist across a restart, and has no real user-identity system to
attribute a review to beyond whatever *reviewer* string a caller
supplies. Both are honest, documented v1 limits, not silently faked
completeness.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from pathlib import Path

_logger = get_logger("jarvis.core.plugins.marketplace")

MIN_STARS = 1
MAX_STARS = 5


@dataclass(frozen=True, slots=True)
class MarketplaceListing:
    plugin_id: str
    display_name: str
    description: str
    author: str
    versions: tuple[str, ...]
    sdk_range: str = ""
    homepage: str | None = None
    category: str = "uncategorized"
    tags: tuple[str, ...] = field(default_factory=tuple)


@runtime_checkable
class IPluginRepository(Protocol):
    def list_all(self) -> tuple[MarketplaceListing, ...]: ...


class LocalPluginRepository:
    """Reads ``{"plugins": [...]}`` from a local JSON index file. A
    malformed index, or one or more malformed entries within an
    otherwise-valid index, are logged and skipped -- never a hard
    failure that empties the whole marketplace over one bad entry."""

    def __init__(self, index_path: Path) -> None:
        self._index_path = index_path

    def list_all(self) -> tuple[MarketplaceListing, ...]:
        if not self._index_path.exists():
            return ()
        try:
            raw = json.loads(self._index_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as err:
            _logger.warning("Could not read marketplace index {}: {}", self._index_path, err)
            return ()

        listings: list[MarketplaceListing] = []
        for entry in raw.get("plugins", []):
            listing = self._parse_entry(entry)
            if listing is not None:
                listings.append(listing)
        return tuple(listings)

    @staticmethod
    def _parse_entry(entry: dict[str, Any]) -> MarketplaceListing | None:
        try:
            return MarketplaceListing(
                plugin_id=entry["name"],
                display_name=entry.get("display_name", entry["name"]),
                description=entry.get("description", ""),
                author=entry.get("author", "unknown"),
                versions=tuple(entry.get("versions", [])),
                sdk_range=entry.get("sdk_range", ""),
                homepage=entry.get("homepage"),
                category=entry.get("category", "uncategorized"),
                tags=tuple(entry.get("tags", [])),
            )
        except KeyError as err:
            _logger.warning("Skipping malformed marketplace entry: missing {}", err)
            return None


@dataclass(frozen=True, slots=True)
class Review:
    plugin_id: str
    reviewer: str
    stars: int
    comment: str = ""
    at: datetime = field(default_factory=lambda: datetime.now(UTC))


@runtime_checkable
class IReviewStore(Protocol):
    def add(self, review: Review) -> None: ...
    def list_for(self, plugin_id: str) -> tuple[Review, ...]: ...
    def average_rating(self, plugin_id: str) -> float | None: ...


class InMemoryReviewStore:
    def __init__(self) -> None:
        self._reviews: dict[str, list[Review]] = defaultdict(list)

    def add(self, review: Review) -> None:
        if not MIN_STARS <= review.stars <= MAX_STARS:
            raise ValueError(
                f"stars must be between {MIN_STARS} and {MAX_STARS}, got {review.stars}."
            )
        self._reviews[review.plugin_id].append(review)

    def list_for(self, plugin_id: str) -> tuple[Review, ...]:
        return tuple(self._reviews.get(plugin_id, ()))

    def average_rating(self, plugin_id: str) -> float | None:
        reviews = self._reviews.get(plugin_id)
        if not reviews:
            return None
        return sum(r.stars for r in reviews) / len(reviews)


class Marketplace:
    def __init__(
        self, repository: IPluginRepository, *, review_store: IReviewStore | None = None
    ) -> None:
        self._repository = repository
        self._review_store = review_store or InMemoryReviewStore()

    def browse(self, *, category: str | None = None) -> tuple[MarketplaceListing, ...]:
        listings = self._repository.list_all()
        if category is None:
            return listings
        return tuple(listing for listing in listings if listing.category == category)

    def search(self, query: str) -> tuple[MarketplaceListing, ...]:
        normalized = query.strip().lower()
        if not normalized:
            return self._repository.list_all()
        return tuple(
            listing for listing in self._repository.list_all() if self._matches(listing, normalized)
        )

    @staticmethod
    def _matches(listing: MarketplaceListing, normalized_query: str) -> bool:
        haystacks = (listing.plugin_id, listing.display_name, listing.description, *listing.tags)
        return any(normalized_query in haystack.lower() for haystack in haystacks)

    def categories(self) -> tuple[str, ...]:
        return tuple(sorted({listing.category for listing in self._repository.list_all()}))

    def get(self, plugin_id: str) -> MarketplaceListing | None:
        for listing in self._repository.list_all():
            if listing.plugin_id == plugin_id:
                return listing
        return None

    def rate(self, plugin_id: str, reviewer: str, stars: int, comment: str = "") -> None:
        self._review_store.add(
            Review(plugin_id=plugin_id, reviewer=reviewer, stars=stars, comment=comment)
        )

    def reviews_for(self, plugin_id: str) -> tuple[Review, ...]:
        return self._review_store.list_for(plugin_id)

    def average_rating(self, plugin_id: str) -> float | None:
        return self._review_store.average_rating(plugin_id)
