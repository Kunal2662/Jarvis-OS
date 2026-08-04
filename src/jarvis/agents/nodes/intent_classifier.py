"""Intent Engine (Milestone 10) -- classifies a request into an actionable
intent before planning starts, upstream of ``planner.py``, per M10's Key
Features list in ``docs/MASTER_ROADMAP.md``."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from jarvis.agents.prompting import parse_json_object, safe_complete
from jarvis.agents.state import AgentState

if TYPE_CHECKING:
    from jarvis.core.interfaces.llm_provider import ILLMProvider

_INSTRUCTIONS = (
    "You are JARVIS's intent classification module. Classify the user's "
    'request into exactly one of: "tool_use" (needs a tool or service to '
    'fulfil), "direct_answer" (answerable from knowledge alone, no tool '
    'needed), or "clarification_needed" (too ambiguous to act on).\n'
    "Respond with ONLY a JSON object, no prose, no markdown fences: "
    '{"intent": "<one of the three>", "confidence": <0.0-1.0>}\n'
)
_FALLBACK = '{"intent": "tool_use", "confidence": 0.5}'
_VALID_INTENTS = frozenset({"tool_use", "direct_answer", "clarification_needed"})
_DEFAULT_INTENT = "tool_use"
_DEFAULT_CONFIDENCE = 0.5


def make_intent_classifier_node(
    llm: ILLMProvider,
) -> Callable[[AgentState], Awaitable[dict[str, Any]]]:
    async def intent_classifier_node(state: AgentState) -> dict[str, Any]:
        prompt = f"{_INSTRUCTIONS}\nUser request: {state['prompt']}"
        raw = await safe_complete(llm, prompt, fallback=_FALLBACK)
        decision = parse_json_object(raw)

        intent = decision.get("intent")
        if intent not in _VALID_INTENTS:
            intent = _DEFAULT_INTENT

        try:
            confidence = float(decision.get("confidence", _DEFAULT_CONFIDENCE))
        except (TypeError, ValueError):
            confidence = _DEFAULT_CONFIDENCE
        confidence = max(0.0, min(1.0, confidence))

        return {
            "intent": intent,
            "intent_confidence": confidence,
            "last_node": "intent_classifier",
        }

    return intent_classifier_node
