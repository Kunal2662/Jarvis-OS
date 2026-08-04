"""Unit tests for ``jarvis.core.plugins.marketplace`` (Milestone 9 Task
Group D, Phase 8)."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError

import pytest

from jarvis.core.plugins.marketplace import (
    InMemoryReviewStore,
    LocalPluginRepository,
    Marketplace,
    MarketplaceListing,
    Review,
)

_INDEX = {
    "plugins": [
        {
            "name": "weather-widget",
            "display_name": "Weather Widget",
            "description": "Shows the current weather on your dashboard.",
            "author": "JARVIS Team",
            "versions": ["1.0.0", "1.2.0"],
            "sdk_range": ">=1.0.0,<2.0.0",
            "category": "widgets",
            "tags": ["weather", "dashboard"],
        },
        {
            "name": "code-reviewer",
            "display_name": "Code Reviewer",
            "description": "AI-assisted code review commands.",
            "author": "Community",
            "versions": ["0.3.0"],
            "category": "developer-tools",
            "tags": ["ai", "code"],
        },
        {"description": "No name field -- this entry is genuinely malformed."},
    ]
}


def _write_index(tmp_path, data=_INDEX):
    path = tmp_path / "index.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _marketplace(tmp_path, data=_INDEX):
    repository = LocalPluginRepository(_write_index(tmp_path, data))
    return Marketplace(repository)


# ---- LocalPluginRepository ----------------------------------------------------
def test_repository_lists_valid_entries_and_skips_malformed(tmp_path):
    repository = LocalPluginRepository(_write_index(tmp_path))
    listings = repository.list_all()
    assert {listing.plugin_id for listing in listings} == {"weather-widget", "code-reviewer"}


def test_repository_missing_index_returns_empty(tmp_path):
    repository = LocalPluginRepository(tmp_path / "does-not-exist.json")
    assert repository.list_all() == ()


def test_repository_corrupt_index_returns_empty(tmp_path):
    path = tmp_path / "index.json"
    path.write_text("{not valid json", encoding="utf-8")
    repository = LocalPluginRepository(path)
    assert repository.list_all() == ()


def test_repository_parses_full_listing_shape(tmp_path):
    repository = LocalPluginRepository(_write_index(tmp_path))
    (listing,) = [x for x in repository.list_all() if x.plugin_id == "weather-widget"]
    assert listing.display_name == "Weather Widget"
    assert listing.versions == ("1.0.0", "1.2.0")
    assert listing.category == "widgets"
    assert listing.tags == ("weather", "dashboard")


def test_repository_defaults_category_when_absent(tmp_path):
    repository = LocalPluginRepository(_write_index(tmp_path))
    (listing,) = [x for x in repository.list_all() if x.plugin_id == "code-reviewer"]
    assert listing.category == "developer-tools"


# ---- Marketplace browse/search/categories ----------------------------------------------------
def test_browse_returns_all_listings(tmp_path):
    marketplace = _marketplace(tmp_path)
    assert len(marketplace.browse()) == 2


def test_browse_filters_by_category(tmp_path):
    marketplace = _marketplace(tmp_path)
    listings = marketplace.browse(category="widgets")
    assert [listing.plugin_id for listing in listings] == ["weather-widget"]


def test_search_matches_name(tmp_path):
    marketplace = _marketplace(tmp_path)
    results = marketplace.search("weather")
    assert [listing.plugin_id for listing in results] == ["weather-widget"]


def test_search_matches_description(tmp_path):
    marketplace = _marketplace(tmp_path)
    results = marketplace.search("code review")
    assert [listing.plugin_id for listing in results] == ["code-reviewer"]


def test_search_matches_tag(tmp_path):
    marketplace = _marketplace(tmp_path)
    results = marketplace.search("dashboard")
    assert [listing.plugin_id for listing in results] == ["weather-widget"]


def test_search_empty_query_returns_everything(tmp_path):
    marketplace = _marketplace(tmp_path)
    assert len(marketplace.search("   ")) == 2


def test_search_no_match_returns_empty(tmp_path):
    marketplace = _marketplace(tmp_path)
    assert marketplace.search("nonexistent-xyz") == ()


def test_categories_sorted_and_unique(tmp_path):
    marketplace = _marketplace(tmp_path)
    assert marketplace.categories() == ("developer-tools", "widgets")


def test_get_returns_listing_by_id(tmp_path):
    marketplace = _marketplace(tmp_path)
    listing = marketplace.get("weather-widget")
    assert listing is not None
    assert listing.author == "JARVIS Team"


def test_get_unknown_id_returns_none(tmp_path):
    marketplace = _marketplace(tmp_path)
    assert marketplace.get("ghost") is None


# ---- Ratings / reviews ----------------------------------------------------------
def test_rate_and_average(tmp_path):
    marketplace = _marketplace(tmp_path)
    marketplace.rate("weather-widget", "alice", 5, "Great!")
    marketplace.rate("weather-widget", "bob", 3)
    assert marketplace.average_rating("weather-widget") == 4.0
    reviews = marketplace.reviews_for("weather-widget")
    assert len(reviews) == 2
    assert reviews[0].reviewer == "alice"
    assert reviews[0].comment == "Great!"


def test_average_rating_none_when_no_reviews(tmp_path):
    marketplace = _marketplace(tmp_path)
    assert marketplace.average_rating("weather-widget") is None


def test_rate_out_of_range_raises(tmp_path):
    marketplace = _marketplace(tmp_path)
    with pytest.raises(ValueError, match="stars"):
        marketplace.rate("weather-widget", "alice", 6)


def test_in_memory_review_store_isolated_per_plugin():
    store = InMemoryReviewStore()
    store.add(Review(plugin_id="a", reviewer="alice", stars=5))
    store.add(Review(plugin_id="b", reviewer="bob", stars=1))
    assert len(store.list_for("a")) == 1
    assert len(store.list_for("b")) == 1
    assert store.list_for("a")[0].reviewer == "alice"


def test_marketplace_default_review_store_used_when_none_given(tmp_path):
    marketplace = _marketplace(tmp_path)
    marketplace.rate("weather-widget", "alice", 4)
    assert marketplace.average_rating("weather-widget") == 4.0


def test_listing_is_immutable():
    listing = MarketplaceListing(
        plugin_id="p", display_name="P", description="", author="a", versions=("1.0.0",)
    )
    with pytest.raises(FrozenInstanceError):
        listing.plugin_id = "changed"  # type: ignore[misc]
