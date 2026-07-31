"""Tool-executor node — actually invokes the tool the selector chose."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from jarvis.agents.state import AgentState
from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

_logger = get_logger("jarvis.agents.nodes.tool_executor")


def make_tool_executor_node(
    tools_by_name: dict[str, BaseTool],
) -> Callable[[AgentState], Awaitable[dict[str, Any]]]:
    async def tool_executor_node(state: AgentState) -> dict[str, Any]:
        name = state.get("tool_name", "")
        args = state.get("tool_args") or {}
        entry: dict[str, Any] = {"tool": name, "args": args}

        tool = tools_by_name.get(name)
        if tool is None:
            entry["error"] = f"Unknown tool: {name!r}"
        else:
            try:
                entry["result"] = await tool.ainvoke(args)
            except Exception as err:  # tool failures must not crash the graph
                _logger.warning("Tool {!r} failed: {}", name, err)
                entry["error"] = str(err)

        tool_calls = [*state.get("tool_calls", []), entry]
        return {
            "tool_calls": tool_calls,
            "step": state.get("step", 0) + 1,
            "last_node": "tool_executor",
        }

    return tool_executor_node
