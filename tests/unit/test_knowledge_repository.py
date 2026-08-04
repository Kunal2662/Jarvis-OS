"""Unit tests for :class:`KnowledgeRepository` — Milestone 10A.

Real (temp-file) SQLite database via :class:`SQLiteDatabase`, matching
``test_memory_service.py``'s established pattern.
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


@pytest.mark.asyncio
async def test_add_and_get_entity(db) -> None:
    from jarvis.infrastructure.database.repositories import KnowledgeRepository

    async with db.session() as sess:
        repo = KnowledgeRepository(sess)
        entity = await repo.add_entity("Project X", entity_type="project", description="A project.")

    async with db.session() as sess:
        repo = KnowledgeRepository(sess)
        fetched = await repo.get_entity(entity.id)
        assert fetched is not None
        assert fetched.name == "Project X"
        assert fetched.entity_type == "project"


@pytest.mark.asyncio
async def test_find_entity_by_name_is_case_insensitive(db) -> None:
    from jarvis.infrastructure.database.repositories import KnowledgeRepository

    async with db.session() as sess:
        repo = KnowledgeRepository(sess)
        await repo.add_entity("Project X")

    async with db.session() as sess:
        repo = KnowledgeRepository(sess)
        found = await repo.find_entity_by_name("project x")
        assert found is not None
        assert found.name == "Project X"


@pytest.mark.asyncio
async def test_search_entities_matches_name_and_description(db) -> None:
    from jarvis.infrastructure.database.repositories import KnowledgeRepository

    async with db.session() as sess:
        repo = KnowledgeRepository(sess)
        await repo.add_entity("Alice", entity_type="person", description="Works on Project X.")
        await repo.add_entity("Bob", entity_type="person", description="Unrelated.")

    async with db.session() as sess:
        repo = KnowledgeRepository(sess)
        hits = await repo.search_entities("Project X")
        assert {e.name for e in hits} == {"Alice"}


@pytest.mark.asyncio
async def test_relationship_roundtrip_and_supersede(db) -> None:
    from jarvis.infrastructure.database.repositories import KnowledgeRepository

    async with db.session() as sess:
        repo = KnowledgeRepository(sess)
        meeting = await repo.add_entity("meeting", entity_type="topic")
        wednesday = await repo.add_entity("Wednesday", entity_type="topic")
        thursday = await repo.add_entity("Thursday", entity_type="topic")
        old_rel = await repo.add_relationship(meeting.id, "occurs_on", wednesday.id)

        rels = await repo.list_relationships_for_entity(meeting.id)
        assert len(rels) == 1
        assert rels[0].object_id == wednesday.id

        new_rel = await repo.add_relationship(meeting.id, "occurs_on", thursday.id, confidence=0.95)
        superseded_count = await repo.supersede_relationships(
            meeting.id, "occurs_on", exclude_id=new_rel.id
        )
        assert superseded_count == 1

        active = await repo.list_relationships_for_entity(meeting.id)
        assert len(active) == 1
        assert active[0].object_id == thursday.id

        with_history = await repo.list_relationships_for_entity(meeting.id, include_superseded=True)
        assert len(with_history) == 2
        assert old_rel.superseded is True


@pytest.mark.asyncio
async def test_link_entity_memory_is_idempotent(db) -> None:
    from jarvis.infrastructure.database.repositories import KnowledgeRepository

    async with db.session() as sess:
        repo = KnowledgeRepository(sess)
        entity = await repo.add_entity("Project X")
        await repo.link_entity_memory(entity.id, "mem-1")
        await repo.link_entity_memory(entity.id, "mem-1")  # no-op second call

    async with db.session() as sess:
        repo = KnowledgeRepository(sess)
        ids = await repo.list_memory_ids_for_entity(entity.id)
        assert ids == ["mem-1"]


@pytest.mark.asyncio
async def test_delete_entity(db) -> None:
    from jarvis.infrastructure.database.repositories import KnowledgeRepository

    async with db.session() as sess:
        repo = KnowledgeRepository(sess)
        entity = await repo.add_entity("Temp")

    async with db.session() as sess:
        repo = KnowledgeRepository(sess)
        await repo.delete_entity(entity.id)

    async with db.session() as sess:
        repo = KnowledgeRepository(sess)
        assert await repo.get_entity(entity.id) is None


@pytest.mark.asyncio
async def test_count_entities_and_relationships(db) -> None:
    from jarvis.infrastructure.database.repositories import KnowledgeRepository

    async with db.session() as sess:
        repo = KnowledgeRepository(sess)
        a = await repo.add_entity("A")
        b = await repo.add_entity("B")
        await repo.add_relationship(a.id, "relates_to", b.id)

    async with db.session() as sess:
        repo = KnowledgeRepository(sess)
        assert await repo.count_entities() == 2
        assert await repo.count_relationships() == 1
