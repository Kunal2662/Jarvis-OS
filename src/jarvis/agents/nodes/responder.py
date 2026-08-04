"""Responder / Decision Engine node — composes the final answer handed back
to the caller (Milestone 5-Agents; retitled Decision Engine in Milestone
10's Key Features list, which describes it as "the responder node's
successor, deciding final response shape and routing")."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from jarvis.agents.prompting import (
    UNTRUSTED_TOOL_OUTPUT_NOTICE,
    format_tool_call_history,
    safe_complete,
)
from jarvis.agents.state import AgentState

if TYPE_CHECKING:
    from jarvis.core.interfaces.llm_provider import ILLMProvider

_FALLBACK = "I wasn't able to complete that request."


def build_final_response_prompt(state: AgentState) -> str:
    """Pure prompt-construction, no LLM call -- shared by
    :func:`make_responder_node`'s blocking ``invoke()`` path and
    :meth:`~jarvis.agents.orchestrator.AgentOrchestrator.stream`'s real
    token-streaming path (Milestone 10 AC2), so the two never drift."""
    history = format_tool_call_history(state.get("tool_calls", []))
    return (
        "Compose the final answer to the user based on the plan and any "
        "tool results below. Be concise and helpful; do not mention the "
        "plan or tool machinery explicitly unless the user asked about "
        f"it.\n{UNTRUSTED_TOOL_OUTPUT_NOTICE}\n\n"
        f"User request: {state['prompt']}\n\nPlan:\n{state.get('plan', '')}\n\n"
        f"Tool results:\n{history}"
    )


def make_responder_node(llm: ILLMProvider) -> Callable[[AgentState], Awaitable[dict[str, Any]]]:
    async def responder_node(state: AgentState) -> dict[str, Any]:
        # The tool-selector already wrote a direct answer when no tool was
        # needed (the "final" branch) — nothing left to compose.
        if state.get("final_response"):
            return {"last_node": "responder", "response_mode": "direct"}

        prompt = build_final_response_prompt(state)
        text = await safe_complete(llm, prompt, fallback=_FALLBACK)
        return {"final_response": text, "response_mode": "composed", "last_node": "responder"}

    return responder_node
