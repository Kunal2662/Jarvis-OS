"""Integration tests for :class:`AgentOrchestrator` (Milestone 5-Agents).

Exercises the real compiled LangGraph state machine end-to-end — planner
-> tool_selector -> tool_executor -> critic -> responder, including the
loop-back edge and the ``max_steps`` hard stop — with a fake
memory service (no real DB/vector store needed) and
:class:`ScriptedFakeLLM` standing in for every LLM call.
"""

from __future__ import annotations

import pytest

from jarvis.core.config.settings import AgentSettings, Settings
from jarvis.core.events.event_bus import EventBus
from jarvis.core.events.events import AgentStepEvent
from jarvis.core.interfaces.agent import AgentRequest
from tests.fakes.fake_scripted_llm import ScriptedFakeLLM

pytest.importorskip("langgraph")
pytest.importorskip("langchain_core")


class _FakeMemoryService:
    async def remember(self, content: str, *, memory_type: str = "long_term") -> str:
        return "mem-1"

    async def recall(self, query: str, *, top_k: int = 5):
        return []


def _settings(tmp_path, *, max_steps: int = 10) -> Settings:
    return Settings(
        data_dir=tmp_path,
        agent=AgentSettings(checkpoint_enabled=False, max_steps=max_steps, timeout_seconds=30),
    )


@pytest.mark.asyncio
async def test_invoke_answers_directly_when_no_tool_needed(tmp_path) -> None:
    from jarvis.agents.orchestrator import AgentOrchestrator

    llm = ScriptedFakeLLM(
        {
            "tool-selection module": (
                '{"action": "final", "final_text": "Paris is the capital of France."}'
            ),
        }
    )
    orchestrator = AgentOrchestrator(
        _settings(tmp_path), llm, memory=None, automation=None, browser=None
    )

    response = await orchestrator.invoke(AgentRequest(prompt="What is the capital of France?"))

    assert response.text == "Paris is the capital of France."
    assert response.steps == 0
    assert response.metadata["tool_calls"] == []

    await orchestrator.stop()


@pytest.mark.asyncio
async def test_invoke_calls_a_tool_then_responds(tmp_path) -> None:
    from jarvis.agents.orchestrator import AgentOrchestrator

    llm = ScriptedFakeLLM(
        {
            # First tool_selector call has no history yet -> pick the tool.
            "(none yet)": (
                '{"action": "tool", "tool": "recall_memory", "args": {"query": "birthday"}}'
            ),
            "self-critique module": '{"complete": true, "reason": "recalled successfully"}',
            "Compose the final answer": "Your birthday note has been recalled.",
        }
    )
    orchestrator = AgentOrchestrator(
        _settings(tmp_path), llm, memory=_FakeMemoryService(), automation=None, browser=None
    )

    response = await orchestrator.invoke(AgentRequest(prompt="What's my birthday note?"))

    assert response.steps == 1
    assert response.text == "Your birthday note has been recalled."
    assert response.metadata["tool_calls"][0]["tool"] == "recall_memory"

    await orchestrator.stop()


@pytest.mark.asyncio
async def test_invoke_stops_at_max_steps_even_if_critic_never_satisfied(tmp_path) -> None:
    """A critic that always says "keep going" must not loop forever —
    the hard ``max_steps`` cap (see ``agents/graph.py``'s router
    functions) has to win."""
    from jarvis.agents.orchestrator import AgentOrchestrator

    llm = ScriptedFakeLLM(
        {
            "tool-selection module": (
                '{"action": "tool", "tool": "recall_memory", "args": {"query": "x"}}'
            ),
            "self-critique module": '{"complete": false, "reason": "never satisfied"}',
            "Compose the final answer": "Here's what I found so far.",
        }
    )
    orchestrator = AgentOrchestrator(
        _settings(tmp_path, max_steps=2),
        llm,
        memory=_FakeMemoryService(),
        automation=None,
        browser=None,
    )

    response = await orchestrator.invoke(AgentRequest(prompt="Keep digging."))

    assert response.steps == 2  # capped, not runaway
    assert len(response.metadata["tool_calls"]) == 2
    assert response.text == "Here's what I found so far."

    await orchestrator.stop()


@pytest.mark.asyncio
async def test_invoke_publishes_agent_step_events(tmp_path) -> None:
    from jarvis.agents.orchestrator import AgentOrchestrator

    llm = ScriptedFakeLLM({"tool-selection module": '{"action": "final", "final_text": "ok"}'})
    bus = EventBus()
    received: list[AgentStepEvent] = []
    bus.subscribe(AgentStepEvent, received.append)

    orchestrator = AgentOrchestrator(
        _settings(tmp_path), llm, memory=None, automation=None, browser=None, event_bus=bus
    )

    await orchestrator.invoke(AgentRequest(prompt="hi"))

    assert received, "expected at least one AgentStepEvent to be published"
    assert received[-1].node == "responder"

    await orchestrator.stop()


@pytest.mark.asyncio
async def test_stream_yields_the_final_response_text(tmp_path) -> None:
    from jarvis.agents.orchestrator import AgentOrchestrator

    llm = ScriptedFakeLLM(
        {"tool-selection module": '{"action": "final", "final_text": "streamed answer here"}'}
    )
    orchestrator = AgentOrchestrator(
        _settings(tmp_path), llm, memory=None, automation=None, browser=None
    )

    chunks = [chunk async for chunk in orchestrator.stream(AgentRequest(prompt="hi"))]

    assert "".join(chunks).strip() == "streamed answer here"

    await orchestrator.stop()


