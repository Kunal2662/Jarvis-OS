"""Unit tests for :class:`KnowledgeService` — Milestone 10A.

Real (temp-file) SQLite database, ``FakeVectorStore``, and
``ScriptedFakeLLM``/``FakeLLM`` for the LLM, matching
``test_memory_service.py``'s established pattern.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.fakes.fake_llm import FakeLLM
from tests.fakes.fake_scripted_llm import ScriptedFakeLLM
from tests.fakes.fake_vector_store import FakeVectorStore


def _settings(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JARVIS_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'jarvis.db'}")
    monkeypatch.setenv("JARVIS_OPENAI_ENABLED", "false")
    monkeypatch.setenv("JARVIS_OLLAMA_ENABLED", "true")

    from jarvis.core.config import settings as settings_mod

    settings_mod.load_settings.cache_clear()  # type: ignore[attr-defined]
    return settings_mod.load_settings()


class _FakeMemoryService:
    def __init__(self) -> None:
        self.remembered: list[str] = []

    async def remember(self, content: str, **kwargs) -> str:
        self.remembered.append(content)
        return f"mem-{len(self.remembered)}"

    async def recall(self, query: str, *, top_k: int = 5):
        return []

    async def browse(self, *, limit: int = 200, **kwargs):
        return []

    async def set_pinned(self, memory_id: str, *, pinned: bool) -> None:
        pass


@pytest.fixture
async def env(tmp_path: Path, monkeypatch):
    settings = _settings(tmp_path, monkeypatch)
    from jarvis.infrastructure.database.sqlite_client import SQLiteDatabase

    db = SQLiteDatabase(settings.db)
    await db.initialize()
    vs = FakeVectorStore()
    memory = _FakeMemoryService()
    try:
        yield db, vs, memory
    finally:
        await db.dispose()


_EXTRACTION_MEETING_THURSDAY = json.dumps(
    {
        "entities": [{"name": "meeting", "type": "topic", "description": "A meeting."}],
        "relationships": [],
    }
)


@pytest.mark.asyncio
async def test_learn_from_text_extracts_entities_and_relationships(env) -> None:
    from jarvis.services.knowledge_service import KnowledgeService

    db, vs, memory = env
    llm = FakeLLM(
        json.dumps(
            {
                "entities": [
                    {"name": "Alice", "type": "person", "description": "A colleague."},
                    {"name": "Project X", "type": "project", "description": "A project."},
                ],
                "relationships": [
                    {"subject": "Alice", "predicate": "works_on", "object": "Project X"}
                ],
            }
        )
    )
    svc = KnowledgeService(database=db, vector_store=vs, llm=llm, memory=memory)

    # A real memory row: `knowledge_entity_memories.memory_id` is a
    # foreign key, and the production caller
    # (`learn_from_recent_memories`) always passes a real one.
    from jarvis.infrastructure.database.models import Memory

    async with db.session() as sess:
        memory = Memory(content="Alice works on Project X.")
        sess.add(memory)
        await sess.flush()
        memory_id = memory.id

    result = await svc.learn_from_text("Alice works on Project X.", source_memory_id=memory_id)

    assert result.entities_created == 2
    assert result.relationships_created == 1

    detail = await svc.get_entity_detail("Alice")
    assert detail is not None
    assert detail.relationships[0].predicate == "works_on"
    assert detail.relationships[0].other_entity == "Project X"


@pytest.mark.asyncio
async def test_learn_from_text_is_idempotent_for_repeated_entities(env) -> None:
    from jarvis.services.knowledge_service import KnowledgeService

    db, vs, memory = env
    llm = FakeLLM(
        json.dumps({"entities": [{"name": "Alice", "type": "person"}], "relationships": []})
    )
    svc = KnowledgeService(database=db, vector_store=vs, llm=llm, memory=memory)

    first = await svc.learn_from_text("Alice is here.")
    second = await svc.learn_from_text("Alice is here again.")

    assert first.entities_created == 1
    assert second.entities_created == 0  # same entity, not duplicated


@pytest.mark.asyncio
async def test_learn_from_text_empty_input_extracts_nothing(env) -> None:
    from jarvis.services.knowledge_service import KnowledgeService

    db, vs, memory = env
    svc = KnowledgeService(database=db, vector_store=vs, llm=FakeLLM(""), memory=memory)

    result = await svc.learn_from_text("   ")

    assert result.entities_created == 0
    assert result.relationships_created == 0


@pytest.mark.asyncio
async def test_learn_from_text_tolerates_llm_failure(env) -> None:
    from jarvis.services.knowledge_service import KnowledgeService

    db, vs, memory = env
    svc = KnowledgeService(database=db, vector_store=vs, llm=FakeLLM(fail=True), memory=memory)

    result = await svc.learn_from_text("Alice works on Project X.")

    assert result.entities_created == 0
    assert result.relationships_created == 0


@pytest.mark.asyncio
async def test_correction_supersedes_prior_relationship(env) -> None:
    """Milestone 10A Acceptance Criterion 3: a correction measurably
    updates future recall."""
    from jarvis.services.knowledge_service import KnowledgeService

    db, vs, memory = env
    llm = ScriptedFakeLLM(
        {
            "meeting is on Wednesday": json.dumps(
                {
                    "entities": [
                        {"name": "meeting", "type": "topic"},
                        {"name": "Wednesday", "type": "topic"},
                    ],
                    "relationships": [
                        {"subject": "meeting", "predicate": "occurs_on", "object": "Wednesday"}
                    ],
                }
            ),
            "meeting is on Thursday": json.dumps(
                {
                    "entities": [
                        {"name": "meeting", "type": "topic"},
                        {"name": "Thursday", "type": "topic"},
                    ],
                    "relationships": [
                        {"subject": "meeting", "predicate": "occurs_on", "object": "Thursday"}
                    ],
                }
            ),
        }
    )
    svc = KnowledgeService(database=db, vector_store=vs, llm=llm, memory=memory)

    await svc.learn_from_text("The meeting is on Wednesday.")
    before = await svc.get_entity_detail("meeting")
    assert before is not None
    assert before.relationships[0].other_entity == "Wednesday"

    correction = await svc.correct("Actually, the meeting is on Thursday, not Wednesday.")
    assert correction.relationships_superseded >= 1
    assert correction.relationships_created >= 1

    after = await svc.get_entity_detail("meeting")
    assert after is not None
    assert after.relationships[0].other_entity == "Thursday"


@pytest.mark.asyncio
async def test_correct_rejects_empty_statement(env) -> None:
    from jarvis.core.exceptions import ServiceError
    from jarvis.services.knowledge_service import KnowledgeService

    db, vs, memory = env
    svc = KnowledgeService(database=db, vector_store=vs, llm=FakeLLM(""), memory=memory)

    with pytest.raises(ServiceError):
        await svc.correct("   ")


@pytest.mark.asyncio
async def test_export_import_round_trip(env) -> None:
    """Milestone 10A Acceptance Criterion 2: the knowledge graph survives
    an export/import round-trip."""
    from jarvis.services.knowledge_service import KnowledgeService

    db, vs, memory = env
    llm = FakeLLM(
        json.dumps(
            {
                "entities": [
                    {"name": "Alice", "type": "person"},
                    {"name": "Project X", "type": "project"},
                ],
                "relationships": [
                    {"subject": "Alice", "predicate": "works_on", "object": "Project X"}
                ],
            }
        )
    )
    svc = KnowledgeService(database=db, vector_store=vs, llm=llm, memory=memory)
    await svc.learn_from_text("Alice works on Project X.")

    exported = await svc.export_graph()
    parsed = json.loads(exported)
    assert len(parsed["entities"]) == 2
    assert len(parsed["relationships"]) == 1

    # Round-trip into a *fresh* database to prove the export is self-contained.
    import tempfile

    from jarvis.infrastructure.database.sqlite_client import SQLiteDatabase

    with tempfile.TemporaryDirectory() as tmp2:
        from jarvis.core.config.settings import DatabaseSettings

        db2 = SQLiteDatabase(DatabaseSettings(url=f"sqlite+aiosqlite:///{tmp2}/jarvis2.db"))
        await db2.initialize()
        try:
            svc2 = KnowledgeService(
                database=db2, vector_store=FakeVectorStore(), llm=llm, memory=memory
            )
            result = await svc2.import_graph(exported)
            assert result.entities_created == 2
            assert result.relationships_created == 1

            detail = await svc2.get_entity_detail("Alice")
            assert detail is not None
            assert detail.relationships[0].other_entity == "Project X"
        finally:
            await db2.dispose()


@pytest.mark.asyncio
async def test_import_graph_rejects_invalid_json(env) -> None:
    from jarvis.core.exceptions import ServiceError
    from jarvis.services.knowledge_service import KnowledgeService

    db, vs, memory = env
    svc = KnowledgeService(database=db, vector_store=vs, llm=FakeLLM(""), memory=memory)

    with pytest.raises(ServiceError):
        await svc.import_graph("not json")


@pytest.mark.asyncio
async def test_ask_returns_default_when_nothing_known(env) -> None:
    from jarvis.services.knowledge_service import KnowledgeService

    db, vs, memory = env
    svc = KnowledgeService(database=db, vector_store=vs, llm=FakeLLM(""), memory=memory)

    answer = await svc.ask("What do you know about Nothing?")
    assert "don't have any knowledge" in answer.lower()


@pytest.mark.asyncio
async def test_search_returns_matching_entities(env) -> None:
    from jarvis.services.knowledge_service import KnowledgeService

    db, vs, memory = env
    llm = FakeLLM(
        json.dumps({"entities": [{"name": "Project X", "type": "project"}], "relationships": []})
    )
    svc = KnowledgeService(database=db, vector_store=vs, llm=llm, memory=memory)
    await svc.learn_from_text("Project X exists.")

    results = await svc.search("Project X")
    assert len(results) == 1
    assert results[0].source == "knowledge"
    assert results[0].title == "Project X"
