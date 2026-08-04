"""Unit tests for :class:`SearchService`'s provider registry and fan-out
merge — Milestone 10A, Additional Requirement #1."""

from __future__ import annotations

import pytest

from jarvis.core.interfaces.search import SearchResult


class _FakeSource:
    def __init__(
        self, source_type: str, results: list[SearchResult], *, fail: bool = False
    ) -> None:
        self.source_type = source_type
        self._results = results
        self._fail = fail
        self.calls: list[str] = []

    async def search(self, query: str, *, top_k: int = 10) -> list[SearchResult]:
        self.calls.append(query)
        if self._fail:
            raise RuntimeError("simulated source failure")
        return self._results[:top_k]


def _result(source: str, score: float) -> SearchResult:
    return SearchResult(id=f"{source}-1", title=source, content="", source=source, score=score)


@pytest.mark.asyncio
async def test_register_and_get_sources() -> None:
    from jarvis.services.search_service import SearchService

    svc = SearchService()
    memory_source = _FakeSource("memory", [])
    svc.register_source(memory_source)

    assert [s.source_type for s in svc.get_sources()] == ["memory"]


@pytest.mark.asyncio
async def test_register_source_replaces_same_type() -> None:
    from jarvis.services.search_service import SearchService

    svc = SearchService()
    svc.register_source(_FakeSource("memory", [_result("memory", 0.5)]))
    svc.register_source(_FakeSource("memory", [_result("memory", 0.9)]))

    assert len(svc.get_sources()) == 1
    results = await svc.search("x")
    assert results[0].score == 0.9


@pytest.mark.asyncio
async def test_unregister_source() -> None:
    from jarvis.services.search_service import SearchService

    svc = SearchService()
    svc.register_source(_FakeSource("memory", []))
    svc.unregister_source("memory")

    assert svc.get_sources() == []


@pytest.mark.asyncio
async def test_search_fans_out_and_merges_by_score() -> None:
    from jarvis.services.search_service import SearchService

    svc = SearchService()
    svc.register_source(_FakeSource("memory", [_result("memory", 0.3)]))
    svc.register_source(_FakeSource("knowledge", [_result("knowledge", 0.9)]))

    results = await svc.search("query")

    assert [r.source for r in results] == ["knowledge", "memory"]  # sorted by score desc


@pytest.mark.asyncio
async def test_search_spans_at_least_two_source_types() -> None:
    """Milestone 10A Acceptance Criterion 4: a single Universal Search
    query returns relevant results spanning at least two distinct
    source types in one response."""
    from jarvis.services.search_service import SearchService

    svc = SearchService()
    svc.register_source(_FakeSource("memory", [_result("memory", 0.5)]))
    svc.register_source(_FakeSource("commands", [_result("commands", 0.6)]))

    results = await svc.search("query")

    assert {r.source for r in results} == {"memory", "commands"}


@pytest.mark.asyncio
async def test_search_filters_by_source_types() -> None:
    from jarvis.services.search_service import SearchService

    svc = SearchService()
    svc.register_source(_FakeSource("memory", [_result("memory", 0.5)]))
    svc.register_source(_FakeSource("commands", [_result("commands", 0.6)]))

    results = await svc.search("query", source_types={"memory"})

    assert {r.source for r in results} == {"memory"}


@pytest.mark.asyncio
async def test_failing_source_does_not_break_the_query() -> None:
    from jarvis.services.search_service import SearchService

    svc = SearchService()
    svc.register_source(_FakeSource("memory", [_result("memory", 0.5)]))
    svc.register_source(_FakeSource("broken", [], fail=True))

    results = await svc.search("query")

    assert [r.source for r in results] == ["memory"]


@pytest.mark.asyncio
async def test_search_empty_query_returns_nothing() -> None:
    from jarvis.services.search_service import SearchService

    svc = SearchService()
    svc.register_source(_FakeSource("memory", [_result("memory", 0.5)]))

    assert await svc.search("   ") == []


@pytest.mark.asyncio
async def test_search_respects_top_k() -> None:
    from jarvis.services.search_service import SearchService

    svc = SearchService()
    svc.register_source(
        _FakeSource(
            "memory", [_result("memory", 0.9), _result("memory", 0.8), _result("memory", 0.7)]
        )
    )

    results = await svc.search("query", top_k=2)

    assert len(results) == 2
