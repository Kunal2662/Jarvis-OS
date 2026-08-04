"""Unit tests for the intelligence agent tools — Milestone 10B."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

pytest.importorskip("langchain_core")


@dataclass
class _FakeGoal:
    id: str = "g1"
    title: str = "Learn Rust"
    progress_percent: int = 0
    status: str = "active"


@dataclass
class _FakeSuggestion:
    title: str
    reason: str
    score: float = 0.5
    kind: str = "goal"


@dataclass
class _FakeBriefing:
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    goals_due_soon: list = field(default_factory=list)
    top_suggestions: list = field(default_factory=list)
    routine_reminders: list = field(default_factory=list)


class _FakeIntelligenceService:
    def __init__(self) -> None:
        self.created: list[tuple[str, str]] = []

    async def create_goal(self, title: str, *, description: str = "", **kwargs):
        self.created.append((title, description))
        return _FakeGoal(title=title)

    async def list_goals(self, *, status: str = "active", **kwargs):
        if status != "active":
            return []
        return [_FakeGoal(id="g1", title="Learn Rust", progress_percent=40)]

    async def update_goal_progress(self, goal_id: str, progress_percent: int):
        if goal_id != "g1":
            return None
        return _FakeGoal(id=goal_id, title="Learn Rust", progress_percent=progress_percent)

    async def predict_suggestions(self, *, top_k: int = 5, **kwargs):
        return [
            _FakeSuggestion(title="You often do this now: make_coffee", reason="observed 3 times")
        ]

    async def generate_daily_briefing(self, **kwargs):
        return _FakeBriefing(
            goals_due_soon=["Submit taxes"],
            top_suggestions=[
                _FakeSuggestion(title="You often do this now: make_coffee", reason="x")
            ],
        )


@pytest.mark.asyncio
async def test_create_goal_tool() -> None:
    from jarvis.agents.tools.intelligence_tools import build_intelligence_tools

    tools = build_intelligence_tools(_FakeIntelligenceService())
    create = next(t for t in tools if t.name == "create_goal")

    result = await create.ainvoke({"title": "Learn Rust"})

    assert "Learn Rust" in result


@pytest.mark.asyncio
async def test_list_goals_tool() -> None:
    from jarvis.agents.tools.intelligence_tools import build_intelligence_tools

    tools = build_intelligence_tools(_FakeIntelligenceService())
    list_tool = next(t for t in tools if t.name == "list_goals")

    result = await list_tool.ainvoke({"status": "active"})

    assert "Learn Rust" in result
    assert "40%" in result


@pytest.mark.asyncio
async def test_list_goals_tool_no_results() -> None:
    from jarvis.agents.tools.intelligence_tools import build_intelligence_tools

    tools = build_intelligence_tools(_FakeIntelligenceService())
    list_tool = next(t for t in tools if t.name == "list_goals")

    result = await list_tool.ainvoke({"status": "completed"})

    assert "No completed goals" in result


@pytest.mark.asyncio
async def test_update_goal_progress_tool() -> None:
    from jarvis.agents.tools.intelligence_tools import build_intelligence_tools

    tools = build_intelligence_tools(_FakeIntelligenceService())
    update = next(t for t in tools if t.name == "update_goal_progress")

    result = await update.ainvoke({"goal_id": "g1", "progress_percent": 75})

    assert "75%" in result


@pytest.mark.asyncio
async def test_update_goal_progress_tool_unknown_goal() -> None:
    from jarvis.agents.tools.intelligence_tools import build_intelligence_tools

    tools = build_intelligence_tools(_FakeIntelligenceService())
    update = next(t for t in tools if t.name == "update_goal_progress")

    result = await update.ainvoke({"goal_id": "missing", "progress_percent": 50})

    assert "No goal found" in result


@pytest.mark.asyncio
async def test_get_suggestions_tool() -> None:
    from jarvis.agents.tools.intelligence_tools import build_intelligence_tools

    tools = build_intelligence_tools(_FakeIntelligenceService())
    suggestions_tool = next(t for t in tools if t.name == "get_suggestions")

    result = await suggestions_tool.ainvoke({})

    assert "make_coffee" in result


@pytest.mark.asyncio
async def test_get_daily_briefing_tool() -> None:
    from jarvis.agents.tools.intelligence_tools import build_intelligence_tools

    tools = build_intelligence_tools(_FakeIntelligenceService())
    briefing_tool = next(t for t in tools if t.name == "get_daily_briefing")

    result = await briefing_tool.ainvoke({})

    assert "Submit taxes" in result
    assert "make_coffee" in result
