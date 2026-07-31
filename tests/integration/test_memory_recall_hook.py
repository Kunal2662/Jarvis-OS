"""Verify the memory-recall hook is invoked by ChatService and its output
is prepended between the system prompt and the persisted history.

This is the Milestone 3 reservation point — the test proves that a
future ``MemoryService.recall``-backed hook will Just Work.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core.interfaces.memory import IMemoryRecallHook
from jarvis.core.types import ChatMessage
from tests.fakes.fake_llm import FakeLLM


class _MemoryHook(IMemoryRecallHook):
    def __init__(self, memories: list[ChatMessage]) -> None:
        self.memories = memories
        self.calls: list[tuple[str, str]] = []

    async def recall(self, conversation_id: str, prompt: str):
        self.calls.append((conversation_id, prompt))
        return self.memories


@pytest.mark.asyncio
async def test_memory_hook_is_called_and_prepended(tmp_path: Path, monkeypatch) -> None:
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
        llm = FakeLLM("ok")
        hook = _MemoryHook(
            [
                ChatMessage(role="system", content="Remember: user prefers concise answers."),
                ChatMessage(role="system", content="Remember: user's timezone is CET."),
            ]
        )
        chat = ChatService(llm=llm, conversations=convs, settings=settings, memory_recall=hook)

        summary = await convs.create()
        _ = await chat.ask(summary.id, "hi")

        # Hook received the right call.
        assert hook.calls == [(summary.id, "hi")]

        # LLM saw: [system prompt] + [2 memories] + [user message]
        sent = llm.calls[0]
        assert sent[0].role == "system" and sent[0].content == settings.ui.system_prompt
        assert sent[1].role == "system" and "concise" in sent[1].content
        assert sent[2].role == "system" and "CET" in sent[2].content
        assert sent[3].role == "user" and sent[3].content == "hi"
    finally:
        await db.dispose()
