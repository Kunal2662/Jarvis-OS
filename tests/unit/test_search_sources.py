"""Unit tests for the concrete :class:`~jarvis.core.interfaces.search.ISearchSource`
adapters — Milestone 10A."""

from __future__ import annotations

from dataclasses import dataclass

import pytest


@dataclass
class _FakeMemoryRecord:
    id: str
    content: str
    memory_type: str = "conversation"
    pinned: bool = False
    score: float = 0.5


class _FakeMemoryService:
    def __init__(self, records: list[_FakeMemoryRecord]) -> None:
        self._records = records

    async def search(self, query: str, *, mode: str = "hybrid", top_k: int = 20):
        return self._records[:top_k]


@pytest.mark.asyncio
async def test_memory_search_source_wraps_memory_service_search() -> None:
    from jarvis.services.search_sources import MemorySearchSource

    memory = _FakeMemoryService([_FakeMemoryRecord(id="m1", content="hello world")])
    source = MemorySearchSource(memory)

    results = await source.search("hello")

    assert source.source_type == "memory"
    assert results[0].id == "m1"
    assert results[0].content == "hello world"
    assert results[0].source == "memory"


class _FakeKnowledgeService:
    async def search(self, query: str, *, top_k: int = 10):
        from jarvis.core.interfaces.search import SearchResult

        return [
            SearchResult(id="e1", title="Entity", content="desc", source="knowledge", score=0.8)
        ]


@pytest.mark.asyncio
async def test_knowledge_search_source_wraps_knowledge_service_search() -> None:
    from jarvis.services.search_sources import KnowledgeSearchSource

    source = KnowledgeSearchSource(_FakeKnowledgeService())

    results = await source.search("entity")

    assert source.source_type == "knowledge"
    assert results[0].id == "e1"


class _FakeIntelligenceService:
    async def search(self, query: str, *, top_k: int = 10):
        from jarvis.core.interfaces.search import SearchResult

        return [SearchResult(id="g1", title="Learn Rust", content="", source="goals", score=1.0)]


@pytest.mark.asyncio
async def test_goal_search_source_wraps_intelligence_service_search() -> None:
    from jarvis.services.search_sources import GoalSearchSource

    source = GoalSearchSource(_FakeIntelligenceService())

    results = await source.search("rust")

    assert source.source_type == "goals"
    assert results[0].id == "g1"


class _FakePluginManifest:
    def __init__(self, commands: list) -> None:
        self.commands = commands


class _FakeCommand:
    def __init__(self, id: str, description: str) -> None:
        self.id = id
        self.description = description


class _FakePluginRegistry:
    def __init__(self, manifests: list) -> None:
        self._manifests = manifests

    def list_manifests(self):
        return self._manifests


@pytest.mark.asyncio
async def test_command_search_source_matches_tools_and_plugin_commands() -> None:
    from jarvis.services.search_sources import CommandSearchSource

    tools = [("open_browser", "Opens the web browser")]
    plugin_registry = _FakePluginRegistry(
        [_FakePluginManifest([_FakeCommand("say_hello", "Says hello to the user")])]
    )
    source = CommandSearchSource(tools, plugin_registry=plugin_registry)

    browser_hits = await source.search("browser")
    assert len(browser_hits) == 1
    assert browser_hits[0].metadata["kind"] == "tool"

    hello_hits = await source.search("hello")
    assert len(hello_hits) == 1
    assert hello_hits[0].metadata["kind"] == "plugin_command"


@pytest.mark.asyncio
async def test_command_search_source_reads_plugin_registry_live() -> None:
    """A plugin registered *after* the source was constructed must still
    be searchable -- the registry is read fresh at query time, not
    snapshotted once at construction."""
    from jarvis.services.search_sources import CommandSearchSource

    plugin_registry = _FakePluginRegistry([])
    source = CommandSearchSource([], plugin_registry=plugin_registry)

    assert await source.search("newcommand") == []

    plugin_registry._manifests.append(
        _FakePluginManifest([_FakeCommand("newcommand", "A newly installed command")])
    )

    results = await source.search("newcommand")
    assert len(results) == 1


@pytest.mark.asyncio
async def test_command_search_source_without_plugin_registry() -> None:
    from jarvis.services.search_sources import CommandSearchSource

    source = CommandSearchSource([("do_thing", "Does a thing")], plugin_registry=None)

    results = await source.search("thing")
    assert len(results) == 1


@pytest.mark.asyncio
async def test_command_search_source_empty_query_returns_nothing() -> None:
    from jarvis.services.search_sources import CommandSearchSource

    source = CommandSearchSource([("do_thing", "Does a thing")])
    assert await source.search("") == []
