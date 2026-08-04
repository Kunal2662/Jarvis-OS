"""Unit tests for the knowledge agent tools — Milestone 10A."""

from __future__ import annotations

import pytest

pytest.importorskip("langchain_core")


class _FakeKnowledgeService:
    def __init__(self, *, ask_answer: str = "Here's what I know.", fail: bool = False) -> None:
        self._ask_answer = ask_answer
        self._fail = fail

    async def ask(self, query: str) -> str:
        if self._fail:
            raise RuntimeError("boom")
        return self._ask_answer

    async def search(self, query: str, *, top_k: int = 5):
        from jarvis.core.interfaces.search import SearchResult

        if not query:
            return []
        return [
            SearchResult(
                id="e1", title="Project X", content="A project.", source="knowledge", score=0.9
            )
        ]


@pytest.mark.asyncio
async def test_ask_knowledge_tool_returns_answer() -> None:
    from jarvis.agents.tools.knowledge_tools import build_knowledge_tools

    tools = build_knowledge_tools(_FakeKnowledgeService(ask_answer="Project X is a thing."))
    ask_tool = next(t for t in tools if t.name == "ask_knowledge")

    result = await ask_tool.ainvoke({"query": "what is Project X"})

    assert result == "Project X is a thing."


@pytest.mark.asyncio
async def test_ask_knowledge_tool_handles_failure() -> None:
    from jarvis.agents.tools.knowledge_tools import build_knowledge_tools

    tools = build_knowledge_tools(_FakeKnowledgeService(fail=True))
    ask_tool = next(t for t in tools if t.name == "ask_knowledge")

    result = await ask_tool.ainvoke({"query": "x"})

    assert "Couldn't answer" in result


@pytest.mark.asyncio
async def test_search_knowledge_tool_formats_results() -> None:
    from jarvis.agents.tools.knowledge_tools import build_knowledge_tools

    tools = build_knowledge_tools(_FakeKnowledgeService())
    search_tool = next(t for t in tools if t.name == "search_knowledge")

    result = await search_tool.ainvoke({"query": "Project X"})

    assert "Project X" in result
    assert "A project." in result


@pytest.mark.asyncio
async def test_search_knowledge_tool_no_results() -> None:
    from jarvis.agents.tools.knowledge_tools import build_knowledge_tools

    tools = build_knowledge_tools(_FakeKnowledgeService())
    search_tool = next(t for t in tools if t.name == "search_knowledge")

    result = await search_tool.ainvoke({"query": ""})

    assert "No matching" in result
