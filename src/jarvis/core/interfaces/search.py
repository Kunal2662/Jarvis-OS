"""Universal Search port (Milestone 10A).

:class:`ISearchSource` is the seam every searchable subsystem plugs into
-- memory, the knowledge graph, agent/plugin commands today; files, logs,
settings, and workspaces (M11B and later) without changing
:class:`~jarvis.services.search_service.SearchService` itself, the same
"port + adapter" shape every other cross-cutting capability in this
codebase already uses (:class:`~jarvis.core.interfaces.vector_store.IVectorStore`,
:class:`~jarvis.core.interfaces.llm_provider.ILLMProvider`, ...).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class SearchResult:
    """One result from one :class:`ISearchSource`.

    Deliberately extensible: ``confidence`` and ``reason`` carry no
    meaning yet (always ``1.0`` / ``""`` respectively until a future
    milestone adds real AI reranking) but exist now so that milestone
    can populate them without changing this model's shape or any
    caller's field access.
    """

    id: str
    title: str
    content: str
    source: str
    score: float
    confidence: float = 1.0
    reason: str = ""
    uri: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ISearchSource(Protocol):
    """Abstract search provider. One instance per searchable subsystem,
    registered with :class:`~jarvis.services.search_service.SearchService`
    via ``register_source()`` -- never imported or special-cased by name
    inside ``SearchService`` itself."""

    #: Stable identifier used as ``SearchResult.source`` and as the key
    #: callers pass to filter by source type (e.g. ``source_types={"memory"}``).
    source_type: str

    async def search(self, query: str, *, top_k: int = 10) -> list[SearchResult]: ...
