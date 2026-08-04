"""Tool-selector node — decides, one step at a time, whether to call a tool
or answer the user directly, given the plan and any tool calls so far."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from jarvis.agents.prompting import (
    UNTRUSTED_TOOL_OUTPUT_NOTICE,
    format_tool_call_history,
    format_tool_descriptions,
    parse_json_object,
    safe_complete,
)
from jarvis.agents.state import AgentState

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

    from jarvis.core.interfaces.llm_provider import ILLMProvider

_INSTRUCTIONS = (
    "You are JARVIS's tool-selection module. Given the plan and the tool "
    "calls made so far, decide the next action.\n"
    "Respond with ONLY a JSON object, no prose, no markdown fences, in one "
    "of these three shapes:\n"
    '  {"action": "tool", "tool": "<tool_name>", "args": {<tool arguments>}}\n'
    '  {"action": "tool_parallel", "tools": ['
    '{"tool": "<tool_name>", "args": {<tool arguments>}}, ...]}'
    " -- use this only when two or more remaining steps are genuinely "
    "independent of each other's results\n"
    '  {"action": "final", "final_text": "<answer to the user>"}\n'
)
_FALLBACK = '{"action": "final", "final_text": ""}'


def make_tool_selector_node(
    llm: ILLMProvider, tools: list[BaseTool]
) -> Callable[[AgentState], Awaitable[dict[str, Any]]]:
    tool_desc = format_tool_descriptions(tools)
    valid_names = {t.name for t in tools}

    async def tool_selector_node(state: AgentState) -> dict[str, Any]:
        history = format_tool_call_history(state.get("tool_calls", []))
        prompt = (
            f"{_INSTRUCTIONS}\n{UNTRUSTED_TOOL_OUTPUT_NOTICE}\n\n"
            f"Available tools:\n{tool_desc}\n\n"
            f"Plan:\n{state.get('plan', '')}\n\n"
            f"User request: {state['prompt']}\n\n"
            f"Tool calls so far:\n{history}"
        )
        raw = await safe_complete(llm, prompt, fallback=_FALLBACK)
        decision = parse_json_object(raw)
        action = decision.get("action")

        if action == "tool" and decision.get("tool") in valid_names:
            return {
                "next_action": "tool",
                "tool_name": decision["tool"],
                "tool_args": decision.get("args") or {},
                "last_node": "tool_selector",
            }

        if action == "tool_parallel":
            raw_calls = decision.get("tools")
            calls = _valid_parallel_calls(raw_calls, valid_names)
            if calls:
                return {
                    "next_action": "tool_parallel",
                    "pending_tool_calls": calls,
                    "last_node": "tool_selector",
                }

        return {
            "next_action": "final",
            "final_response": str(decision.get("final_text") or ""),
            "last_node": "tool_selector",
        }

    return tool_selector_node


def _valid_parallel_calls(raw_calls: Any, valid_names: set[str]) -> list[dict[str, Any]]:
    """Filter a hallucination-prone LLM ``tools`` list down to well-formed,
    known-tool calls only -- mirrors ``tool_selector_node``'s existing
    "never trust a hallucinated tool name through to the executor" rule
    (see ``test_tool_selector_node_rejects_unknown_tool_name``) for the
    parallel-dispatch shape."""
    if not isinstance(raw_calls, list):
        return []
    calls: list[dict[str, Any]] = []
    for entry in raw_calls:
        if not isinstance(entry, dict):
            continue
        name = entry.get("tool")
        if name not in valid_names:
            continue
        calls.append({"tool": name, "args": entry.get("args") or {}})
    return calls
