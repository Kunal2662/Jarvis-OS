"""Agent tools wrapping :class:`~jarvis.services.intelligence_service.IntelligenceService`
(Milestone 10B)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool, tool

from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.services.intelligence_service import IntelligenceService

_logger = get_logger("jarvis.agents.tools.intelligence")


def build_intelligence_tools(intelligence: IntelligenceService) -> list[BaseTool]:
    @tool
    async def create_goal(title: str, description: str = "") -> str:
        """Create a new goal for the user to track (e.g. "learn Spanish",
        "finish the quarterly report"). Returns the new goal's id."""
        try:
            goal = await intelligence.create_goal(title, description=description)
        except Exception as err:
            _logger.warning("create_goal tool failed: {}", err)
            return f"Failed to create goal: {err}"
        return f"Created goal {goal.id}: {goal.title}"

    @tool
    async def list_goals(status: str = "active") -> str:
        """List the user's goals. ``status`` is one of active, completed,
        abandoned. Returns each goal's id, title, and progress."""
        goals = await intelligence.list_goals(status=status)
        if not goals:
            return f"No {status} goals found."
        return "\n".join(f"- [{g.id}] {g.title} ({g.progress_percent}% complete)" for g in goals)

    @tool
    async def update_goal_progress(goal_id: str, progress_percent: int) -> str:
        """Update how far along a goal is, from 0 to 100. Reaching 100
        automatically marks the goal completed."""
        goal = await intelligence.update_goal_progress(goal_id, progress_percent)
        if goal is None:
            return f"No goal found with id {goal_id!r}."
        return (
            f"Goal {goal.title!r} is now {goal.progress_percent}% complete (status: {goal.status})."
        )

    @tool
    async def get_suggestions(top_k: int = 5) -> str:
        """Get JARVIS's current predictive suggestions -- goals coming
        due and routines the user often does around this time."""
        suggestions = await intelligence.predict_suggestions(top_k=top_k)
        if not suggestions:
            return "No suggestions right now."
        return "\n".join(f"- {s.title} ({s.reason})" for s in suggestions)

    @tool
    async def get_daily_briefing() -> str:
        """Generate today's briefing: goals due soon and top suggestions."""
        briefing = await intelligence.generate_daily_briefing()
        lines = []
        if briefing.goals_due_soon:
            lines.append("Goals due soon: " + ", ".join(briefing.goals_due_soon))
        if briefing.top_suggestions:
            lines.append("Suggestions:")
            lines.extend(f"  - {s.title}" for s in briefing.top_suggestions)
        return "\n".join(lines) if lines else "Nothing notable today."

    return [create_goal, list_goals, update_goal_progress, get_suggestions, get_daily_briefing]
