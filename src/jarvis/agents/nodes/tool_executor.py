"""Tool-executor node — actually invokes the tool(s) the selector chose.

Milestone 10 AC1 (absorbing M7 Phase 3's deferred cross-tool-parallelism
scope): when the selector proposed independent tool calls via the
``tool_parallel`` shape, this node dispatches them concurrently, bounded by
``AgentSettings.max_parallel_steps`` -- declared in Milestone 7 for exactly
this purpose but unread by any code until now. The pre-M10 single-tool path
(``next_action == "tool"``) is unchanged below, byte-for-byte.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from jarvis.agents.state import AgentState
from jarvis.core.logging.logger import get_logger
from jarvis.utils.async_utils import gather_with_concurrency

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

_logger = get_logger("jarvis.agents.nodes.tool_executor")


async def _invoke_one(tool: BaseTool | None, name: str, args: dict[str, Any]) -> dict[str, Any]:
    entry: dict[str, Any] = {"tool": name, "args": args}
    if tool is None:
        entry["error"] = f"Unknown tool: {name!r}"
        return entry
    try:
        entry["result"] = await tool.ainvoke(args)
    except Exception as err:  # tool failures must not crash the graph
        _logger.warning("Tool {!r} failed: {}", name, err)
        entry["error"] = str(err)
    return entry


def _invoke_call(
    tools_by_name: dict[str, BaseTool], call: dict[str, Any]
) -> Awaitable[dict[str, Any]]:
    name = call.get("tool", "")
    args = call.get("args") or {}
    return _invoke_one(tools_by_name.get(name), name, args)


def make_tool_executor_node(
    tools_by_name: dict[str, BaseTool],
    *,
    max_parallel_steps: int = 4,
) -> Callable[[AgentState], Awaitable[dict[str, Any]]]:
    async def tool_executor_node(state: AgentState) -> dict[str, Any]:
        if state.get("next_action") == "tool_parallel":
            calls = state.get("pending_tool_calls") or []
            results = await gather_with_concurrency(
                max(1, max_parallel_steps),
                *(_invoke_call(tools_by_name, call) for call in calls),
            )
            tool_calls = [*state.get("tool_calls", []), *results]
            return {
                "tool_calls": tool_calls,
                "step": state.get("step", 0) + len(results),
                "pending_tool_calls": [],
                "last_node": "tool_executor",
            }

        name = state.get("tool_name", "")
        args = state.get("tool_args") or {}
        entry = await _invoke_one(tools_by_name.get(name), name, args)

        tool_calls = [*state.get("tool_calls", []), entry]
        return {
            "tool_calls": tool_calls,
            "step": state.get("step", 0) + 1,
            "last_node": "tool_executor",
        }

    return tool_executor_node
