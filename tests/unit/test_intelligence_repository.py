"""Unit tests for :class:`IntelligenceRepository` — Milestone 10B.

Real (temp-file) SQLite database via :class:`SQLiteDatabase`, matching
``test_knowledge_repository.py``'s established pattern.
"""

from __future__ import annotations

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


@pytest.fixture
async def db(tmp_path: Path, monkeypatch):
    settings = _settings(tmp_path, monkeypatch)
    from jarvis.infrastructure.database.sqlite_client import SQLiteDatabase

    database = SQLiteDatabase(settings.db)
    await database.initialize()
    try:
        yield database
    finally:
        await database.dispose()


# ---------------------------------------------------------------------------
# Goals
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_add_and_get_goal(db) -> None:
    from jarvis.infrastructure.database.repositories import IntelligenceRepository

    async with db.session() as sess:
        repo = IntelligenceRepository(sess)
        goal = await repo.add_goal("Learn Rust", description="side project")

    async with db.session() as sess:
        repo = IntelligenceRepository(sess)
        fetched = await repo.get_goal(goal.id)
        assert fetched is not None
        assert fetched.title == "Learn Rust"
        assert fetched.status == "active"
        assert fetched.progress_percent == 0


@pytest.mark.asyncio
async def test_goal_hierarchy(db) -> None:
    from jarvis.infrastructure.database.repositories import IntelligenceRepository

    async with db.session() as sess:
        repo = IntelligenceRepository(sess)
        parent = await repo.add_goal("Get fit")
        await repo.add_goal("Run 5k", parent_goal_id=parent.id)
        await repo.add_goal("Eat healthy", parent_goal_id=parent.id)

    async with db.session() as sess:
        repo = IntelligenceRepository(sess)
        children = await repo.list_child_goals(parent.id)
        assert {c.title for c in children} == {"Run 5k", "Eat healthy"}
        top_level = await repo.list_top_level_goals()
        assert [g.title for g in top_level] == ["Get fit"]


@pytest.mark.asyncio
async def test_update_goal_progress_and_status(db) -> None:
    from jarvis.infrastructure.database.repositories import IntelligenceRepository

    async with db.session() as sess:
        repo = IntelligenceRepository(sess)
        goal = await repo.add_goal("Write a book")
        await repo.update_goal_progress(goal.id, 150)  # clamped to 100

    async with db.session() as sess:
        repo = IntelligenceRepository(sess)
        fetched = await repo.get_goal(goal.id)
        assert fetched.progress_percent == 100

        await repo.set_goal_status(goal.id, "completed")

    async with db.session() as sess:
        repo = IntelligenceRepository(sess)
        completed = await repo.get_goal(goal.id)
        assert completed.status == "completed"
        assert completed.completed_at is not None


@pytest.mark.asyncio
async def test_delete_goal(db) -> None:
    from jarvis.infrastructure.database.repositories import IntelligenceRepository

    async with db.session() as sess:
        repo = IntelligenceRepository(sess)
        goal = await repo.add_goal("Temp goal")

    async with db.session() as sess:
        await IntelligenceRepository(sess).delete_goal(goal.id)

    async with db.session() as sess:
        assert await IntelligenceRepository(sess).get_goal(goal.id) is None


@pytest.mark.asyncio
async def test_search_goals(db) -> None:
    from jarvis.infrastructure.database.repositories import IntelligenceRepository

    async with db.session() as sess:
        repo = IntelligenceRepository(sess)
        await repo.add_goal("Learn Spanish", description="for the trip")
        await repo.add_goal("Buy groceries")

    async with db.session() as sess:
        hits = await IntelligenceRepository(sess).search_goals("Spanish")
        assert {g.title for g in hits} == {"Learn Spanish"}


# ---------------------------------------------------------------------------
# Routines
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_routine_find_reinforce_and_match(db) -> None:
    from jarvis.infrastructure.database.repositories import IntelligenceRepository

    async with db.session() as sess:
        repo = IntelligenceRepository(sess)
        assert await repo.find_matching_routine("make_coffee", hour_of_day=9, day_of_week=1) is None
        routine = await repo.add_routine("make_coffee", hour_of_day=9, day_of_week=1)
        assert routine.observation_count == 1

    async with db.session() as sess:
        repo = IntelligenceRepository(sess)
        found = await repo.find_matching_routine("make_coffee", hour_of_day=9, day_of_week=1)
        assert found is not None
        await repo.reinforce_routine(found.id)
        assert found.observation_count == 2
        assert found.confidence > 0.3


@pytest.mark.asyncio
async def test_list_routines_matches_wildcard_slots(db) -> None:
    from jarvis.infrastructure.database.repositories import IntelligenceRepository

    async with db.session() as sess:
        repo = IntelligenceRepository(sess)
        await repo.add_routine("check_email", hour_of_day=None, day_of_week=None)  # any time
        await repo.add_routine("standup_meeting", hour_of_day=9, day_of_week=0)  # Monday 9am only

    async with db.session() as sess:
        repo = IntelligenceRepository(sess)
        monday_9am = await repo.list_routines(hour_of_day=9, day_of_week=0)
        assert {r.action_type for r in monday_9am} == {"check_email", "standup_meeting"}

        tuesday_3pm = await repo.list_routines(hour_of_day=15, day_of_week=1)
        assert {r.action_type for r in tuesday_3pm} == {"check_email"}


# ---------------------------------------------------------------------------
# Preferences
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_preference_upsert_is_idempotent_on_key(db) -> None:
    from jarvis.infrastructure.database.repositories import IntelligenceRepository

    async with db.session() as sess:
        repo = IntelligenceRepository(sess)
        await repo.upsert_preference("theme", "dark", source="explicit")

    async with db.session() as sess:
        repo = IntelligenceRepository(sess)
        await repo.upsert_preference("theme", "light", source="explicit")

    async with db.session() as sess:
        repo = IntelligenceRepository(sess)
        prefs = await repo.list_preferences()
        assert len(prefs) == 1
        assert prefs[0].value == "light"


@pytest.mark.asyncio
async def test_get_and_delete_preference(db) -> None:
    from jarvis.infrastructure.database.repositories import IntelligenceRepository

    async with db.session() as sess:
        repo = IntelligenceRepository(sess)
        await repo.upsert_preference("reply_length", "short")

    async with db.session() as sess:
        repo = IntelligenceRepository(sess)
        pref = await repo.get_preference("reply_length")
        assert pref is not None
        assert pref.value == "short"
        await repo.delete_preference("reply_length")

    async with db.session() as sess:
        assert await IntelligenceRepository(sess).get_preference("reply_length") is None


@pytest.mark.asyncio
async def test_counts(db) -> None:
    from jarvis.infrastructure.database.repositories import IntelligenceRepository

    async with db.session() as sess:
        repo = IntelligenceRepository(sess)
        await repo.add_goal("A")
        await repo.add_routine("do_x", hour_of_day=None, day_of_week=None)
        await repo.upsert_preference("k", "v")

    async with db.session() as sess:
        repo = IntelligenceRepository(sess)
        assert await repo.count_goals() == 1
        assert await repo.count_routines() == 1
        assert await repo.count_preferences() == 1
