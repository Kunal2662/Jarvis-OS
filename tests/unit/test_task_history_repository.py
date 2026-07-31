"""Unit tests for :class:`TaskHistoryRepository` -- Milestone 4."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
async def db_session(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JARVIS_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'jarvis.db'}")
    monkeypatch.setenv("JARVIS_OPENAI_ENABLED", "false")
    monkeypatch.setenv("JARVIS_OLLAMA_ENABLED", "true")

    from jarvis.core.config import settings as settings_mod

    settings_mod.load_settings.cache_clear()  # type: ignore[attr-defined]
    settings = settings_mod.load_settings()

    from jarvis.infrastructure.database.sqlite_client import SQLiteDatabase

    db = SQLiteDatabase(settings.db)
    await db.initialize()
    try:
        async with db.session() as sess:
            yield sess
    finally:
        await db.dispose()


@pytest.mark.asyncio
async def test_add_and_list_recent(db_session) -> None:
    from jarvis.infrastructure.database.repositories.task_history_repository import (
        TaskHistoryRepository,
    )

    repo = TaskHistoryRepository(db_session)
    await repo.add(plan_id="p1", action="open_app", target="chrome", status="succeeded")
    await repo.add(plan_id="p1", action="screenshot", target=None, status="failed", error="boom")

    rows = await repo.list_recent(limit=10)
    assert len(rows) == 2
    assert {r.action for r in rows} == {"open_app", "screenshot"}


@pytest.mark.asyncio
async def test_list_for_plan_filters_by_plan_id(db_session) -> None:
    from jarvis.infrastructure.database.repositories.task_history_repository import (
        TaskHistoryRepository,
    )

    repo = TaskHistoryRepository(db_session)
    await repo.add(plan_id="p1", action="open_app", target="chrome", status="succeeded")
    await repo.add(plan_id="p2", action="mute", target=None, status="succeeded")

    rows = await repo.list_for_plan("p1")
    assert len(rows) == 1
    assert rows[0].action == "open_app"


@pytest.mark.asyncio
async def test_clear_removes_all_rows(db_session) -> None:
    from jarvis.infrastructure.database.repositories.task_history_repository import (
        TaskHistoryRepository,
    )

    repo = TaskHistoryRepository(db_session)
    await repo.add(plan_id="p1", action="open_app", target="chrome", status="succeeded")
    removed = await repo.clear()
    assert removed == 1
    assert await repo.list_recent() == []
