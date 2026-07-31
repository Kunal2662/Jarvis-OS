"""Planner node — first step of the graph: turn a prompt into a short plan."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from jarvis.agents.prompting import format_tool_descriptions, safe_complete
from jarvis.agents.state import AgentState

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

    from jarvis.core.interfaces.llm_provider import ILLMProvider

_FALLBACK_PLAN = "Answer the user's request directly without using any tools."


def make_planner_node(
    llm: ILLMProvider, tools: list[BaseTool]
) -> Callable[[AgentState], Awaitable[dict[str, Any]]]:
    tool_desc = format_tool_descriptions(tools)

    async def planner_node(state: AgentState) -> dict[str, Any]:
        prompt = (
            "You are JARVIS's planning module. Given the user's request and "
            "the tools available to you, write a short plan (1-4 numbered "
            "steps) for how to fulfil it. If no tool is needed, say so and "
            "plan to answer directly.\n\n"
            f"Available tools:\n{tool_desc}\n\n"
            f"User request: {state['prompt']}"
        )
        plan = await safe_complete(llm, prompt, fallback=_FALLBACK_PLAN)
        return {"plan": plan, "last_node": "planner"}

    return planner_node
