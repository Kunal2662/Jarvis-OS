"""Runtime session issuance -- the real, minimal precursor to the
``Depends(get_current_session)`` mechanism ``docs/ARCHITECTURE.md``
sections 5/6 reference (Milestone 9 Task Group B). Not M14's full
Bearer/JWT auth (future work, see ``runtime_ws.py``'s module
docstring) -- issues and reads back a
:class:`~jarvis.core.lifecycle.session_manager.SessionManager` session,
the one real session concept this task group builds. A session id
returned here is the ``token`` query param ``/api/v1/ws`` expects.

**Response shape (changed Aug 2026, backlog pass).** These routes now
return the ``{data, meta}`` envelope ``docs/ARCHITECTURE.md`` §5
mandates, like every other resource route. They were the last holdout:
§15 deferred the change while ``/sessions`` was the *only* real
resource route, on the reasoning that adopting a wrapper before a
second route proved the pattern risked getting it wrong and changing it
twice. Six route modules now use the envelope consistently, so that
reasoning has expired and the inconsistency was the only thing left.

Callers read ``response.json()["data"]["session_id"]`` where they
previously read ``response.json()["session_id"]``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from jarvis.infrastructure.api.auth import Envelope, envelope

if TYPE_CHECKING:
    from jarvis.core.lifecycle.session_manager import SessionManager

router = APIRouter(tags=["sessions"])


class CreateSessionRequest(BaseModel):
    conversation_id: str | None = None
    thread_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionResponse(BaseModel):
    session_id: str
    conversation_id: str | None
    thread_id: str | None
    created_at: str
    last_active_at: str


def _session_manager(request: Request) -> SessionManager:
    return cast("SessionManager", request.app.state.container.session_manager())


def _to_response(info: Any) -> SessionResponse:
    return SessionResponse(
        session_id=info.session_id,
        conversation_id=info.conversation_id,
        thread_id=info.thread_id,
        created_at=info.created_at.isoformat(),
        last_active_at=info.last_active_at.isoformat(),
    )


@router.post("/sessions", response_model=Envelope[SessionResponse], status_code=201)
async def create_session(body: CreateSessionRequest, request: Request) -> Envelope[SessionResponse]:
    from jarvis.core.exceptions import ServiceError

    manager = _session_manager(request)
    try:
        info = await manager.create(
            conversation_id=body.conversation_id,
            thread_id=body.thread_id,
            metadata=body.metadata,
        )
    except ServiceError as err:
        # An unknown `conversation_id` is a bad request, not a server
        # fault. Before the Aug 2026 integrity pass enabled foreign-key
        # enforcement this wrote a session pointing at nothing and still
        # returned 201.
        raise HTTPException(status_code=400, detail=str(err)) from err
    return envelope(_to_response(info), meta={"created": True})


@router.get("/sessions/{session_id}", response_model=Envelope[SessionResponse])
async def get_session(session_id: str, request: Request) -> Envelope[SessionResponse]:
    manager = _session_manager(request)
    info = manager.get(session_id)
    if info is None:
        raise HTTPException(status_code=404, detail="Session not found or already closed.")
    return envelope(_to_response(info))


@router.delete("/sessions/{session_id}", status_code=204)
async def close_session(session_id: str, request: Request) -> None:
    manager = _session_manager(request)
    if manager.get(session_id) is None:
        raise HTTPException(status_code=404, detail="Session not found or already closed.")
    await manager.close(session_id)
