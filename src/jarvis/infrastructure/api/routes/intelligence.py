"""Intelligence Layer API -- Milestone 10B.

``/api/v1/goals`` (Goal Manager) and ``/api/v1/intelligence/*``
(Context Awareness, Predictive Suggestions, Daily Briefing, Preference
Learning) -- thin REST routes over ``IntelligenceService``, the domain
layer this router owns no state of its own.

Same ``Depends(get_current_session)`` Bearer auth + ``{data, meta}``
envelope convention as ``routes/plugins.py``/``routes/devtools.py``/
``routes/agent.py``/``routes/knowledge.py``.

``GET /api/v1/intelligence/briefing`` generates the Daily Briefing
on demand -- Milestone 7's Scheduler (Phase 6) does not exist yet, so
this route (or an agent tool) is the only way to produce one today;
firing it automatically on a configured schedule is explicit future
work once Phase 6 ships, not built here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from jarvis.infrastructure.api.auth import Envelope, envelope, get_current_session

if TYPE_CHECKING:
    from jarvis.services.intelligence_service import IntelligenceService

router = APIRouter(tags=["intelligence"], dependencies=[Depends(get_current_session)])


class CreateGoalRequest(BaseModel):
    title: str
    description: str = ""
    parent_goal_id: str | None = None


class UpdateGoalProgressRequest(BaseModel):
    progress_percent: int


class SetPreferenceRequest(BaseModel):
    key: str
    value: str
    source: str = "explicit"


def _intelligence(request: Request) -> IntelligenceService:
    return cast("IntelligenceService", request.app.state.container.intelligence_service())


def _goal_payload(goal: Any) -> dict[str, Any]:
    return {
        "id": goal.id,
        "title": goal.title,
        "description": goal.description,
        "status": goal.status,
        "progress_percent": goal.progress_percent,
        "parent_goal_id": goal.parent_goal_id,
        "target_date": goal.target_date.isoformat() if goal.target_date else None,
    }


# ---------------------------------------------------------------------------
# Goal Manager
# ---------------------------------------------------------------------------
@router.post("/goals", response_model=Envelope[dict[str, Any]], status_code=201)
async def create_goal(body: CreateGoalRequest, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        goal = await _intelligence(request).create_goal(
            body.title, description=body.description, parent_goal_id=body.parent_goal_id
        )
    except ServiceError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err
    return envelope(_goal_payload(goal))


@router.get("/goals", response_model=Envelope[tuple[dict[str, Any], ...]])
async def list_goals(
    request: Request, status: str | None = None, top_level_only: bool = False
) -> Envelope[tuple[dict[str, Any], ...]]:
    goals = await _intelligence(request).list_goals(status=status, top_level_only=top_level_only)
    payload = tuple(_goal_payload(g) for g in goals)
    return envelope(payload, meta={"count": len(payload)})


@router.get("/goals/{goal_id}", response_model=Envelope[dict[str, Any] | None])
async def get_goal(goal_id: str, request: Request) -> Envelope[dict[str, Any] | None]:
    detail = await _intelligence(request).get_goal_hierarchy(goal_id)
    if detail is None:
        return envelope(None, meta={"found": False})
    payload = _goal_payload(detail.goal)
    payload["children"] = [_goal_payload(c) for c in detail.children]
    return envelope(payload, meta={"found": True})


@router.patch("/goals/{goal_id}/progress", response_model=Envelope[dict[str, Any] | None])
async def update_goal_progress(
    goal_id: str, body: UpdateGoalProgressRequest, request: Request
) -> Envelope[dict[str, Any] | None]:
    goal = await _intelligence(request).update_goal_progress(goal_id, body.progress_percent)
    if goal is None:
        return envelope(None, meta={"found": False})
    return envelope(_goal_payload(goal), meta={"found": True})


@router.post("/goals/{goal_id}/complete", response_model=Envelope[dict[str, Any] | None])
async def complete_goal(goal_id: str, request: Request) -> Envelope[dict[str, Any] | None]:
    goal = await _intelligence(request).complete_goal(goal_id)
    if goal is None:
        return envelope(None, meta={"found": False})
    return envelope(_goal_payload(goal), meta={"found": True})


@router.delete("/goals/{goal_id}", response_model=Envelope[dict[str, bool]])
async def delete_goal(goal_id: str, request: Request) -> Envelope[dict[str, bool]]:
    await _intelligence(request).delete_goal(goal_id)
    return envelope({"deleted": True})


# ---------------------------------------------------------------------------
# Context Awareness / Predictive Suggestions / Daily Briefing
# ---------------------------------------------------------------------------
@router.get("/intelligence/context", response_model=Envelope[dict[str, Any]])
async def get_context(
    request: Request, conversation_id: str | None = None
) -> Envelope[dict[str, Any]]:
    signals = await _intelligence(request).get_context_signals(conversation_id=conversation_id)
    payload = {
        "hour_of_day": signals.hour_of_day,
        "day_of_week": signals.day_of_week,
        "recent_memory_snippets": signals.recent_memory_snippets,
        "active_conversation_id": signals.active_conversation_id,
    }
    return envelope(payload)


@router.get("/intelligence/suggestions", response_model=Envelope[tuple[dict[str, Any], ...]])
async def get_suggestions(request: Request, top_k: int = 5) -> Envelope[tuple[dict[str, Any], ...]]:
    suggestions = await _intelligence(request).predict_suggestions(top_k=top_k)
    payload = tuple(
        {"title": s.title, "reason": s.reason, "score": s.score, "kind": s.kind}
        for s in suggestions
    )
    return envelope(payload, meta={"count": len(payload)})


@router.get("/intelligence/briefing", response_model=Envelope[dict[str, Any]])
async def get_daily_briefing(request: Request) -> Envelope[dict[str, Any]]:
    briefing = await _intelligence(request).generate_daily_briefing()
    payload = {
        "generated_at": briefing.generated_at.isoformat(),
        "goals_due_soon": briefing.goals_due_soon,
        "top_suggestions": [
            {"title": s.title, "reason": s.reason, "score": s.score, "kind": s.kind}
            for s in briefing.top_suggestions
        ],
        "routine_reminders": briefing.routine_reminders,
    }
    return envelope(payload)


# ---------------------------------------------------------------------------
# Preference Learning
# ---------------------------------------------------------------------------
@router.post("/intelligence/preferences", response_model=Envelope[dict[str, Any]])
async def set_preference(body: SetPreferenceRequest, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        pref = await _intelligence(request).set_preference(body.key, body.value, source=body.source)
    except ServiceError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err
    return envelope(
        {"key": pref.key, "value": pref.value, "confidence": pref.confidence, "source": pref.source}
    )


@router.get("/intelligence/preferences", response_model=Envelope[tuple[dict[str, Any], ...]])
async def list_preferences(request: Request) -> Envelope[tuple[dict[str, Any], ...]]:
    prefs = await _intelligence(request).list_preferences()
    payload = tuple(
        {"key": p.key, "value": p.value, "confidence": p.confidence, "source": p.source}
        for p in prefs
    )
    return envelope(payload, meta={"count": len(payload)})


@router.get("/intelligence/preferences/{key}", response_model=Envelope[dict[str, Any] | None])
async def get_preference(key: str, request: Request) -> Envelope[dict[str, Any] | None]:
    pref = await _intelligence(request).get_preference(key)
    if pref is None:
        return envelope(None, meta={"found": False})
    payload = {
        "key": pref.key,
        "value": pref.value,
        "confidence": pref.confidence,
        "source": pref.source,
    }
    return envelope(payload, meta={"found": True})
