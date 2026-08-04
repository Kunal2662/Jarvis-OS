"""Intelligence service — Milestone 10B, Intelligence Layer.

The goal-tracking, routine/preference-learning, and predictive-
suggestion engine M15's Proactive Intelligence module (communication/
delivery layer, not started) and M16's Goal Reflection / Behaviour
Reflection modules (retrospective analysis layer, not started) will
both consume as their backing implementation, rather than each
maintaining its own. Deliberately not a duplicate of either -- this
milestone supplies data and deterministic ranking only, never a
delivery UI or a retrospective-analysis layer of its own.

Routine/Preference "learning" here is deliberately simple and
deterministic (direct observation + confidence reinforcement, plain
keyword matching for suggestion boosting) rather than ML-driven -- the
same posture M10A's own "AI reranking... deferred" scope note already
established for this codebase. A future milestone can add real
learning sophistication without this service's public API changing.

Daily Briefing is generated on demand (REST or agent tool), the same
"on-demand, not scheduled" posture M10A's Reflection Foundation
already established: M7's Scheduler (Phase 6) does not exist yet, so
firing this automatically on a configured schedule is explicit future
work, not built here -- wiring it up is a small, additive change once
Phase 6 ships, not a redesign.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from jarvis.core.exceptions import ServiceError
from jarvis.core.interfaces.search import SearchResult
from jarvis.core.logging.logger import get_logger
from jarvis.infrastructure.database.repositories import IntelligenceRepository

if TYPE_CHECKING:
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.interfaces.database import IDatabase
    from jarvis.infrastructure.database.models import Goal, Preference, Routine
    from jarvis.services.memory_service import MemoryService

_logger = get_logger("jarvis.services.intelligence")

_ROUTINE_SUGGESTION_MIN_OBSERVATIONS = 2
_GOAL_DUE_SOON_DAYS = 3
_PREFERENCE_BOOST_KEY_PREFIX = "suggestion_boost_keyword"
_PREFERENCE_BOOST_MULTIPLIER = 1.5


def _days_until(target: datetime, now: datetime) -> int:
    """SQLite (via SQLAlchemy's ``DateTime(timezone=True)``) round-trips a
    stored aware datetime back as a *naive* one -- a known dialect
    quirk, not specific to this table. Every datetime this service
    stores is UTC by convention (matching ``models.py``'s own
    ``_utcnow()`` helper), so a naive value here always means naive
    UTC; normalizing both sides before subtracting avoids
    ``TypeError: can't subtract offset-naive and offset-aware
    datetimes`` regardless of which side came from the database."""
    if target.tzinfo is None:
        target = target.replace(tzinfo=UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return (target - now).days


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class GoalDetail:
    goal: Goal
    children: list[Goal] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ContextSignals:
    """Signal aggregation feeding Predictive Suggestions. ``location`` is
    deliberately absent: no location provider exists anywhere in this
    codebase yet, so that signal the roadmap mentions ("time, location
    if granted, ...") is not available to aggregate -- not silently
    faked, just not included until a real provider exists."""

    hour_of_day: int
    day_of_week: int  # 0=Monday .. 6=Sunday, matching datetime.weekday()
    recent_memory_snippets: list[str]
    active_conversation_id: str | None = None


@dataclass(frozen=True, slots=True)
class Suggestion:
    title: str
    reason: str
    score: float
    kind: str  # "goal" | "routine"


@dataclass(frozen=True, slots=True)
class DailyBriefing:
    generated_at: datetime
    goals_due_soon: list[str]
    top_suggestions: list[Suggestion]
    routine_reminders: list[str]


class IntelligenceService:
    """Goal Manager, Routine/Preference Learning, Context Awareness,
    Predictive Suggestions, and on-demand Daily Briefing generation."""

    def __init__(
        self,
        database: IDatabase,
        memory: MemoryService,
        *,
        event_bus: EventBus | None = None,
    ) -> None:
        self._db = database
        self._memory = memory
        self._event_bus = event_bus

    # ------------------------------------------------------------------
    # Goal Manager
    # ------------------------------------------------------------------
    async def create_goal(
        self,
        title: str,
        *,
        description: str = "",
        parent_goal_id: str | None = None,
        target_date: datetime | None = None,
    ) -> Goal:
        title = (title or "").strip()
        if not title:
            raise ServiceError("Cannot create a goal with an empty title.")
        async with self._db.session() as sess:
            repo = IntelligenceRepository(sess)  # type: ignore[arg-type]
            if parent_goal_id is not None and await repo.get_goal(parent_goal_id) is None:
                raise ServiceError(f"Parent goal {parent_goal_id!r} does not exist.")
            goal = await repo.add_goal(
                title,
                description=description,
                parent_goal_id=parent_goal_id,
                target_date=target_date,
            )
        await self._publish_goal_updated(goal.id, action="created")
        return goal

    async def get_goal(self, goal_id: str) -> Goal | None:
        async with self._db.session() as sess:
            return await IntelligenceRepository(sess).get_goal(goal_id)  # type: ignore[arg-type]

    async def get_goal_hierarchy(self, goal_id: str) -> GoalDetail | None:
        async with self._db.session() as sess:
            repo = IntelligenceRepository(sess)  # type: ignore[arg-type]
            goal = await repo.get_goal(goal_id)
            if goal is None:
                return None
            children = await repo.list_child_goals(goal_id)
            return GoalDetail(goal=goal, children=children)

    async def list_goals(
        self, *, status: str | None = None, top_level_only: bool = False
    ) -> list[Goal]:
        async with self._db.session() as sess:
            repo = IntelligenceRepository(sess)  # type: ignore[arg-type]
            if top_level_only:
                return await repo.list_top_level_goals(status=status)
            return await repo.list_goals(status=status)

    async def update_goal_progress(self, goal_id: str, progress_percent: int) -> Goal | None:
        async with self._db.session() as sess:
            repo = IntelligenceRepository(sess)  # type: ignore[arg-type]
            goal = await repo.update_goal_progress(goal_id, progress_percent)
            if goal is not None and goal.progress_percent >= 100 and goal.status == "active":
                await repo.set_goal_status(goal_id, "completed")
                goal = await repo.get_goal(goal_id)
        if goal is None:
            return None
        await self._publish_goal_updated(goal_id, action="progress_updated")
        return goal

    async def complete_goal(self, goal_id: str) -> Goal | None:
        async with self._db.session() as sess:
            goal = await IntelligenceRepository(sess).set_goal_status(  # type: ignore[arg-type]
                goal_id, "completed"
            )
        if goal is None:
            return None
        await self._publish_goal_updated(goal_id, action="completed")
        return goal

    async def delete_goal(self, goal_id: str) -> None:
        async with self._db.session() as sess:
            await IntelligenceRepository(sess).delete_goal(goal_id)  # type: ignore[arg-type]
        await self._publish_goal_updated(goal_id, action="deleted")

    async def search(self, query: str, *, top_k: int = 10) -> list[SearchResult]:
        """``GoalSearchSource``'s backing method -- see
        ``services/search_sources.py``."""
        query = (query or "").strip()
        if not query:
            return []
        async with self._db.session() as sess:
            hits = await IntelligenceRepository(sess).search_goals(  # type: ignore[arg-type]
                query, limit=top_k
            )
        return [
            SearchResult(
                id=g.id,
                title=g.title,
                content=g.description,
                source="goals",
                score=1.0 if g.status == "active" else 0.5,
                uri=f"goal://{g.id}",
                metadata={"status": g.status, "progress_percent": g.progress_percent},
            )
            for g in hits
        ]

    # ------------------------------------------------------------------
    # Routine Learning
    # ------------------------------------------------------------------
    async def learn_routine(
        self, action_type: str, *, observed_at: datetime | None = None
    ) -> Routine:
        action_type = (action_type or "").strip()
        if not action_type:
            raise ServiceError("Cannot learn a routine with an empty action type.")
        observed_at = observed_at or datetime.now(UTC)
        hour, day = observed_at.hour, observed_at.weekday()
        async with self._db.session() as sess:
            repo = IntelligenceRepository(sess)  # type: ignore[arg-type]
            existing = await repo.find_matching_routine(
                action_type, hour_of_day=hour, day_of_week=day
            )
            if existing is not None:
                # `reinforce_routine` re-fetches by id within the same
                # session, so SQLAlchemy's identity map returns this same
                # tracked instance -- mutating it there mutates `existing`
                # here too, no re-fetch needed.
                await repo.reinforce_routine(existing.id)
                return existing
            return await repo.add_routine(action_type, hour_of_day=hour, day_of_week=day)

    # ------------------------------------------------------------------
    # Preference Learning
    # ------------------------------------------------------------------
    async def set_preference(
        self, key: str, value: str, *, source: str = "explicit", confidence: float = 0.9
    ) -> Preference:
        key = (key or "").strip()
        if not key:
            raise ServiceError("Cannot set a preference with an empty key.")
        async with self._db.session() as sess:
            return await IntelligenceRepository(sess).upsert_preference(  # type: ignore[arg-type]
                key, value, confidence=confidence, source=source
            )

    async def get_preference(self, key: str) -> Preference | None:
        async with self._db.session() as sess:
            return await IntelligenceRepository(sess).get_preference(key)  # type: ignore[arg-type]

    async def list_preferences(self) -> list[Preference]:
        async with self._db.session() as sess:
            return await IntelligenceRepository(sess).list_preferences()  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Context Awareness
    # ------------------------------------------------------------------
    async def get_context_signals(
        self, *, conversation_id: str | None = None, now: datetime | None = None
    ) -> ContextSignals:
        now = now or datetime.now(UTC)
        try:
            recent = await self._memory.browse(limit=5)
            snippets = [r.content for r in recent]
        except Exception as err:  # context assembly must never crash the caller
            _logger.warning("Context signal recent-activity lookup failed: {}", err)
            snippets = []
        return ContextSignals(
            hour_of_day=now.hour,
            day_of_week=now.weekday(),
            recent_memory_snippets=snippets,
            active_conversation_id=conversation_id,
        )

    # ------------------------------------------------------------------
    # Predictive Suggestions
    # ------------------------------------------------------------------
    async def predict_suggestions(
        self,
        *,
        top_k: int = 5,
        conversation_id: str | None = None,
        now: datetime | None = None,
    ) -> list[Suggestion]:
        now = now or datetime.now(UTC)
        context = await self.get_context_signals(conversation_id=conversation_id, now=now)

        async with self._db.session() as sess:
            repo = IntelligenceRepository(sess)  # type: ignore[arg-type]
            active_goals = await repo.list_goals(status="active")
            matching_routines = await repo.list_routines(
                hour_of_day=context.hour_of_day, day_of_week=context.day_of_week
            )
            boost_pref = await repo.get_preference(_PREFERENCE_BOOST_KEY_PREFIX)

        suggestions: list[Suggestion] = []
        for goal in active_goals:
            if goal.target_date is None:
                continue
            days_left = _days_until(goal.target_date, now)
            if 0 <= days_left <= _GOAL_DUE_SOON_DAYS:
                suggestions.append(
                    Suggestion(
                        title=f"Goal due soon: {goal.title}",
                        reason=f"target date in {days_left} day(s)",
                        score=0.9,
                        kind="goal",
                    )
                )

        for routine in matching_routines:
            if routine.observation_count < _ROUTINE_SUGGESTION_MIN_OBSERVATIONS:
                continue
            suggestions.append(
                Suggestion(
                    title=f"You often do this now: {routine.action_type}",
                    reason=f"observed {routine.observation_count} times at this time",
                    score=routine.confidence,
                    kind="routine",
                )
            )

        if boost_pref is not None and boost_pref.value:
            keyword = boost_pref.value.lower()
            suggestions = [
                (
                    Suggestion(
                        title=s.title,
                        reason=f"{s.reason} (boosted by your preference for {boost_pref.value!r})",
                        score=min(1.0, s.score * _PREFERENCE_BOOST_MULTIPLIER),
                        kind=s.kind,
                    )
                    if keyword in s.title.lower()
                    else s
                )
                for s in suggestions
            ]

        suggestions.sort(key=lambda s: s.score, reverse=True)
        return suggestions[:top_k]

    # ------------------------------------------------------------------
    # Daily Briefing (on-demand -- see module docstring)
    # ------------------------------------------------------------------
    async def generate_daily_briefing(self, *, now: datetime | None = None) -> DailyBriefing:
        now = now or datetime.now(UTC)
        async with self._db.session() as sess:
            active_goals = await IntelligenceRepository(sess).list_goals(  # type: ignore[arg-type]
                status="active"
            )
        goals_due_soon = [
            g.title
            for g in active_goals
            if g.target_date is not None
            and 0 <= _days_until(g.target_date, now) <= _GOAL_DUE_SOON_DAYS
        ]
        suggestions = await self.predict_suggestions(top_k=5, now=now)
        routine_reminders = [s.title for s in suggestions if s.kind == "routine"]

        briefing = DailyBriefing(
            generated_at=now,
            goals_due_soon=goals_due_soon,
            top_suggestions=suggestions,
            routine_reminders=routine_reminders,
        )
        await self._publish_briefing_generated()
        return briefing

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    async def _publish_goal_updated(self, goal_id: str, *, action: str) -> None:
        if self._event_bus is None:
            return
        from jarvis.core.events.events import GoalUpdatedEvent

        await self._event_bus.publish(GoalUpdatedEvent(goal_id=goal_id, action=action))

    async def _publish_briefing_generated(self) -> None:
        if self._event_bus is None:
            return
        from jarvis.core.events.events import DailyBriefingGeneratedEvent

        await self._event_bus.publish(DailyBriefingGeneratedEvent())
