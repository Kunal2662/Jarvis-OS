"""Builds the compiled LangGraph state machine (Milestone 5-Agents).

``planner -> tool_selector -> (tool_executor -> critic -> tool_selector)* ->
responder -> END`` — the exact node sequence named in
``docs/MASTER_ROADMAP.md``'s Milestone 5-Agents spec, with a loop back
from ``critic`` to ``tool_selector`` so a multi-step task ("search web ->
summarise -> save memory") can keep calling tools until the critic is
satisfied or ``max_steps`` is hit.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langgraph.graph import END, START, StateGraph

from jarvis.agents.nodes.critic import make_critic_node
from jarvis.agents.nodes.planner import make_planner_node
from jarvis.agents.nodes.responder import make_responder_node
from jarvis.agents.nodes.tool_executor import make_tool_executor_node
from jarvis.agents.nodes.tool_selector import make_tool_selector_node
from jarvis.agents.state import AgentState

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

    from jarvis.core.interfaces.llm_provider import ILLMProvider


def _route_after_selection(state: AgentState) -> str:
    if state.get("step", 0) >= state.get("max_steps", 25):
        return "final"
    return "tool" if state.get("next_action") == "tool" else "final"


def _route_after_critic(state: AgentState) -> str:
    if state.get("step", 0) >= state.get("max_steps", 25):
        return "done"
    return "continue" if state.get("needs_more_work") else "done"


def build_agent_graph(*, llm: ILLMProvider, tools: list[BaseTool], checkpointer: Any) -> Any:
    """Compile the graph. ``checkpointer`` is any LangGraph
    ``BaseCheckpointSaver`` (see :mod:`jarvis.agents.checkpointer`)."""
    tools_by_name = {t.name: t for t in tools}

    # `StateGraph`'s `.add_node()` overloads are typed against
    # `TypedDictLikeV1/V2 | DataclassLike | BaseModel` node-input bounds
    # that don't line up with a plain `Callable[[AgentState],
    # Awaitable[dict[Any, Any]]]` node factory under mypy --strict, even
    # though this is the standard, documented way to add an async node
    # function to a LangGraph graph (works correctly at runtime). The
    # `type: ignore` comments below are scoped to that one, known
    # stub-resolution limitation, not a suppression of real errors.
    graph = StateGraph(AgentState)
    graph.add_node("planner", make_planner_node(llm, tools))  # type: ignore[call-overload]
    graph.add_node("tool_selector", make_tool_selector_node(llm, tools))  # type: ignore[call-overload]
    graph.add_node("tool_executor", make_tool_executor_node(tools_by_name))  # type: ignore[call-overload]
    graph.add_node("critic", make_critic_node(llm))  # type: ignore[call-overload]
    graph.add_node("responder", make_responder_node(llm))  # type: ignore[call-overload]

    graph.add_edge(START, "planner")
    graph.add_edge("planner", "tool_selector")
    graph.add_conditional_edges(
        "tool_selector",
        _route_after_selection,
        {"tool": "tool_executor", "final": "responder"},
    )
    graph.add_edge("tool_executor", "critic")
    graph.add_conditional_edges(
        "critic",
        _route_after_critic,
        {"continue": "tool_selector", "done": "responder"},
    )
    graph.add_edge("responder", END)

    return graph.compile(checkpointer=checkpointer)
