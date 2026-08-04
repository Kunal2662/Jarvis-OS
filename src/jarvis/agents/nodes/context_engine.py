"""Context Engine (Milestone 10) -- assembles the context window from
available memory before planning starts, replacing the pre-M10 gap where no
node ever queried memory ahead of planning.

Scoped deliberately: M10's own spec describes Context Engine assembling
context from "M10A's knowledge substrate and M3 Memory" -- M10A (Universal
Search & Knowledge Platform) has not shipped (``docs/MASTER_ROADMAP.md``,
status Planned), so there is no knowledge graph to query yet. This node
assembles context from M3 Memory only, which is real today; the
knowledge-graph half of Context Engine is deferred pending M10A rather than
silently left unbuilt -- see the Milestone 10 completion report.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.agents.state import AgentState
    from jarvis.services.memory_service import MemoryService

_logger = get_logger("jarvis.agents.nodes.context_engine")
_MAX_MEMORIES = 5


def make_context_engine_node(
    memory: MemoryService | None,
) -> Callable[[AgentState], Awaitable[dict[str, Any]]]:
    async def context_engine_node(state: AgentState) -> dict[str, Any]:
        if memory is None:
            return {"context": "", "last_node": "context_engine"}
        try:
            records = await memory.recall(state["prompt"], top_k=_MAX_MEMORIES)
        except Exception as err:  # memory lookup must never crash the graph
            _logger.warning("Context engine memory recall failed: {}", err)
            return {"context": "", "last_node": "context_engine"}

        context = "\n".join(f"- {r.content}" for r in records)
        return {"context": context, "last_node": "context_engine"}

    return context_engine_node
