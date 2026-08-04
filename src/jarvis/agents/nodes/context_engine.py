"""Context Engine (Milestone 10, extended Milestone 10A) -- assembles the
context window from available memory and the knowledge graph before
planning starts, replacing the pre-M10 gap where no node ever queried
memory ahead of planning.

M10's own spec describes Context Engine assembling context from "M10A's
knowledge substrate and M3 Memory". M10's initial pass (M10A not shipped
yet at the time) scoped this to M3 Memory only, explicitly documenting the
knowledge-graph half as deferred pending M10A. Milestone 10A closes that
deferral: *when a* :class:`~jarvis.services.knowledge_service.KnowledgeService`
*is supplied*, this node also asks it for entities/relationships related to
the prompt. ``knowledge`` stays optional (default ``None``) so every
pre-M10A call site and test keeps working unchanged.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.agents.state import AgentState
    from jarvis.services.knowledge_service import KnowledgeService
    from jarvis.services.memory_service import MemoryService

_logger = get_logger("jarvis.agents.nodes.context_engine")
_MAX_MEMORIES = 5


def make_context_engine_node(
    memory: MemoryService | None,
    knowledge: KnowledgeService | None = None,
) -> Callable[[AgentState], Awaitable[dict[str, Any]]]:
    async def context_engine_node(state: AgentState) -> dict[str, Any]:
        sections: list[str] = []

        if memory is not None:
            try:
                records = await memory.recall(state["prompt"], top_k=_MAX_MEMORIES)
            except Exception as err:  # memory lookup must never crash the graph
                _logger.warning("Context engine memory recall failed: {}", err)
                records = []
            if records:
                sections.append("\n".join(f"- {r.content}" for r in records))

        if knowledge is not None:
            try:
                detail = await knowledge.get_entity_detail(state["prompt"])
            except Exception as err:  # knowledge lookup must never crash the graph
                _logger.warning("Context engine knowledge lookup failed: {}", err)
                detail = None
            if detail is not None:
                lines = [f"Known entity: {detail.name} ({detail.entity_type})"]
                if detail.description:
                    lines.append(detail.description)
                for rel in detail.relationships:
                    arrow = "->" if rel.direction == "outgoing" else "<-"
                    lines.append(
                        f"  {detail.name} {arrow} {rel.predicate} {arrow} {rel.other_entity}"
                    )
                sections.append("\n".join(lines))

        return {"context": "\n\n".join(sections), "last_node": "context_engine"}

    return context_engine_node
