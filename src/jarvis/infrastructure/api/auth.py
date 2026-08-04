"""``Depends(get_current_session)`` -- Milestone 9 Task Group E.

``docs/ARCHITECTURE.md`` sections 5/6 have referenced this exact
dependency by name since Task Group B (``sessions.py``, ``runtime_ws.py``
docstrings), but no route ever actually depended on it -- the only two
real REST routes that existed (``/api/v1/health``, ``/api/v1/sessions``)
are both documented, deliberate exceptions to needing it (health is
public by design; sessions is what issues the token every other route
needs). Task Group E's new routes (``routes/plugins.py``,
``routes/devtools.py``) are the first real REST resources built *after*
those two exceptions, so they are the first to actually use this
dependency -- resolving the "M10+ resource routes are expected to
follow this section exactly" note ``ARCHITECTURE.md`` section 5 left
for whoever added the next one.

Validates the same ``SessionManager`` session id
``runtime_ws.py``'s ``RuntimeWebSocketHub.authenticate()`` already
validates for the WebSocket -- one real session concept, two transports,
not two competing auth mechanisms. M14 (Security Platform) layers real
Bearer/JWT semantics on top of this same contract later without
changing it, exactly as ``runtime_ws.py``'s own docstring already
promises for the WebSocket side.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from fastapi import Header, HTTPException, Request
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from jarvis.core.lifecycle.session_manager import SessionInfo, SessionManager

_UNAUTHORIZED_DETAIL = "Missing, malformed, or invalid/expired session token."


async def get_current_session(
    request: Request, authorization: str | None = Header(default=None)
) -> SessionInfo:
    """The real Bearer-auth dependency ``docs/ARCHITECTURE.md`` section
    5 calls for: ``Authorization: Bearer <session_id>``, validated
    against the real ``SessionManager`` (Task Group B) every other
    route ultimately shares. Raises ``401`` for a missing header, a
    malformed scheme, or a session id ``SessionManager`` doesn't
    recognize (expired, closed, or never issued) -- never distinguishes
    *which* of those three to an unauthenticated caller, matching
    standard practice for not leaking which failure mode occurred."""
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail=_UNAUTHORIZED_DETAIL)
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail=_UNAUTHORIZED_DETAIL)

    session_manager = cast("SessionManager", request.app.state.container.session_manager())
    info = session_manager.get(token)
    if info is None:
        raise HTTPException(status_code=401, detail=_UNAUTHORIZED_DETAIL)
    return info


# ---------------------------------------------------------------------------
# {data, meta} envelope -- docs/ARCHITECTURE.md section 5's "Request /
# response schema", made real for the first time by these same routes.
# ---------------------------------------------------------------------------
class Envelope[T](BaseModel):
    data: T
    meta: dict[str, Any] = Field(default_factory=dict)


def envelope[T](data: T, *, meta: dict[str, Any] | None = None) -> Envelope[T]:
    return Envelope[T](data=data, meta=meta or {})
