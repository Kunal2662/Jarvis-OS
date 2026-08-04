"""Shared state shape threaded through every LangGraph node.

A plain ``TypedDict`` rather than a Pydantic model: LangGraph merges each
node's *partial* return dict into this state between steps, which is the
idiomatic ``StateGraph`` pattern and keeps every node's return value a
trivially checkpoint-serializable ``dict``.
"""

from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    # Input
    prompt: str
    thread_id: str
    max_steps: int

    # Intent Engine (Milestone 10)
    intent: str  # "tool_use" | "direct_answer" | "clarification_needed"
    intent_confidence: float

    # Context Engine (Milestone 10) -- assembled from M3 Memory only; the
    # M10A knowledge-graph half of Context Engine is deferred pending M10A.
    context: str

    # Planner
    plan: str

    # Tool selector
    next_action: str  # "tool" | "tool_parallel" | "final"
    tool_name: str
    tool_args: dict[str, Any]
    # Milestone 10 AC1 (absorbs M7 Phase 3): independent tool calls the
    # selector wants dispatched concurrently in one step. Only populated
    # when next_action == "tool_parallel"; the single-tool tool_name/
    # tool_args fields above are unchanged and still used for next_action
    # == "tool", preserving the pre-M10 single-tool shape byte-for-byte.
    pending_tool_calls: list[dict[str, Any]]

    # Permission Validation (Milestone 10 AC3, interim -- see
    # agents/permission.py). Only meaningful for the single-tool path;
    # the parallel path records denials directly into tool_calls instead.
    permission_denied: bool

    # Executor
    tool_calls: list[dict[str, Any]]
    step: int

    # Critic
    critique: str
    needs_more_work: bool

    # Responder / Decision Engine (Milestone 10)
    final_response: str
    response_mode: str  # "direct" | "composed"

    # Diagnostics
    error: str | None
    last_node: str
