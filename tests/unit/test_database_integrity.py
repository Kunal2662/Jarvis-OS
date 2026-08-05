"""Foreign-key enforcement tests -- Aug 2026 database integrity pass.

SQLite ships with ``PRAGMA foreign_keys`` **off**, and the setting is
per-connection rather than per-database. Every ``ON DELETE`` clause in
``models.py`` was therefore decorative until ``SQLiteDatabase`` began
issuing the pragma from a ``connect`` event listener.

These tests exist because that is exactly the kind of setting that gets
silently lost -- a refactor that builds the engine somewhere else, a
pool that grows a connection the listener never saw, a future adapter
that forgets. Asserting the pragma's *value* is not enough on its own,
so the enforcement is also proven by an insert and a delete that must
now fail.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from jarvis.infrastructure.database.models import Conversation, Memory, Note, Workspace


@pytest.fixture
async def db(tmp_path: Path):
    from jarvis.core.config.settings import DatabaseSettings
    from jarvis.infrastructure.database.sqlite_client import SQLiteDatabase

    settings = DatabaseSettings(url=f"sqlite+aiosqlite:///{tmp_path / 'jarvis.db'}")
    database = SQLiteDatabase(settings)
    await database.initialize()
    try:
        yield database
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_the_pragma_is_on_for_every_pooled_connection(db) -> None:
    """Per-connection, not per-database: a pool that recycles or grows
    would otherwise hand out connections with enforcement off, and the
    resulting corruption would be intermittent -- worse than never
    enabling it."""
    for _ in range(3):
        async with db.session() as sess:
            assert (await sess.execute(text("PRAGMA foreign_keys"))).scalar() == 1


@pytest.mark.asyncio
async def test_an_orphan_insert_is_rejected(db) -> None:
    """A note whose workspace does not exist. Accepted silently before
    this pass."""
    with pytest.raises(IntegrityError):
        async with db.session() as sess:
            sess.add(Note(workspace_id="does-not-exist", title="orphan"))
            await sess.flush()


@pytest.mark.asyncio
async def test_a_valid_insert_still_works(db) -> None:
    """The enforcement must reject only what is genuinely broken."""
    async with db.session() as sess:
        workspace = Workspace(name="Real")
        sess.add(workspace)
        await sess.flush()
        sess.add(Note(workspace_id=workspace.id, title="fine"))
        await sess.flush()


@pytest.mark.asyncio
async def test_nullable_foreign_keys_still_accept_null(db) -> None:
    """``ON DELETE SET NULL`` columns are optional by design -- a note
    filed against no project, a session with no conversation. Enforcement
    must not turn "not set" into "invalid"."""
    async with db.session() as sess:
        workspace = Workspace(name="W")
        sess.add(workspace)
        await sess.flush()
        sess.add(Note(workspace_id=workspace.id, project_id=None, title="unfiled"))
        await sess.flush()


@pytest.mark.asyncio
async def test_declared_cascades_now_actually_run(db) -> None:
    """``ON DELETE CASCADE`` at the database level, with no ORM
    relationship involved -- this deletes through Core rather than the
    ORM session's cascade machinery, so it proves the *constraint* is
    what removed the child."""
    from jarvis.infrastructure.database.repositories import KnowledgeRepository

    async with db.session() as sess:
        memory = Memory(content="c")
        sess.add(memory)
        await sess.flush()
        memory_id = memory.id

        entity = await KnowledgeRepository(sess).add_entity("Entity")
        entity_id = entity.id
        await sess.execute(
            text(
                "INSERT INTO knowledge_entity_memories (entity_id, memory_id) "
                "VALUES (:eid, :mid)"
            ),
            {"eid": entity_id, "mid": memory_id},
        )

    async with db.session() as sess:
        await sess.execute(
            text("DELETE FROM knowledge_entities WHERE id = :eid"), {"eid": entity_id}
        )

    async with db.session() as sess:
        remaining = (
            await sess.execute(text("SELECT COUNT(*) FROM knowledge_entity_memories"))
        ).scalar()
        assert remaining == 0


@pytest.mark.asyncio
async def test_a_session_cannot_reference_a_missing_conversation(db) -> None:
    """The product gap this pass surfaced: ``POST /api/v1/sessions``
    took ``conversation_id`` straight from the request body into a real
    foreign key. ``SessionManager.create`` now rejects an unknown id
    before writing."""
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.exceptions import ServiceError
    from jarvis.core.lifecycle.session_manager import SessionManager

    manager = SessionManager(db, EventBus())

    with pytest.raises(ServiceError, match="does not exist"):
        await manager.create(conversation_id="never-created")


@pytest.mark.asyncio
async def test_a_session_with_a_real_conversation_is_accepted(db) -> None:
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.lifecycle.session_manager import SessionManager

    async with db.session() as sess:
        conversation = Conversation(title="Real")
        sess.add(conversation)
        await sess.flush()
        conversation_id = conversation.id

    info = await SessionManager(db, EventBus()).create(conversation_id=conversation_id)

    assert info.conversation_id == conversation_id


@pytest.mark.asyncio
async def test_a_session_without_a_conversation_is_accepted(db) -> None:
    """The common case -- a session created before any conversation is
    chosen. Validation must not make the optional column mandatory."""
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.lifecycle.session_manager import SessionManager

    info = await SessionManager(db, EventBus()).create(thread_id="anything")

    assert info.conversation_id is None
    # `thread_id` is not a foreign key, so an arbitrary value stands.
    assert info.thread_id == "anything"
