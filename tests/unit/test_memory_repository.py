"""Unit tests for :class:`MemoryRepository` — Milestone 3."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
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
async def test_add_and_get(db_session) -> None:
    from jarvis.infrastructure.database.repositories.memory_repository import MemoryRepository

    repo = MemoryRepository(db_session)
    row = await repo.add("hello world", memory_type="preference")

    fetched = await repo.get(row.id)
    assert fetched is not None
    assert fetched.content == "hello world"
    assert fetched.memory_type == "preference"
    assert fetched.archived is False
    assert fetched.pinned is False


@pytest.mark.asyncio
async def test_list_filters_by_type_and_archived(db_session) -> None:
    from jarvis.infrastructure.database.repositories.memory_repository import MemoryRepository

    repo = MemoryRepository(db_session)
    a = await repo.add("task one", memory_type="task")
    await repo.add("pref one", memory_type="preference")
    await repo.archive(a.id)

    only_tasks = await repo.list(memory_type="task", include_archived=True)
    assert [r.id for r in only_tasks] == [a.id]

    active_only = await repo.list(include_archived=False)
    assert a.id not in [r.id for r in active_only]


@pytest.mark.asyncio
async def test_keyword_search_is_case_insensitive_and_tokenized(db_session) -> None:
    from jarvis.infrastructure.database.repositories.memory_repository import MemoryRepository

    repo = MemoryRepository(db_session)
    await repo.add("The Quick Brown Fox")
    await repo.add("Lazy Dog")

    hits = await repo.keyword_search("quick fox")
    assert len(hits) == 1
    assert "Quick" in hits[0].content


@pytest.mark.asyncio
async def test_list_expired_only_returns_past_due(db_session) -> None:
    from jarvis.infrastructure.database.repositories.memory_repository import MemoryRepository

    repo = MemoryRepository(db_session)
    past = datetime.now(UTC) - timedelta(days=1)
    future = datetime.now(UTC) + timedelta(days=1)
    expired = await repo.add("old", expires_at=past)
    await repo.add("still fresh", expires_at=future)
    await repo.add("never expires")

    rows = await repo.list_expired(as_of=datetime.now(UTC))
    assert [r.id for r in rows] == [expired.id]


@pytest.mark.asyncio
async def test_list_prunable_counts_pinned_against_cap(db_session) -> None:
    from jarvis.infrastructure.database.repositories.memory_repository import MemoryRepository

    repo = MemoryRepository(db_session)
    await repo.add("pinned", pinned=True)
    unpinned = await repo.add("unpinned")

    prunable = await repo.list_prunable(keep=1)
    assert [r.id for r in prunable] == [unpinned.id]


@pytest.mark.asyncio
async def test_list_prunable_returns_empty_when_under_cap(db_session) -> None:
    from jarvis.infrastructure.database.repositories.memory_repository import MemoryRepository

    repo = MemoryRepository(db_session)
    await repo.add("one")
    prunable = await repo.list_prunable(keep=5)
    assert prunable == []


@pytest.mark.asyncio
async def test_delete_all_removes_every_row(db_session) -> None:
    from jarvis.infrastructure.database.repositories.memory_repository import MemoryRepository

    repo = MemoryRepository(db_session)
    await repo.add("one")
    await repo.add("two")

    removed = await repo.delete_all()

    assert removed == 2
    assert await repo.count() == 0


@pytest.mark.asyncio
async def test_count_respects_archived_flag(db_session) -> None:
    from jarvis.infrastructure.database.repositories.memory_repository import MemoryRepository

    repo = MemoryRepository(db_session)
    a = await repo.add("one")
    await repo.add("two")
    await repo.archive(a.id)

    assert await repo.count(include_archived=True) == 2
    assert await repo.count(include_archived=False) == 1


# ---------------------------------------------------------------------------
# Milestone 3.1 — Timeline filtering + retention re-stamping
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_list_filtered_by_type_pinned_and_archived(db_session) -> None:
    from jarvis.infrastructure.database.repositories.memory_repository import MemoryRepository

    repo = MemoryRepository(db_session)
    pinned = await repo.add("pinned task", memory_type="task", pinned=True)
    plain = await repo.add("plain task", memory_type="task")
    archived = await repo.add("archived pref", memory_type="preference")
    await repo.archive(archived.id)

    only_pinned = await repo.list_filtered(pinned_only=True)
    assert [r.id for r in only_pinned] == [pinned.id]

    tasks_only = await repo.list_filtered(memory_type="task", include_archived=True)
    assert {r.id for r in tasks_only} == {pinned.id, plain.id}

    without_archived = await repo.list_filtered(include_archived=False)
    assert archived.id not in [r.id for r in without_archived]

    with_archived = await repo.list_filtered(include_archived=True)
    assert archived.id in [r.id for r in with_archived]


@pytest.mark.asyncio
async def test_list_filtered_by_date_range(db_session) -> None:
    from jarvis.infrastructure.database.repositories.memory_repository import MemoryRepository

    repo = MemoryRepository(db_session)
    row = await repo.add("in range")

    past = row.created_at - timedelta(days=1)
    future = row.created_at + timedelta(days=1)

    in_range = await repo.list_filtered(start_date=past, end_date=future)
    assert row.id in [r.id for r in in_range]

    out_of_range = await repo.list_filtered(start_date=future)
    assert row.id not in [r.id for r in out_of_range]


@pytest.mark.asyncio
async def test_set_pinned_toggles_flag(db_session) -> None:
    from jarvis.infrastructure.database.repositories.memory_repository import MemoryRepository

    repo = MemoryRepository(db_session)
    row = await repo.add("something")
    assert row.pinned is False

    await repo.set_pinned(row.id, pinned=True)
    fetched = await repo.get(row.id)
    assert fetched is not None
    assert fetched.pinned is True


@pytest.mark.asyncio
async def test_restamp_expirations_applies_new_retention(db_session) -> None:
    from jarvis.infrastructure.database.repositories.memory_repository import MemoryRepository

    repo = MemoryRepository(db_session)
    unpinned = await repo.add("unpinned", expires_at=None)
    pinned = await repo.add("pinned", pinned=True, expires_at=None)

    changed = await repo.restamp_expirations(retention_days=30)

    assert changed == 1  # only the unpinned row is touched
    refreshed = await repo.get(unpinned.id)
    assert refreshed is not None
    assert refreshed.expires_at is not None
    assert refreshed.expires_at - refreshed.created_at == timedelta(days=30)

    still_pinned = await repo.get(pinned.id)
    assert still_pinned is not None
    assert still_pinned.expires_at is None


@pytest.mark.asyncio
async def test_restamp_expirations_clears_when_retention_zero(db_session) -> None:
    from jarvis.infrastructure.database.repositories.memory_repository import MemoryRepository

    repo = MemoryRepository(db_session)
    row = await repo.add("temporary", expires_at=datetime.now(UTC) + timedelta(days=5))

    changed = await repo.restamp_expirations(retention_days=0)

    assert changed == 1
    refreshed = await repo.get(row.id)
    assert refreshed is not None
    assert refreshed.expires_at is None
