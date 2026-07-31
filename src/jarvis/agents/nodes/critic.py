"""Critic node — self-critique: has the plan actually been satisfied yet?"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from jarvis.agents.prompting import (
    UNTRUSTED_TOOL_OUTPUT_NOTICE,
    format_tool_call_history,
    parse_json_object,
    safe_complete,
)
from jarvis.agents.state import AgentState

if TYPE_CHECKING:
    from jarvis.core.interfaces.llm_provider import ILLMProvider

_INSTRUCTIONS = (
    "You are JARVIS's self-critique module. Given the plan and the tool "
    "calls made so far, decide whether the user's request has been fully "
    "satisfied.\nRespond with ONLY a JSON object, no prose, no markdown "
    'fences: {"complete": true|false, "reason": "<one short sentence>"}\n'
)
_FALLBACK = '{"complete": true, "reason": "critic call failed; stopping to avoid a stuck loop"}'


def make_critic_node(llm: ILLMProvider) -> Callable[[AgentState], Awaitable[dict[str, Any]]]:
    async def critic_node(state: AgentState) -> dict[str, Any]:
        history = format_tool_call_history(state.get("tool_calls", []))
        prompt = (
            f"{_INSTRUCTIONS}\n{UNTRUSTED_TOOL_OUTPUT_NOTICE}\n\n"
            f"Plan:\n{state.get('plan', '')}\n\n"
            f"User request: {state['prompt']}\n\nTool calls:\n{history}"
        )
        raw = await safe_complete(llm, prompt, fallback=_FALLBACK)
        decision = parse_json_object(raw)
        complete = bool(decision.get("complete", True))
        return {
            "needs_more_work": not complete,
            "critique": str(decision.get("reason") or ""),
            "last_node": "critic",
        }

    return critic_node
