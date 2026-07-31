"""Unit tests for :class:`MemoryService` — Milestone 3.

Uses a real (temp-file) SQLite database via :class:`SQLiteDatabase` plus
in-memory fakes for the LLM (embeddings) and vector store, so these tests
never require ``chromadb`` or network access.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tests.fakes.fake_llm import FakeLLM
from tests.fakes.fake_vector_store import FakeVectorStore


def _settings(tmp_path: Path, monkeypatch, **overrides: str):
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JARVIS_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'jarvis.db'}")
    monkeypatch.setenv("JARVIS_OPENAI_ENABLED", "false")
    monkeypatch.setenv("JARVIS_OLLAMA_ENABLED", "true")
    for key, value in overrides.items():
        monkeypatch.setenv(key, value)

    from jarvis.core.config import settings as settings_mod

    settings_mod.load_settings.cache_clear()  # type: ignore[attr-defined]
    return settings_mod.load_settings()


@pytest.fixture
async def env(tmp_path: Path, monkeypatch):
    settings = _settings(tmp_path, monkeypatch)

    from jarvis.infrastructure.database.sqlite_client import SQLiteDatabase
    from jarvis.services.memory_service import MemoryService

    db = SQLiteDatabase(settings.db)
    await db.initialize()
    llm = FakeLLM("a summary of the conversation")
    vs = FakeVectorStore()
    svc = MemoryService(database=db, vector_store=vs, llm=llm, settings=settings)
    try:
        yield svc, db, llm, vs, settings
    finally:
        await db.dispose()


@pytest.mark.asyncio
async def test_remember_and_recall_roundtrip(env) -> None:
    svc, *_ = env
    mid = await svc.remember("The user's favorite color is teal.", source="user")
    assert mid

    results = await svc.recall("favorite color", top_k=5)
    assert any(r.id == mid for r in results)
    assert results[0].content == "The user's favorite color is teal."


@pytest.mark.asyncio
async def test_remember_rejects_empty_content(env) -> None:
    svc, *_ = env
    from jarvis.core.exceptions import ServiceError

    with pytest.raises(ServiceError):
        await svc.remember("   ")


@pytest.mark.asyncio
async def test_remember_tags_memory_type(env) -> None:
    svc, *_ = env
    from jarvis.core.types import MemoryType

    mid = await svc.remember("Project Phoenix deadline is Friday.", memory_type=MemoryType.PROJECT)
    results = await svc.search("phoenix", mode="keyword", top_k=5)
    assert any(r.id == mid and r.memory_type == "project" for r in results)


@pytest.mark.asyncio
async def test_forget_removes_from_both_stores(env) -> None:
    svc, _db, _llm, vs, _settings = env
    mid = await svc.remember("Temporary note.")
    assert await vs.count() == 1

    await svc.forget(mid)

    assert await vs.count() == 0
    results = await svc.search("Temporary note", mode="keyword")
    assert results == []


@pytest.mark.asyncio
async def test_forget_all_clears_everything(env) -> None:
    svc, *_ = env
    await svc.remember("one")
    await svc.remember("two")
    await svc.remember("three")

    removed = await svc.forget_all()

    assert removed == 3
    stats = await svc.stats()
    assert stats.sql_count == 0
    assert stats.vector_count == 0


@pytest.mark.asyncio
async def test_search_recent_mode_ignores_query(env) -> None:
    svc, *_ = env
    await svc.remember("alpha")
    await svc.remember("beta")

    results = await svc.search(mode="recent", top_k=10)
    assert {r.content for r in results} == {"alpha", "beta"}


@pytest.mark.asyncio
async def test_search_keyword_mode_filters_by_type(env) -> None:
    svc, *_ = env
    from jarvis.core.types import MemoryType

    await svc.remember("call mom tomorrow", memory_type=MemoryType.TASK)
    await svc.remember("call center project notes", memory_type=MemoryType.PROJECT)

    results = await svc.search("call", mode="keyword", memory_type=MemoryType.TASK, top_k=10)
    assert len(results) == 1
    assert results[0].memory_type == "task"


@pytest.mark.asyncio
async def test_summarize_persists_long_term_memory(env) -> None:
    svc, *_ = env
    from jarvis.core.types import MemoryType

    summary = await svc.summarize("user: I love hiking\nassistant: noted!")
    assert summary == "a summary of the conversation"

    results = await svc.search(mode="recent", memory_type=MemoryType.LONG_TERM, top_k=10)
    assert any(r.content == summary for r in results)


@pytest.mark.asyncio
async def test_export_then_import_roundtrip(env) -> None:
    svc, *_ = env
    await svc.remember("exported fact one", source="user")
    await svc.remember("exported fact two", source="user")

    dump = await svc.export_memories()
    payload = json.loads(dump)
    assert len(payload["memories"]) == 2

    imported = await svc.import_memories(dump)
    assert imported == 2

    stats = await svc.stats()
    assert stats.sql_count == 4  # original 2 + 2 re-imported (new ids)


@pytest.mark.asyncio
async def test_import_rejects_malformed_json(env) -> None:
    svc, *_ = env
    from jarvis.core.exceptions import ServiceError

    with pytest.raises(ServiceError):
        await svc.import_memories("not json")


@pytest.mark.asyncio
async def test_import_skips_blank_entries(env) -> None:
    svc, *_ = env
    dump = json.dumps({"memories": [{"content": "  "}, {"content": "kept"}]})
    imported = await svc.import_memories(dump)
    assert imported == 1


@pytest.mark.asyncio
async def test_import_rejects_wrong_top_level_structure(env) -> None:
    """Real gap: valid JSON, but not the expected shape (a list, or a
    dict with a "memories" list) -- e.g. a user picks the wrong file
    for Import Memory. Must fail with a clear ServiceError, not a raw
    AttributeError/TypeError from deep inside the loop."""
    svc, *_ = env
    from jarvis.core.exceptions import ServiceError

    with pytest.raises(ServiceError, match="must contain a list"):
        await svc.import_memories(json.dumps({"unexpected": "shape"}))

    with pytest.raises(ServiceError, match="must contain a list"):
        await svc.import_memories(json.dumps(42))


@pytest.mark.asyncio
async def test_import_skips_non_dict_list_entries(env) -> None:
    """A list of memories where some entries aren't objects at all
    (e.g. a hand-edited or corrupted export file) -- must skip those
    entries, not crash the whole import."""
    svc, *_ = env
    dump = json.dumps({"memories": [1, "not-a-dict", {"content": "kept"}, None]})

    imported = await svc.import_memories(dump)

    assert imported == 1


@pytest.mark.asyncio
async def test_import_continues_after_one_entry_fails(env) -> None:
    """Graceful degradation: if one entry fails inside remember() (e.g.
    an invalid memory_type), the rest of the batch must still import
    rather than the whole operation aborting."""
    svc, *_ = env
    dump = json.dumps(
        {
            "memories": [
                {"content": "good memory one"},
                {"content": "bad memory", "memory_type": "not_a_real_memory_type"},
                {"content": "good memory two"},
            ]
        }
    )

    imported = await svc.import_memories(dump)

    # At least the two valid entries made it through even though the
    # middle one had an invalid memory_type.
    assert imported >= 2
    results = await svc.search(mode="recent", top_k=10)
    contents = {r.content for r in results}
    assert "good memory one" in contents
    assert "good memory two" in contents


@pytest.mark.asyncio
async def test_enforce_policies_prunes_over_cap(tmp_path: Path, monkeypatch) -> None:
    settings = _settings(tmp_path, monkeypatch, JARVIS_MEMORY_MAX_MEMORIES="2")

    from jarvis.infrastructure.database.sqlite_client import SQLiteDatabase
    from jarvis.services.memory_service import MemoryService

    db = SQLiteDatabase(settings.db)
    await db.initialize()
    try:
        svc = MemoryService(
            database=db, vector_store=FakeVectorStore(), llm=FakeLLM(), settings=settings
        )
        await svc.remember("first")
        await svc.remember("second")
        await svc.remember("third")

        report = await svc.enforce_policies()

        assert report.pruned == 1  # oldest one archived beyond the cap of 2
        remaining = await svc.search(mode="recent", top_k=10)
        assert {r.content for r in remaining} == {"second", "third"}
    finally:
        await db.dispose()


@pytest.mark.asyncio
async def test_enforce_policies_expires_old_memories(tmp_path: Path, monkeypatch) -> None:
    settings = _settings(tmp_path, monkeypatch)

    from jarvis.infrastructure.database.sqlite_client import SQLiteDatabase
    from jarvis.services.memory_service import MemoryService

    db = SQLiteDatabase(settings.db)
    await db.initialize()
    try:
        svc = MemoryService(
            database=db, vector_store=FakeVectorStore(), llm=FakeLLM(), settings=settings
        )
        past = datetime.now(UTC) - timedelta(days=1)
        await svc.remember("stale note", expires_at=past)
        await svc.remember("fresh note")

        report = await svc.enforce_policies()

        assert report.expired == 1
        remaining = await svc.search(mode="recent", top_k=10)
        assert {r.content for r in remaining} == {"fresh note"}
    finally:
        await db.dispose()


@pytest.mark.asyncio
async def test_pinned_memories_survive_pruning(tmp_path: Path, monkeypatch) -> None:
    settings = _settings(tmp_path, monkeypatch, JARVIS_MEMORY_MAX_MEMORIES="1")

    from jarvis.infrastructure.database.sqlite_client import SQLiteDatabase
    from jarvis.services.memory_service import MemoryService

    db = SQLiteDatabase(settings.db)
    await db.initialize()
    try:
        svc = MemoryService(
            database=db, vector_store=FakeVectorStore(), llm=FakeLLM(), settings=settings
        )
        await svc.remember("pin me", pinned=True)
        await svc.remember("prune me")

        await svc.enforce_policies()

        remaining = await svc.search(mode="recent", top_k=10)
        assert {r.content for r in remaining} == {"pin me"}
    finally:
        await db.dispose()


@pytest.mark.asyncio
async def test_delete_archived_hard_deletes(tmp_path: Path, monkeypatch) -> None:
    settings = _settings(tmp_path, monkeypatch, JARVIS_MEMORY_MAX_MEMORIES="1")

    from jarvis.infrastructure.database.sqlite_client import SQLiteDatabase
    from jarvis.services.memory_service import MemoryService

    db = SQLiteDatabase(settings.db)
    await db.initialize()
    try:
        svc = MemoryService(
            database=db, vector_store=FakeVectorStore(), llm=FakeLLM(), settings=settings
        )
        await svc.remember("old")
        await svc.remember("new")
        await svc.enforce_policies()

        removed = await svc.delete_archived()

        assert removed == 1
        stats = await svc.stats()
        assert stats.sql_count == 1
    finally:
        await db.dispose()


# ---------------------------------------------------------------------------
# Milestone 3.1 — Timeline browsing + retention re-stamping
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_browse_filters_by_type_and_pinned(env) -> None:
    svc, *_ = env
    await svc.remember("a task", memory_type="task")
    await svc.remember("a pinned preference", memory_type="preference", pinned=True)

    tasks = await svc.browse(memory_type="task")
    assert {r.content for r in tasks} == {"a task"}

    pinned = await svc.browse(pinned_only=True)
    assert {r.content for r in pinned} == {"a pinned preference"}


@pytest.mark.asyncio
async def test_set_pinned_and_archive_memory_roundtrip(env) -> None:
    svc, *_ = env
    mid = await svc.remember("pin candidate")

    await svc.set_pinned(mid, pinned=True)
    pinned = await svc.browse(pinned_only=True)
    assert mid in [r.id for r in pinned]

    await svc.archive_memory(mid)
    active_only = await svc.browse(include_archived=False)
    assert mid not in [r.id for r in active_only]
    with_archived = await svc.browse(include_archived=True)
    assert mid in [r.id for r in with_archived]


@pytest.mark.asyncio
async def test_restamp_retention_archives_newly_expired_rows(tmp_path: Path, monkeypatch) -> None:
    settings = _settings(tmp_path, monkeypatch, JARVIS_MEMORY_RETENTION_DAYS="0")

    from jarvis.infrastructure.database.repositories.memory_repository import MemoryRepository
    from jarvis.infrastructure.database.sqlite_client import SQLiteDatabase
    from jarvis.services.memory_service import MemoryService

    db = SQLiteDatabase(settings.db)
    await db.initialize()
    try:
        svc = MemoryService(
            database=db, vector_store=FakeVectorStore(), llm=FakeLLM(), settings=settings
        )
        mid = await svc.remember("written when retention was unlimited")
        assert settings.memory.retention_days == 0

        # Back-date the row so a modest retention window is already in the
        # past once re-stamped — a freshly-written row can never appear
        # already-expired under a positive retention_days.
        async with db.session() as sess:
            row = await MemoryRepository(sess).get(mid)
            assert row is not None
            row.created_at = datetime.now(UTC) - timedelta(days=10)

        # Lower retention after the fact and re-stamp existing rows.
        settings.memory.retention_days = 1
        changed = await svc.restamp_retention()
        assert changed == 1

        report = await svc.enforce_policies()
        assert report.expired == 1

        active_only = await svc.browse(include_archived=False)
        assert mid not in [r.id for r in active_only]
    finally:
        await db.dispose()
