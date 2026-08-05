"""Workspace agent-tool tests -- Milestone 11 Task Group D.

Tiny duck-typed fake assistant, matching ``test_agent_tools_registry``'s
own approach: each fake implements only the method its tool calls, so
these assert the *tool wrapper* -- its text contract and its failure
handling -- without a database, an LLM or a container.
"""

from __future__ import annotations

import pytest

from jarvis.core.interfaces.search import SearchResult
from jarvis.domain.ai_workspace.models import ContextItem, ContextSection, pack

pytest.importorskip("langchain_core")


class _FakeAssistant:
    def __init__(self, *, workspaces=None, results=None, answer="An answer.") -> None:
        self._workspaces = (
            workspaces
            if workspaces is not None
            else [{"id": "w1", "name": "Research", "status": "active"}]
        )
        self._results = (
            results
            if results is not None
            else [
                SearchResult(
                    id="n1",
                    title="Standup",
                    content="we discussed the migration",
                    source="notes",
                    score=1.0,
                )
            ]
        )
        self._answer = answer
        self.asked: list[tuple[str, str]] = []

    async def list_workspaces(self):
        return self._workspaces

    async def context(self, workspace_id: str, *, budget_chars: int | None = None):
        return pack(
            [
                ContextSection(
                    name="workspace",
                    items=(ContextItem(title="Research", detail="the migration"),),
                    total=1,
                )
            ],
            workspace_id=workspace_id,
            workspace_name="Research",
        )

    async def retrieve(self, workspace_id: str, query: str, **kwargs):
        return self._results

    async def ask(self, workspace_id: str, question: str, **kwargs):
        from jarvis.services.workspace_ai_service import AssistResult

        self.asked.append((workspace_id, question))
        return AssistResult(workspace_id=workspace_id, mode="ask", answer=self._answer)

    async def summarize(self, workspace_id: str, **kwargs):
        from jarvis.services.workspace_ai_service import AssistResult

        return AssistResult(workspace_id=workspace_id, mode="summarize", answer=self._answer)


class _BrokenAssistant:
    async def list_workspaces(self):
        return []

    async def context(self, workspace_id: str, **kwargs):
        raise RuntimeError("database is on fire")

    async def retrieve(self, workspace_id: str, query: str, **kwargs):
        raise RuntimeError("database is on fire")

    async def ask(self, workspace_id: str, question: str, **kwargs):
        raise RuntimeError("database is on fire")

    async def summarize(self, workspace_id: str, **kwargs):
        raise RuntimeError("database is on fire")


def _tools(assistant):
    from jarvis.agents.tools.workspace_tools import build_workspace_tools

    return {tool.name: tool for tool in build_workspace_tools(assistant)}


# --- the five tools -------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_workspaces_reports_ids_the_other_tools_need() -> None:
    result = await _tools(_FakeAssistant())["list_workspaces"].ainvoke({})

    assert "[w1] Research (active)" in result


@pytest.mark.asyncio
async def test_list_workspaces_says_so_when_there_are_none() -> None:
    result = await _tools(_FakeAssistant(workspaces=[]))["list_workspaces"].ainvoke({})

    assert result == "No workspaces exist yet."


@pytest.mark.asyncio
async def test_workspace_context_renders_the_context() -> None:
    result = await _tools(_FakeAssistant())["workspace_context"].ainvoke({"workspace_id": "w1"})

    assert "Research" in result
    assert "the migration" in result


@pytest.mark.asyncio
async def test_search_workspace_labels_each_hit_with_its_source() -> None:
    result = await _tools(_FakeAssistant())["search_workspace"].ainvoke(
        {"workspace_id": "w1", "query": "migration"}
    )

    assert "[notes] Standup" in result


@pytest.mark.asyncio
async def test_search_workspace_says_so_on_no_match() -> None:
    result = await _tools(_FakeAssistant(results=[]))["search_workspace"].ainvoke(
        {"workspace_id": "w1", "query": "nothing"}
    )

    assert result == "Nothing in that workspace matches."


@pytest.mark.asyncio
async def test_ask_workspace_returns_the_answer_and_passes_the_question() -> None:
    assistant = _FakeAssistant(answer="Friday.")

    result = await _tools(assistant)["ask_workspace"].ainvoke(
        {"workspace_id": "w1", "question": "when is cutover?"}
    )

    assert result == "Friday."
    assert assistant.asked == [("w1", "when is cutover?")]


@pytest.mark.asyncio
async def test_summarize_workspace_returns_the_answer() -> None:
    result = await _tools(_FakeAssistant(answer="All quiet."))["summarize_workspace"].ainvoke(
        {"workspace_id": "w1"}
    )

    assert result == "All quiet."


# --- failure handling -----------------------------------------------------------


@pytest.mark.asyncio
async def test_every_tool_reports_a_failure_as_text_not_an_exception() -> None:
    """One bad tool call must not crash the graph -- the posture
    ``agents/nodes/tool_executor.py`` already applies."""
    tools = _tools(_BrokenAssistant())

    for name, args in (
        ("workspace_context", {"workspace_id": "w1"}),
        ("search_workspace", {"workspace_id": "w1", "query": "q"}),
        ("ask_workspace", {"workspace_id": "w1", "question": "q"}),
        ("summarize_workspace", {"workspace_id": "w1"}),
    ):
        result = await tools[name].ainvoke(args)
        assert "Couldn't" in result
        assert "on fire" in result


# --- registry composition -------------------------------------------------------


def test_the_registry_includes_the_workspace_tools_when_wired() -> None:
    from jarvis.agents.tools.registry import build_tool_registry

    names = {t.name for t in build_tool_registry(workspace_assistant=_FakeAssistant())}

    assert names == {
        "list_workspaces",
        "workspace_context",
        "search_workspace",
        "ask_workspace",
        "summarize_workspace",
    }


def test_the_registry_omits_them_when_not_wired() -> None:
    """Optional like every other service in the registry, so a narrower
    agent still builds."""
    from jarvis.agents.tools.registry import build_tool_registry

    assert build_tool_registry() == []
