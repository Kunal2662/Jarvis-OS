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

    # Planner
    plan: str

    # Tool selector
    next_action: str  # "tool" | "final"
    tool_name: str
    tool_args: dict[str, Any]

    # Executor
    tool_calls: list[dict[str, Any]]
    step: int

    # Critic
    critique: str
    needs_more_work: bool

    # Responder
    final_response: str

    # Diagnostics
    error: str | None
    last_node: str
