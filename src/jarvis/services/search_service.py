"""Search service — Milestone 10A, Universal Search.

The one query surface every other searchable JARVIS data source (memory,
knowledge graph, commands today; files, logs, settings, workspaces later)
queries through, rather than each maintaining its own index or its own
REST endpoint. Owns a provider registry
(``register_source``/``unregister_source``/``get_sources``) so a future
module or plugin can add a new :class:`~jarvis.core.interfaces.search.ISearchSource`
without this class ever changing -- no hardcoded source list, no
``isinstance`` dispatch on source type.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from jarvis.core.logging.logger import get_logger
from jarvis.utils.async_utils import gather_with_concurrency

if TYPE_CHECKING:
    from jarvis.core.interfaces.search import ISearchSource, SearchResult

_logger = get_logger("jarvis.services.search")

_MAX_CONCURRENT_SOURCES = 8


class SearchService:
    """Fans a query out to every registered :class:`ISearchSource`
    concurrently and merges the results."""

    def __init__(self) -> None:
        self._sources: dict[str, ISearchSource] = {}

    # ------------------------------------------------------------------
    # Provider registry
    # ------------------------------------------------------------------
    def register_source(self, source: ISearchSource) -> None:
        """Registers *source* under its own ``source_type``. Registering
        a second source with the same ``source_type`` replaces the first
        -- the same "last registration wins" semantics a plugin
        re-registering after a reload would expect."""
        self._sources[source.source_type] = source
        _logger.info("Search source registered: {}", source.source_type)

    def unregister_source(self, source_type: str) -> None:
        removed = self._sources.pop(source_type, None)
        if removed is not None:
            _logger.info("Search source unregistered: {}", source_type)

    def get_sources(self) -> list[ISearchSource]:
        return list(self._sources.values())

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------
    async def search(
        self,
        query: str,
        *,
        top_k: int = 20,
        source_types: set[str] | None = None,
    ) -> list[SearchResult]:
        """Fan out to every registered source (or only *source_types*
        when given), merge by score, return the top *top_k* overall.

        A single failing source is logged and excluded, never fails the
        whole query -- the same "one bad tool call must not crash the
        graph" posture ``agents/nodes/tool_executor.py`` already applies.
        """
        query = (query or "").strip()
        if not query:
            return []

        sources = [
            s
            for s in self._sources.values()
            if source_types is None or s.source_type in source_types
        ]
        if not sources:
            return []

        results_per_source = await gather_with_concurrency(
            _MAX_CONCURRENT_SOURCES,
            *(self._search_one(source, query, top_k) for source in sources),
        )

        merged: list[SearchResult] = [r for results in results_per_source for r in results]
        merged.sort(key=lambda r: r.score, reverse=True)
        return merged[:top_k]

    async def _search_one(
        self, source: ISearchSource, query: str, top_k: int
    ) -> list[SearchResult]:
        try:
            return await source.search(query, top_k=top_k)
        except Exception as err:  # a broken source must not break the query
            _logger.warning("Search source {!r} failed: {}", source.source_type, err)
            return []
