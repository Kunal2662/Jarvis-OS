"""AI Workspace API -- Milestone 11 Task Group D.

``/api/v1/workspace-ai/{workspace_id}/*`` and
``/api/v1/knowledge-links`` -- thin REST over
``WorkspaceAssistantService`` and ``WorkspaceKnowledgeService``, with
the same ``Depends(get_current_session)`` Bearer auth and ``{data,
meta}`` envelope every resource router since M9 Task Group E uses. This
one owns no state and no logic of its own.

**Two prefixes, not one.** ``workspace-ai`` is a set of *operations on*
one workspace (assemble its context, retrieve inside it, ask about it,
ingest it) and is therefore addressed workspace-first.
``knowledge-links`` is a *resource* with its own ids, and a caller
holding a link id should not need its workspace's to delete it -- the
same reasoning that put notes at ``/notes`` rather than under
``/workspaces/{id}/notes`` in Task Group A.

**Assist is a POST even though it reads nothing.** It calls a model,
which costs real time and, for a hosted provider, real money, and it
takes a question that has no business in a URL. GET would also invite
caching a non-deterministic response.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from jarvis.infrastructure.api.auth import Envelope, envelope, get_current_session
from jarvis.infrastructure.api.pagination import Page, page_meta, page_params

if TYPE_CHECKING:
    from jarvis.infrastructure.database.models import WorkspaceKnowledgeLink
    from jarvis.services.workspace_ai_service import (
        WorkspaceAssistantService,
        WorkspaceKnowledgeService,
    )

router = APIRouter(tags=["ai-workspace"], dependencies=[Depends(get_current_session)])


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------
class AssistRequest(BaseModel):
    mode: str = "summarize"
    question: str = ""
    top_k: int | None = None
    budget_chars: int | None = None


class IngestRequest(BaseModel):
    include_notes: bool = True
    include_files: bool = True
    limit: int = 50


class CreateLinkRequest(BaseModel):
    workspace_id: str
    entity_id: str
    target: str = "workspace"
    target_id: str | None = None
    source: str = "manual"
    confidence: float = 0.7


# ---------------------------------------------------------------------------
# Resolution + serialization
# ---------------------------------------------------------------------------
def _assistant(request: Request) -> WorkspaceAssistantService:
    return cast(
        "WorkspaceAssistantService", request.app.state.container.workspace_assistant_service()
    )


def _knowledge(request: Request) -> WorkspaceKnowledgeService:
    return cast(
        "WorkspaceKnowledgeService", request.app.state.container.workspace_knowledge_service()
    )


def _link_payload(link: WorkspaceKnowledgeLink) -> dict[str, Any]:
    from jarvis.services.workspace_ai_service import describe_link_target

    target, target_id = describe_link_target(link)
    return {
        "id": link.id,
        "workspace_id": link.workspace_id,
        "entity_id": link.entity_id,
        "target": target,
        "target_id": target_id,
        "source": link.source,
        "confidence": link.confidence,
        "created_at": link.created_at.isoformat() if link.created_at else None,
    }


def _bad_request(err: Exception) -> HTTPException:
    """``ServiceError`` means the caller asked for something invalid --
    an unknown mode, a link spanning two workspaces, a question-less
    question. 400, not 500: nothing broke."""
    return HTTPException(status_code=400, detail=str(err))


# ---------------------------------------------------------------------------
# Workspace AI
# ---------------------------------------------------------------------------
@router.get("/workspace-ai/{workspace_id}/context", response_model=Envelope[dict[str, Any]])
async def workspace_ai_context(
    workspace_id: str, request: Request, budget_chars: int | None = None
) -> Envelope[dict[str, Any]]:
    """One workspace's full state, ordered and packed into a character
    budget -- the payload the assistant prompts from, so a caller can
    see exactly what a model was shown."""
    from jarvis.core.exceptions import ServiceError

    try:
        context = await _assistant(request).context(workspace_id, budget_chars=budget_chars)
    except ServiceError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    return envelope(
        context.as_dict(),
        meta={"used_chars": context.used_chars, "budget_chars": context.budget_chars},
    )


@router.get("/workspace-ai/{workspace_id}/retrieve", response_model=Envelope[list[dict[str, Any]]])
async def workspace_ai_retrieve(
    workspace_id: str,
    request: Request,
    q: str = Query(..., description="What to look for inside this workspace."),
    top_k: int = 10,
    include_global: bool = False,
) -> Envelope[list[dict[str, Any]]]:
    """Search inside one workspace, through the shared search index.

    ``include_global`` opts the sources with no workspace notion
    (memory, knowledge, goals, commands) back in; they are excluded by
    default because a scoped question deserves a scoped answer.
    """
    from jarvis.core.exceptions import ServiceError

    try:
        results = await _assistant(request).retrieve(
            workspace_id, q, top_k=top_k, include_global=include_global
        )
    except ServiceError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    payload = [
        {
            "id": result.id,
            "title": result.title,
            "content": result.content,
            "source": result.source,
            "score": result.score,
            "uri": result.uri,
            "metadata": result.metadata,
        }
        for result in results
    ]
    return envelope(payload, meta={"count": len(payload), "query": q})


@router.post("/workspace-ai/{workspace_id}/assist", response_model=Envelope[dict[str, Any]])
async def workspace_ai_assist(
    workspace_id: str, body: AssistRequest, request: Request
) -> Envelope[dict[str, Any]]:
    """Summarize, ask about, or propose next actions for one workspace.

    ``meta.synthesized`` is ``false`` when no LLM answered and the
    payload is the assembled context returned verbatim -- a degraded
    answer, reported as one rather than dressed up as a real reply.
    """
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _assistant(request).assist(
            workspace_id,
            mode=body.mode,
            question=body.question,
            top_k=body.top_k,
            budget_chars=body.budget_chars,
        )
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(
        result.as_dict(),
        meta={"synthesized": result.synthesized, "citations": len(result.citations)},
    )


@router.post("/workspace-ai/{workspace_id}/ingest", response_model=Envelope[dict[str, Any]])
async def workspace_ai_ingest(
    workspace_id: str, body: IngestRequest, request: Request
) -> Envelope[dict[str, Any]]:
    """Run knowledge extraction over this workspace's prose and record
    what it is about.

    On demand only -- nothing schedules this. Re-running replaces what
    was previously *extracted* for each target and leaves ``manual``
    links alone.
    """
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _knowledge(request).ingest_workspace(
            workspace_id,
            include_notes=body.include_notes,
            include_files=body.include_files,
            limit=body.limit,
        )
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(result.as_dict(), meta={"workspace_id": workspace_id})


@router.get("/workspace-ai/{workspace_id}/entities", response_model=Envelope[list[dict[str, Any]]])
async def workspace_ai_entities(
    workspace_id: str, request: Request, limit: int = 50
) -> Envelope[list[dict[str, Any]]]:
    """The knowledge entities this workspace is recorded to be about,
    most-linked first."""
    entities = await _knowledge(request).entities_for(workspace_id, limit=limit)
    return envelope(entities, meta={"count": len(entities)})


# ---------------------------------------------------------------------------
# Knowledge links
# ---------------------------------------------------------------------------
@router.post("/knowledge-links", response_model=Envelope[dict[str, Any]], status_code=201)
async def create_knowledge_link(
    body: CreateLinkRequest, request: Request
) -> Envelope[dict[str, Any]]:
    """Assert that something in a workspace is about a knowledge entity.

    Idempotent: linking the same pair twice returns the existing row,
    and asserting one the extractor had already found promotes it to
    ``manual`` so a later re-ingestion cannot remove it. ``201`` either
    way -- the caller's intent was to have the link exist, and it does.
    """
    from jarvis.core.exceptions import ServiceError

    try:
        link = await _knowledge(request).link(
            body.workspace_id,
            body.entity_id,
            target=body.target,
            target_id=body.target_id,
            source=body.source,
            confidence=body.confidence,
        )
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(_link_payload(link), meta={"created": True})


@router.get("/knowledge-links", response_model=Envelope[list[dict[str, Any]]])
async def list_knowledge_links(
    request: Request,
    workspace_id: str | None = None,
    entity_id: str | None = None,
    target: str | None = None,
    target_id: str | None = None,
    source: str | None = None,
    page: Page = Depends(page_params),
) -> Envelope[list[dict[str, Any]]]:
    from jarvis.core.exceptions import ServiceError

    try:
        rows = await _knowledge(request).list_links(
            workspace_id=workspace_id,
            entity_id=entity_id,
            target=target,
            target_id=target_id,
            source=source,
            limit=page.probe_limit,
            offset=page.offset,
        )
    except ServiceError as err:
        raise _bad_request(err) from err
    rows, has_more = page.trim(rows)
    payload = [_link_payload(link) for link in rows]
    return envelope(payload, meta=page_meta(page=page, count=len(payload), has_more=has_more))


@router.get("/knowledge-links/{link_id}", response_model=Envelope[dict[str, Any]])
async def get_knowledge_link(link_id: str, request: Request) -> Envelope[dict[str, Any]]:
    link = await _knowledge(request).get_link(link_id)
    if link is None:
        raise HTTPException(status_code=404, detail="Knowledge link not found.")
    return envelope(_link_payload(link))


@router.delete("/knowledge-links/{link_id}", status_code=204)
async def delete_knowledge_link(link_id: str, request: Request) -> None:
    if not await _knowledge(request).unlink(link_id):
        raise HTTPException(status_code=404, detail="Knowledge link not found.")
