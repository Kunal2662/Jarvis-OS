"""End-to-end chat flow: SQLite + ConversationService + ChatService + FakeLLM."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakes.fake_llm import FakeLLM


@pytest.mark.asyncio
async def test_chat_end_to_end(tmp_path: Path, monkeypatch) -> None:
    # Point the DB at a tmp file BEFORE any imports of settings.
    db_path = tmp_path / "jarvis.db"
    monkeypatch.setenv("JARVIS_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JARVIS_OPENAI_ENABLED", "false")
    monkeypatch.setenv("JARVIS_OLLAMA_ENABLED", "true")

    # Force a fresh Settings load (lru_cached).
    from jarvis.core.config import settings as settings_mod

    settings_mod.load_settings.cache_clear()  # type: ignore[attr-defined]
    settings = settings_mod.load_settings()

    from jarvis.infrastructure.database.sqlite_client import SQLiteDatabase
    from jarvis.services.chat_service import ChatService
    from jarvis.services.conversation_service import ConversationService

    db = SQLiteDatabase(settings.db)
    await db.initialize()
    try:
        convs = ConversationService(db)
        chat = ChatService(
            llm=FakeLLM("Hi there my friend"), conversations=convs, settings=settings
        )

        # 1. New conversation.
        summary = await convs.create(title="Test chat")
        assert summary.id
        assert summary.title == "Test chat"

        # 2. Stream a response.
        tokens: list[str] = []
        async for tok in chat.stream(summary.id, "hello?"):
            tokens.append(tok)
        assert "".join(tokens).strip() == "Hi there my friend"

        # 3. History contains user + assistant messages (system is transient).
        history = await convs.history(summary.id)
        roles = [m.role for m in history]
        assert roles == ["user", "assistant"]
        assert history[0].content == "hello?"
        assert history[1].content == "Hi there my friend"

        # 4. list() returns the conversation.
        listed = await convs.list()
        assert any(c.id == summary.id for c in listed)

        # 5. Non-streaming ask() also works.
        answer = await chat.ask(summary.id, "again please")
        assert answer.strip() == "Hi there my friend"
        history = await convs.history(summary.id)
        assert len(history) == 4  # user, assistant, user, assistant
    finally:
        await db.dispose()
