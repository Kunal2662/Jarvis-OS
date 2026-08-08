"""Unit tests for `agents/graph.py`'s intent-gating routing function
(Milestone 10, Conversational Orchestration Routing -- see
`docs/ORCHESTRATION_ROUTING_LOGIC_CONTRACT.md`).

`_route_after_intent` is tested in isolation here, the same way
`test_agent_nodes.py` tests individual node factories without a
compiled graph -- fast, deterministic, no LangGraph/LLM involved.
End-to-end verification that the compiled graph actually wires this
function in correctly lives in
`tests/integration/test_agent_orchestrator.py`.
"""

from __future__ import annotations

from jarvis.agents.graph import DEFAULT_INTENT_DIRECT_ROUTE_CONFIDENCE, _route_after_intent


def test_default_confidence_threshold_is_conservative() -> None:
    assert 0.5 < DEFAULT_INTENT_DIRECT_ROUTE_CONFIDENCE <= 1.0


def test_high_confidence_direct_answer_routes_direct() -> None:
    state = {"intent": "direct_answer", "intent_confidence": 0.95}
    assert _route_after_intent(state, direct_route_confidence=0.85) == "direct"


def test_confidence_exactly_at_threshold_routes_direct() -> None:
    state = {"intent": "direct_answer", "intent_confidence": 0.85}
    assert _route_after_intent(state, direct_route_confidence=0.85) == "direct"


def test_low_confidence_direct_answer_routes_assess() -> None:
    """Confidence routing: a direct_answer classification below the bar
    still takes the full context/planning/tool-selection path."""
    state = {"intent": "direct_answer", "intent_confidence": 0.5}
    assert _route_after_intent(state, direct_route_confidence=0.85) == "assess"


def test_tool_use_never_routes_direct_regardless_of_confidence() -> None:
    state = {"intent": "tool_use", "intent_confidence": 0.99}
    assert _route_after_intent(state, direct_route_confidence=0.85) == "assess"


def test_clarification_needed_never_routes_direct() -> None:
    state = {"intent": "clarification_needed", "intent_confidence": 0.99}
    assert _route_after_intent(state, direct_route_confidence=0.85) == "assess"


def test_missing_intent_fields_route_assess() -> None:
    """A state that never reached intent_classifier (or whose
    classification failed and fell back) must not accidentally satisfy
    the direct-route condition via missing-key defaults."""
    assert _route_after_intent({}, direct_route_confidence=0.85) == "assess"


def test_confidence_threshold_is_configurable() -> None:
    state = {"intent": "direct_answer", "intent_confidence": 0.6}
    assert _route_after_intent(state, direct_route_confidence=0.5) == "direct"
    assert _route_after_intent(state, direct_route_confidence=0.7) == "assess"
