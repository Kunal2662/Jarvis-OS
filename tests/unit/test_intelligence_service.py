"""Unit tests for :class:`IntelligenceService` — Milestone 10B.

Real (temp-file) SQLite database, matching
``test_knowledge_service.py``'s established pattern.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest


def _settings(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JARVIS_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'jarvis.db'}")
    monkeypatch.setenv("JARVIS_OPENAI_ENABLED", "false")
    monkeypatch.setenv("JARVIS_OLLAMA_ENABLED", "true")

    from jarvis.core.config import settings as settings_mod

    settings_mod.load_settings.cache_clear()  # type: ignore[attr-defined]
    return settings_mod.load_settings()


class _FakeMemoryService:
    async def browse(self, *, limit: int = 200, **kwargs):
        return []


@pytest.fixture
async def env(tmp_path: Path, monkeypatch):
    settings = _settings(tmp_path, monkeypatch)
    from jarvis.infrastructure.database.sqlite_client import SQLiteDatabase

    db = SQLiteDatabase(settings.db)
    await db.initialize()
    try:
        yield db, _FakeMemoryService()
    finally:
        await db.dispose()


_FIXED_TIME = datetime(2026, 8, 4, 9, 0, tzinfo=UTC)  # Tuesday 09:00 UTC


# ---------------------------------------------------------------------------
# Acceptance Criterion 1 -- Goal Manager persists a goal across sessions
# with measurable progress tracking.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_goal_persists_across_sessions_with_progress_tracking(env) -> None:
    from jarvis.services.intelligence_service import IntelligenceService

    db, memory = env
    svc = IntelligenceService(database=db, memory=memory)

    goal = await svc.create_goal("Learn Rust", description="side project")
    assert goal.status == "active"
    assert goal.progress_percent == 0

    # A fresh service instance -- proves persistence, not in-memory state.
    svc2 = IntelligenceService(database=db, memory=memory)
    updated = await svc2.update_goal_progress(goal.id, 60)
    assert updated.progress_percent == 60

    svc3 = IntelligenceService(database=db, memory=memory)
    fetched = await svc3.get_goal(goal.id)
    assert fetched is not None
    assert fetched.progress_percent == 60
    assert fetched.title == "Learn Rust"


@pytest.mark.asyncio
async def test_goal_auto_completes_at_100_percent(env) -> None:
    from jarvis.services.intelligence_service import IntelligenceService

    db, memory = env
    svc = IntelligenceService(database=db, memory=memory)
    goal = await svc.create_goal("Finish report")

    updated = await svc.update_goal_progress(goal.id, 100)
    assert updated.status == "completed"


@pytest.mark.asyncio
async def test_create_goal_rejects_empty_title(env) -> None:
    from jarvis.core.exceptions import ServiceError
    from jarvis.services.intelligence_service import IntelligenceService

    db, memory = env
    svc = IntelligenceService(database=db, memory=memory)
    with pytest.raises(ServiceError):
        await svc.create_goal("   ")


@pytest.mark.asyncio
async def test_goal_hierarchy(env) -> None:
    from jarvis.services.intelligence_service import IntelligenceService

    db, memory = env
    svc = IntelligenceService(database=db, memory=memory)
    parent = await svc.create_goal("Get fit")
    await svc.create_goal("Run 5k", parent_goal_id=parent.id)

    detail = await svc.get_goal_hierarchy(parent.id)
    assert detail is not None
    assert len(detail.children) == 1
    assert detail.children[0].title == "Run 5k"


@pytest.mark.asyncio
async def test_create_goal_rejects_nonexistent_parent(env) -> None:
    from jarvis.core.exceptions import ServiceError
    from jarvis.services.intelligence_service import IntelligenceService

    db, memory = env
    svc = IntelligenceService(database=db, memory=memory)
    with pytest.raises(ServiceError):
        await svc.create_goal("Child", parent_goal_id="does-not-exist")


@pytest.mark.asyncio
async def test_goal_search(env) -> None:
    from jarvis.services.intelligence_service import IntelligenceService

    db, memory = env
    svc = IntelligenceService(database=db, memory=memory)
    await svc.create_goal("Learn Spanish", description="for the trip")

    results = await svc.search("Spanish")
    assert len(results) == 1
    assert results[0].source == "goals"
    assert results[0].title == "Learn Spanish"


# ---------------------------------------------------------------------------
# Acceptance Criterion 2 -- a learned routine or preference measurably
# changes a future Predictive Suggestion.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_learned_routine_changes_future_suggestion(env) -> None:
    from jarvis.services.intelligence_service import IntelligenceService

    db, memory = env
    svc = IntelligenceService(database=db, memory=memory)

    before = await svc.predict_suggestions(now=_FIXED_TIME)
    assert not any(s.kind == "routine" for s in before)

    await svc.learn_routine("make_coffee", observed_at=_FIXED_TIME)
    await svc.learn_routine("make_coffee", observed_at=_FIXED_TIME)  # reinforce past the threshold

    after = await svc.predict_suggestions(now=_FIXED_TIME)
    assert any(s.kind == "routine" and "make_coffee" in s.title for s in after)


@pytest.mark.asyncio
async def test_single_observation_does_not_yet_suggest(env) -> None:
    """A routine needs reinforcement (>=2 observations) before it
    surfaces -- a single sighting is noise, not yet a pattern."""
    from jarvis.services.intelligence_service import IntelligenceService

    db, memory = env
    svc = IntelligenceService(database=db, memory=memory)
    await svc.learn_routine("make_coffee", observed_at=_FIXED_TIME)

    suggestions = await svc.predict_suggestions(now=_FIXED_TIME)
    assert not any(s.kind == "routine" for s in suggestions)


@pytest.mark.asyncio
async def test_learned_preference_boosts_matching_suggestion_score(env) -> None:
    from jarvis.services.intelligence_service import IntelligenceService

    db, memory = env
    svc = IntelligenceService(database=db, memory=memory)
    await svc.create_goal("Exercise more", target_date=datetime(2026, 8, 5, tzinfo=UTC))

    base = await svc.predict_suggestions(now=_FIXED_TIME)
    base_score = next(s.score for s in base if "Exercise" in s.title)

    await svc.set_preference("suggestion_boost_keyword", "exercise")

    boosted = await svc.predict_suggestions(now=_FIXED_TIME)
    boosted_score = next(s.score for s in boosted if "Exercise" in s.title)

    assert boosted_score > base_score


@pytest.mark.asyncio
async def test_routine_learning_is_time_slotted(env) -> None:
    """A routine reinforced at 9am on Tuesday must not surface for an
    unrelated time slot -- proves the context signal actually gates the
    suggestion, not just "any routine exists"."""
    from jarvis.services.intelligence_service import IntelligenceService

    db, memory = env
    svc = IntelligenceService(database=db, memory=memory)
    await svc.learn_routine("make_coffee", observed_at=_FIXED_TIME)
    await svc.learn_routine("make_coffee", observed_at=_FIXED_TIME)

    unrelated_time = datetime(2026, 8, 5, 22, 0, tzinfo=UTC)  # Wednesday 10pm
    suggestions = await svc.predict_suggestions(now=unrelated_time)
    assert not any(s.kind == "routine" and "make_coffee" in s.title for s in suggestions)


@pytest.mark.asyncio
async def test_set_preference_rejects_empty_key(env) -> None:
    from jarvis.core.exceptions import ServiceError
    from jarvis.services.intelligence_service import IntelligenceService

    db, memory = env
    svc = IntelligenceService(database=db, memory=memory)
    with pytest.raises(ServiceError):
        await svc.set_preference("   ", "value")


# ---------------------------------------------------------------------------
# Acceptance Criterion 3 -- Daily Briefing content generation (on-demand;
# automatic scheduling deferred pending M7 Phase 6, see module docstring).
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_daily_briefing_includes_goals_due_soon(env) -> None:
    from jarvis.services.intelligence_service import IntelligenceService

    db, memory = env
    svc = IntelligenceService(database=db, memory=memory)
    await svc.create_goal("Submit taxes", target_date=datetime(2026, 8, 6, tzinfo=UTC))
    await svc.create_goal("Long-term project", target_date=datetime(2027, 1, 1, tzinfo=UTC))

    briefing = await svc.generate_daily_briefing(now=_FIXED_TIME)

    assert "Submit taxes" in briefing.goals_due_soon
    assert "Long-term project" not in briefing.goals_due_soon


@pytest.mark.asyncio
async def test_daily_briefing_includes_routine_reminders(env) -> None:
    from jarvis.services.intelligence_service import IntelligenceService

    db, memory = env
    svc = IntelligenceService(database=db, memory=memory)
    await svc.learn_routine("make_coffee", observed_at=_FIXED_TIME)
    await svc.learn_routine("make_coffee", observed_at=_FIXED_TIME)

    briefing = await svc.generate_daily_briefing(now=_FIXED_TIME)
    assert any("make_coffee" in r for r in briefing.routine_reminders)


# ---------------------------------------------------------------------------
# Context Awareness
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_context_signals_tolerates_memory_failure(env) -> None:
    from jarvis.services.intelligence_service import IntelligenceService

    class _BrokenMemory:
        async def browse(self, *, limit: int = 200, **kwargs):
            raise RuntimeError("db unavailable")

    db, _memory = env
    svc = IntelligenceService(database=db, memory=_BrokenMemory())

    signals = await svc.get_context_signals(now=_FIXED_TIME)
    assert signals.recent_memory_snippets == []
    assert signals.hour_of_day == 9
    assert signals.day_of_week == 1  # Tuesday
