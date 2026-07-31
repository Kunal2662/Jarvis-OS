"""Unit tests for :class:`ChatService` using a fake LLM + in-memory SQLite."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakes.fake_llm import FakeLLM


@pytest.mark.asyncio
async def test_chat_service_persists_and_streams(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JARVIS_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'jarvis.db'}")
    monkeypatch.setenv("JARVIS_OPENAI_ENABLED", "false")
    monkeypatch.setenv("JARVIS_OLLAMA_ENABLED", "true")

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
        llm = FakeLLM("How may I help you today")
        chat = ChatService(llm=llm, conversations=convs, settings=settings)

        summary = await convs.create()

        # Stream and collect.
        received: list[str] = []
        async for tok in chat.stream(summary.id, "hi"):
            received.append(tok)
        assert "".join(received).strip() == "How may I help you today"

        # System prompt is prepended to the LLM call.
        assert llm.calls, "LLM was not invoked"
        first_call = llm.calls[0]
        assert first_call[0].role == "system"
        assert first_call[0].content == settings.ui.system_prompt

        # Only user + assistant are persisted (never `system`).
        history = await convs.history(summary.id)
        assert [m.role for m in history] == ["user", "assistant"]

        # Empty prompts raise.
        with pytest.raises(Exception):
            async for _ in chat.stream(summary.id, "   "):
                pass
    finally:
        await db.dispose()