@pytest.mark.asyncio
async def test_invoke_dispatches_parallel_tool_calls(tmp_path) -> None:
    """Milestone 10 AC1 (absorbs M7 Phase 3): two independent tool calls
    dispatch in one graph step, not sequentially across two loop-backs."""
    from jarvis.agents.orchestrator import AgentOrchestrator

    llm = ScriptedFakeLLM(
        {
            "(none yet)": (
                '{"action": "tool_parallel", "tools": '
                '[{"tool": "remember", "args": {"content": "note one"}}, '
                '{"tool": "recall_memory", "args": {"query": "note"}}]}'
            ),
            "self-critique module": '{"complete": true, "reason": "done"}',
            "Compose the final answer": "Saved and recalled.",
        }
    )
    orchestrator = AgentOrchestrator(
        _settings(tmp_path), llm, memory=_FakeMemoryService(), automation=None, browser=None
    )

    response = await orchestrator.invoke(AgentRequest(prompt="remember and recall a note"))

    assert response.steps == 2
    tool_names = {c["tool"] for c in response.metadata["tool_calls"]}
    assert tool_names == {"remember", "recall_memory"}
    assert response.text == "Saved and recalled."

    await orchestrator.stop()


@pytest.mark.asyncio
async def test_invoke_denies_gated_tool_without_confirmation(tmp_path) -> None:
    """Milestone 10 AC3 (interim Permission Validation): a denied
    permission blocks execution -- run_automation is denied before
    AutomationService.run_command is ever called."""
    from jarvis.agents.orchestrator import AgentOrchestrator

    class _FakeAutomationService:
        async def run_command(self, instruction: str) -> object:
            raise AssertionError("run_automation must be denied before execution")

    llm = ScriptedFakeLLM(
        {
            "(none yet)": (
                '{"action": "tool", "tool": "run_automation", '
                '"args": {"instruction": "shutdown"}}'
            ),
            "self-critique module": '{"complete": true, "reason": "denied"}',
            "Compose the final answer": "I couldn't do that without your confirmation.",
        }
    )
    orchestrator = AgentOrchestrator(
        _settings(tmp_path), llm, memory=None, automation=_FakeAutomationService(), browser=None
    )

    response = await orchestrator.invoke(AgentRequest(prompt="shut down the computer"))

    assert response.steps == 1
    assert response.metadata["tool_calls"][0]["tool"] == "run_automation"
    assert response.metadata["tool_calls"][0]["error"].startswith("Denied:")

    await orchestrator.stop()


@pytest.mark.asyncio
async def test_stream_yields_real_tokens_for_composed_response(tmp_path) -> None:
    """Milestone 10 AC2: once a tool result needs composing into an answer,
    stream() must yield real per-token output from ``llm.stream()``, not a
    word-chunked replay of an already-composed string. ``ScriptedFakeLLM``
    yields one chunk per whitespace-split word (5, for this sentence);
    the old ``_chunk_for_streaming`` replay path groups 4 words per chunk
    (2, for this sentence) -- the chunk count is what proves which path
    ran."""
    from jarvis.agents.orchestrator import AgentOrchestrator

    llm = ScriptedFakeLLM(
        {
            "(none yet)": (
                '{"action": "tool", "tool": "recall_memory", "args": {"query": "birthday"}}'
            ),
            "self-critique module": '{"complete": true, "reason": "done"}',
            "Compose the final answer": "Your birthday is in March.",
        }
    )
    orchestrator = AgentOrchestrator(
        _settings(tmp_path), llm, memory=_FakeMemoryService(), automation=None, browser=None
    )

    chunks = [
        chunk async for chunk in orchestrator.stream(AgentRequest(prompt="when's my birthday?"))
    ]

    assert "".join(chunks).strip() == "Your birthday is in March."
    assert len(chunks) == 5  # one per word -- real token-level, not re-chunked

    await orchestrator.stop()


@pytest.mark.asyncio
async def test_start_and_stop_are_idempotent(tmp_path) -> None:
    from jarvis.agents.orchestrator import AgentOrchestrator

    llm = ScriptedFakeLLM({})
    orchestrator = AgentOrchestrator(
        _settings(tmp_path), llm, memory=None, automation=None, browser=None
    )

    await orchestrator.start()
    await orchestrator.start()  # no-op second call
    await orchestrator.stop()
    await orchestrator.stop()  # no-op second call


@pytest.mark.asyncio
async def test_invoke_with_real_sqlite_checkpointer(tmp_path) -> None:
    """Regression test: every other test in this file runs with
    ``checkpoint_enabled=False`` (in-memory saver). That previously hid a
    real bug -- ``AgentCheckpointer.open()`` succeeded against the real
    ``AsyncSqliteSaver``, but any actual graph invocation raised
    ``AttributeError: 'Connection' object has no attribute 'is_alive'``
    from inside ``langgraph-checkpoint-sqlite``'s own setup path (an
    upstream incompatibility with newer ``aiosqlite`` releases -- see the
    ``aiosqlite`` pin comment in ``pyproject.toml``). Only caught by a
    manual end-to-end smoke run outside pytest, not by the unit-level
    open()/close() coverage in ``test_agent_checkpointer.py`` -- this
    closes that gap."""
    pytest.importorskip("langgraph.checkpoint.sqlite.aio")
    from jarvis.agents.orchestrator import AgentOrchestrator

    settings = Settings(
        data_dir=tmp_path,
        agent=AgentSettings(checkpoint_enabled=True, max_steps=5, timeout_seconds=30),
    )
    llm = ScriptedFakeLLM({"tool-selection module": '{"action": "final", "final_text": "ok"}'})
    orchestrator = AgentOrchestrator(settings, llm, memory=None, automation=None, browser=None)

    response = await orchestrator.invoke(AgentRequest(prompt="hi"))

    assert response.text == "ok"

    from jarvis.core.config import paths as _paths

    assert _paths.agent_checkpoint_db_path(settings.resolved_data_dir).exists()

    await orchestrator.stop()
