"""Unit tests for ``jarvis.core.lifecycle.session_manager.SessionManager``
(Milestone 9 Task Group B)."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
async def database(tmp_path: Path):
    from jarvis.core.config.settings import DatabaseSettings
    from jarvis.infrastructure.database.sqlite_client import SQLiteDatabase

    db = SQLiteDatabase(DatabaseSettings(url=f"sqlite+aiosqlite:///{tmp_path / 'jarvis.db'}"))
    await db.initialize()
    try:
        yield db
    finally:
        await db.dispose()


@pytest.mark.asyncio
async def test_create_persists_and_publishes_session_created_event(database) -> None:
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.events.events import SessionCreatedEvent
    from jarvis.core.lifecycle.session_manager import SessionManager

    bus = EventBus()
    published: list[SessionCreatedEvent] = []
    bus.subscribe(SessionCreatedEvent, published.append)
    manager = SessionManager(database, bus)

    # `conversation_id` is a real foreign key, so the conversation has
    # to exist. `thread_id` is deliberately not one -- LangGraph's
    # checkpointer owns that id space -- so an arbitrary value is fine.
    from jarvis.infrastructure.database.models import Conversation

    async with database.session() as sess:
        conversation = Conversation(title="Test conversation")
        sess.add(conversation)
        await sess.flush()
        conversation_id = conversation.id

    info = await manager.create(
        conversation_id=conversation_id,
        thread_id="thread-1",
        metadata={"client": "desktop-ui"},
    )

    assert info.conversation_id == conversation_id
    assert info.thread_id == "thread-1"
    assert info.metadata == {"client": "desktop-ui"}
    assert info.closed_at is None
    assert manager.get(info.session_id) == info
    assert len(published) == 1
    assert published[0].session_id == info.session_id
    assert published[0].recovered is False


@pytest.mark.asyncio
async def test_close_removes_from_active_and_publishes_event(database) -> None:
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.events.events import SessionClosedEvent
    from jarvis.core.lifecycle.session_manager import SessionManager

    bus = EventBus()
    published: list[SessionClosedEvent] = []
    bus.subscribe(SessionClosedEvent, published.append)
    manager = SessionManager(database, bus)

    info = await manager.create()
    await manager.close(info.session_id)

    assert manager.get(info.session_id) is None
    assert manager.active_sessions == ()
    assert len(published) == 1
    assert published[0].session_id == info.session_id


@pytest.mark.asyncio
async def test_close_unknown_session_is_a_safe_no_op(database) -> None:
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.lifecycle.session_manager import SessionManager

    manager = SessionManager(database, EventBus())
    await manager.close("does-not-exist")  # must not raise


@pytest.mark.asyncio
async def test_close_all_closes_every_active_session(database) -> None:
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.lifecycle.session_manager import SessionManager

    manager = SessionManager(database, EventBus())
    a = await manager.create()
    b = await manager.create()

    await manager.close_all()

    assert manager.active_sessions == ()
    assert manager.get(a.session_id) is None
    assert manager.get(b.session_id) is None


@pytest.mark.asyncio
async def test_touch_updates_last_active_at(database) -> None:
    """Compares two values both read back via ``SELECT`` (not the
    freshly-inserted, still-in-session ``SessionInfo``) -- SQLite
    round-trips ``DateTime(timezone=True)`` columns as naive, so mixing
    a fresh in-memory tz-aware value with a re-queried naive one is not
    a safe comparison, independent of this test."""
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.lifecycle.session_manager import SessionManager
    from jarvis.infrastructure.database.repositories import RuntimeSessionRepository

    manager = SessionManager(database, EventBus())
    info = await manager.create()

    async with database.session() as sess:
        before = await RuntimeSessionRepository(sess).get(info.session_id)
        assert before is not None
        before_last_active_at = before.last_active_at

    await manager.touch(info.session_id)

    async with database.session() as sess:
        after = await RuntimeSessionRepository(sess).get(info.session_id)
        assert after is not None
        assert after.last_active_at >= before_last_active_at


@pytest.mark.asyncio
async def test_recover_closes_dangling_sessions_left_by_unclean_shutdown(
    tmp_path: Path,
) -> None:
    """A session created but never closed (simulating a crash) must be
    found and closed out by the *next* process's ``recover()`` --
    proven here with two independent ``SQLiteDatabase``/``SessionManager``
    instances against the same on-disk file, exactly like two real OS
    process launches would see."""
    from jarvis.core.config.settings import DatabaseSettings
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.events.events import SessionClosedEvent
    from jarvis.core.lifecycle.session_manager import SessionManager
    from jarvis.infrastructure.database.sqlite_client import SQLiteDatabase

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'jarvis.db'}"

    db1 = SQLiteDatabase(DatabaseSettings(url=db_url))
    await db1.initialize()
    manager1 = SessionManager(db1, EventBus())
    dangling = await manager1.create(metadata={})
    await db1.dispose()  # simulated crash: never called close()

    db2 = SQLiteDatabase(DatabaseSettings(url=db_url))
    await db2.initialize()
    bus2 = EventBus()
    published: list[SessionClosedEvent] = []
    bus2.subscribe(SessionClosedEvent, published.append)
    manager2 = SessionManager(db2, bus2)

    recovered = await manager2.recover()

    assert [r.session_id for r in recovered] == [dangling.session_id]
    assert len(published) == 1
    # A second recover() on an already-clean DB finds nothing left.
    assert await manager2.recover() == ()
    await db2.dispose()
