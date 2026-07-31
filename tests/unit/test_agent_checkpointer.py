"""Unit tests for :class:`AgentCheckpointer` (Milestone 5-Agents)."""

from __future__ import annotations

import pytest

from jarvis.core.config.settings import AgentSettings, Settings

pytest.importorskip("langgraph")


@pytest.mark.asyncio
async def test_checkpoint_disabled_uses_memory_saver(tmp_path) -> None:
    from langgraph.checkpoint.memory import MemorySaver

    from jarvis.agents.checkpointer import AgentCheckpointer

    settings = Settings(data_dir=tmp_path, agent=AgentSettings(checkpoint_enabled=False))
    checkpointer = AgentCheckpointer(settings)

    saver = await checkpointer.open()

    assert isinstance(saver, MemorySaver)

    await checkpointer.close()
    assert checkpointer.saver is None


@pytest.mark.asyncio
async def test_checkpoint_enabled_opens_sqlite_file(tmp_path) -> None:
    pytest.importorskip("langgraph.checkpoint.sqlite.aio")
    from jarvis.agents.checkpointer import AgentCheckpointer
    from jarvis.core.config import paths as _paths

    settings = Settings(data_dir=tmp_path, agent=AgentSettings(checkpoint_enabled=True))
    checkpointer = AgentCheckpointer(settings)

    saver = await checkpointer.open()
    assert saver is not None

    db_path = _paths.agent_checkpoint_db_path(settings.resolved_data_dir)
    assert db_path.exists()

    await checkpointer.close()


@pytest.mark.asyncio
async def test_open_is_idempotent(tmp_path) -> None:
    from jarvis.agents.checkpointer import AgentCheckpointer

    settings = Settings(data_dir=tmp_path, agent=AgentSettings(checkpoint_enabled=False))
    checkpointer = AgentCheckpointer(settings)

    first = await checkpointer.open()
    second = await checkpointer.open()

    assert first is second
    await checkpointer.close()
