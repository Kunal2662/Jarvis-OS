"""Builds the compiled LangGraph state machine (Milestone 5-Agents, extended
Milestone 10 -- AI Orchestrator).

``intent_classifier -> context_engine -> planner -> tool_selector ->
permission_validator -> (tool_executor -> critic -> tool_selector)* ->
responder -> END`` -- the Milestone 5-Agents sequence
(``planner -> tool_selector -> tool_executor -> critic -> responder``,
looping from ``critic`` back to ``tool_selector``) with Milestone 10's
Intent Engine and Context Engine prepended, and Permission Validation
(interim -- see ``agents/permission.py``) inserted between tool selection
and execution as the one enforcement point every proposed tool call now
passes through, whether it came from the single-tool or the
``tool_parallel`` (Milestone 10 AC1) path.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langgraph.graph import END, START, StateGraph

from jarvis.agents.nodes.context_engine import make_context_engine_node
from jarvis.agents.nodes.critic import make_critic_node
from jarvis.agents.nodes.intent_classifier import make_intent_classifier_node
from jarvis.agents.nodes.permission_validator import make_permission_validator_node
from jarvis.agents.nodes.planner import make_planner_node
from jarvis.agents.nodes.responder import make_responder_node
from jarvis.agents.nodes.tool_executor import make_tool_executor_node
from jarvis.agents.nodes.tool_selector import make_tool_selector_node
from jarvis.agents.permission import AgentPermissionGate
from jarvis.agents.state import AgentState

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

    from jarvis.core.interfaces.llm_provider import ILLMProvider
    from jarvis.features.automation.permission import ConfirmationCallback
    from jarvis.services.memory_service import MemoryService


def _route_after_selection(state: AgentState) -> str:
    if state.get("step", 0) >= state.get("max_steps", 25):
        return "final"
    action = state.get("next_action")
    if action in ("tool", "tool_parallel"):
        return action
    return "final"


def _route_after_permission(state: AgentState) -> str:
    if state.get("next_action") == "tool_parallel":
        return "run" if state.get("pending_tool_calls") else "skip"
    return "skip" if state.get("permission_denied") else "run"


def _route_after_critic(state: AgentState) -> str:
    if state.get("step", 0) >= state.get("max_steps", 25):
        return "done"
    return "continue" if state.get("needs_more_work") else "done"


def build_agent_graph(
    *,
    llm: ILLMProvider,
    tools: list[BaseTool],
    checkpointer: Any,
    memory: MemoryService | None = None,
    permission_gate: AgentPermissionGate | None = None,
    confirm: ConfirmationCallback | None = None,
    max_parallel_steps: int = 4,
    include_responder: bool = True,
) -> Any:
    """Compile the graph. ``checkpointer`` is any LangGraph
    ``BaseCheckpointSaver`` (see :mod:`jarvis.agents.checkpointer`).

    ``include_responder=False`` compiles a variant that routes the "final"/
    "done" branches straight to ``END`` instead of through ``responder`` --
    used by :meth:`~jarvis.agents.orchestrator.AgentOrchestrator.stream` so
    it can call ``llm.stream()`` directly on the composed prompt for real
    token-level output (Milestone 10 AC2) instead of running responder's
    own blocking completion and re-chunking the result.
    """
    tools_by_name = {t.name: t for t in tools}
    gate = permission_gate or AgentPermissionGate()

    # `StateGraph`'s `.add_node()` overloads are typed against
    # `TypedDictLikeV1/V2 | DataclassLike | BaseModel` node-input bounds
    # that don't line up with a plain `Callable[[AgentState],
    # Awaitable[dict[Any, Any]]]` node factory under mypy --strict, even
    # though this is the standard, documented way to add an async node
    # function to a LangGraph graph (works correctly at runtime). The
    # `type: ignore` comments below are scoped to that one, known
    # stub-resolution limitation, not a suppression of real errors.
    graph = StateGraph(AgentState)
    graph.add_node("intent_classifier", make_intent_classifier_node(llm))  # type: ignore[call-overload]
    graph.add_node("context_engine", make_context_engine_node(memory))  # type: ignore[call-overload]
    graph.add_node("planner", make_planner_node(llm, tools))  # type: ignore[call-overload]
    graph.add_node("tool_selector", make_tool_selector_node(llm, tools))  # type: ignore[call-overload]
    graph.add_node(
        "permission_validator",
        make_permission_validator_node(gate, confirm=confirm),
    )  # type: ignore[call-overload]
    graph.add_node(
        "tool_executor",
        make_tool_executor_node(tools_by_name, max_parallel_steps=max_parallel_steps),
    )  # type: ignore[call-overload]
    graph.add_node("critic", make_critic_node(llm))  # type: ignore[call-overload]

    final_target = "responder" if include_responder else END
    if include_responder:
        graph.add_node("responder", make_responder_node(llm))  # type: ignore[call-overload]

    graph.add_edge(START, "intent_classifier")
    graph.add_edge("intent_classifier", "context_engine")
    graph.add_edge("context_engine", "planner")
    graph.add_edge("planner", "tool_selector")
    graph.add_conditional_edges(
        "tool_selector",
        _route_after_selection,
        {
            "tool": "permission_validator",
            "tool_parallel": "permission_validator",
            "final": final_target,
        },
    )
    graph.add_conditional_edges(
        "permission_validator",
        _route_after_permission,
        {"run": "tool_executor", "skip": "critic"},
    )
    graph.add_edge("tool_executor", "critic")
    graph.add_conditional_edges(
        "critic",
        _route_after_critic,
        {"continue": "tool_selector", "done": final_target},
    )
    if include_responder:
        graph.add_edge("responder", END)

    return graph.compile(checkpointer=checkpointer)
