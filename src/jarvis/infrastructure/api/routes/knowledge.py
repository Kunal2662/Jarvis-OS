"""Universal Search & Knowledge Platform API -- Milestone 10A.

``POST /api/v1/search`` (Universal Search, fanning out across every
registered :class:`~jarvis.core.interfaces.search.ISearchSource`) and
``/api/v1/knowledge/*`` (entity lookup, correction, learn-on-demand,
export/import) -- thin REST routes over ``SearchService``/
``KnowledgeService``, the domain layer this router owns no state of its
own.

Same ``Depends(get_current_session)`` Bearer auth + ``{data, meta}``
envelope convention as ``routes/plugins.py``/``routes/devtools.py``/
``routes/agent.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from jarvis.infrastructure.api.auth import Envelope, envelope, get_current_session

if TYPE_CHECKING:
    from jarvis.services.knowledge_service import KnowledgeService
    from jarvis.services.search_service import SearchService

router = APIRouter(tags=["knowledge"], dependencies=[Depends(get_current_session)])


class SearchRequest(BaseModel):
    query: str
    top_k: int = 20
    source_types: list[str] | None = None


class CorrectRequest(BaseModel):
    statement: str


class ImportRequest(BaseModel):
    data: str


def _search_service(request: Request) -> SearchService:
    return cast("SearchService", request.app.state.container.search_service())


def _knowledge_service(request: Request) -> KnowledgeService:
    return cast("KnowledgeService", request.app.state.container.knowledge_service())


# ---------------------------------------------------------------------------
# Universal Search
# ---------------------------------------------------------------------------
@router.post("/search", response_model=Envelope[tuple[dict[str, Any], ...]])
async def search(body: SearchRequest, request: Request) -> Envelope[tuple[dict[str, Any], ...]]:
    service = _search_service(request)
    source_types = set(body.source_types) if body.source_types else None
    results = await service.search(body.query, top_k=body.top_k, source_types=source_types)
    payload = tuple(
        {
            "id": r.id,
            "title": r.title,
            "content": r.content,
            "source": r.source,
            "score": r.score,
            "confidence": r.confidence,
            "reason": r.reason,
            "uri": r.uri,
            "metadata": r.metadata,
        }
        for r in results
    )
    sources = sorted({s.source_type for s in service.get_sources()})
    return envelope(payload, meta={"count": len(payload), "sources": sources})


# ---------------------------------------------------------------------------
# Knowledge Graph
# ---------------------------------------------------------------------------
@router.get("/knowledge/entities/{name}", response_model=Envelope[dict[str, Any] | None])
async def get_entity(name: str, request: Request) -> Envelope[dict[str, Any] | None]:
    detail = await _knowledge_service(request).get_entity_detail(name)
    if detail is None:
        return envelope(None, meta={"found": False})
    payload = {
        "id": detail.id,
        "name": detail.name,
        "entity_type": detail.entity_type,
        "description": detail.description,
        "confidence": detail.confidence,
        "relationships": [
            {
                "predicate": r.predicate,
                "other_entity": r.other_entity,
                "direction": r.direction,
                "confidence": r.confidence,
            }
            for r in detail.relationships
        ],
        "memory_contents": detail.memory_contents,
    }
    return envelope(payload, meta={"found": True})


@router.get("/knowledge/ask", response_model=Envelope[dict[str, str]])
async def ask(query: str, request: Request) -> Envelope[dict[str, str]]:
    answer = await _knowledge_service(request).ask(query)
    return envelope({"answer": answer})


@router.post("/knowledge/correct", response_model=Envelope[dict[str, int]])
async def correct(body: CorrectRequest, request: Request) -> Envelope[dict[str, int]]:
    result = await _knowledge_service(request).correct(body.statement)
    payload = {
        "entities_touched": result.entities_touched,
        "relationships_superseded": result.relationships_superseded,
        "relationships_created": result.relationships_created,
    }
    return envelope(payload)


@router.post("/knowledge/learn", response_model=Envelope[dict[str, int]])
async def learn(request: Request, limit: int = 20) -> Envelope[dict[str, int]]:
    """On-demand batch extraction over recent memories -- the Reflection
    Foundation capability, triggered here or by an operator/agent, never
    by a background scheduler (explicitly out of scope for Milestone 10A)."""
    result = await _knowledge_service(request).learn_from_recent_memories(limit=limit)
    payload = {
        "entities_created": result.entities_created,
        "relationships_created": result.relationships_created,
    }
    return envelope(payload)


@router.get("/knowledge/export", response_model=Envelope[dict[str, Any]])
async def export_graph(request: Request) -> Envelope[dict[str, Any]]:
    import json

    data = await _knowledge_service(request).export_graph()
    return envelope(cast(dict[str, Any], json.loads(data)))


@router.post("/knowledge/import", response_model=Envelope[dict[str, int]])
async def import_graph(body: ImportRequest, request: Request) -> Envelope[dict[str, int]]:
    result = await _knowledge_service(request).import_graph(body.data)
    payload = {
        "entities_created": result.entities_created,
        "relationships_created": result.relationships_created,
    }
    return envelope(payload)
