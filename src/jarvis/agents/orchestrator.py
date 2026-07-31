"""Root LangGraph orchestrator (Milestone 5-Agents).

Wires together, in order: tool registry (``agents/tools``) -> checkpointer
(``agents/checkpointer``) -> compiled state graph (``agents/graph``,
nodes in ``agents/nodes``). Every other layer of the app (Developer
Mode's Agent Trace panel today; voice/chat/command-palette in later
milestones) only ever talks to :class:`AgentOrchestrator` through the
:class:`~jarvis.core.interfaces.agent.IAgentOrchestrator` port — it never
touches the graph, nodes or tools directly, mirroring how
``AutomationService`` fronts the automation engine's internal layers.

Streaming note: the compiled graph is streamed at the node/step level
(``astream(..., stream_mode="values")``) so each LangGraph node
transition can be published as an :class:`AgentStepEvent` for the trace
panel — this is the "planner narration" half of the roadmap's "streaming
agent tokens end-to-end" goal. The final answer is then re-emitted
word-by-word for a typewriter UX consistent with
:meth:`~jarvis.services.chat_service.ChatService.stream`. True
token-level streaming *from inside* the responder node's own LLM call is
intentionally deferred (see the milestone delivery doc's Remaining Work)
rather than building it against an unverified LangGraph message-streaming
API surface.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from jarvis.agents.checkpointer import AgentCheckpointer
from jarvis.agents.graph import build_agent_graph
from jarvis.agents.state import AgentState
from jarvis.agents.tools import build_tool_registry
from jarvis.core.config.constants import MAX_AGENT_STEPS_HARD_CAP
from jarvis.core.exceptions import AgentError, AgentTimeoutError
from jarvis.core.interfaces.agent import (
    AgentRequest,
    AgentResponse,
    IAgentOrchestrator,
)
from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

    from jarvis.core.config.settings import Settings
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.interfaces.llm_provider import ILLMProvider
    from jarvis.services.automation_service import AutomationService
    from jarvis.services.browser_service import BrowserService
    from jarvis.services.chat_service import ChatService
    from jarvis.services.memory_service import MemoryService
    from jarvis.services.system_service import SystemService
    from jarvis.services.vision_service import VisionService
    from jarvis.services.voice_service import VoiceService

_logger = get_logger("jarvis.agents.orchestrator")


class AgentOrchestrator(IAgentOrchestrator):
    def __init__(
        self,
        settings: Settings,
        llm: ILLMProvider,
        memory: MemoryService,
        automation: AutomationService,
        browser: BrowserService,
        *,
        chat: ChatService | None = None,
        voice: VoiceService | None = None,
        system: SystemService | None = None,
        vision: VisionService | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self._settings = settings
        self._llm = llm
        self._memory = memory
        self._automation = automation
        self._browser = browser
        self._chat = chat
        self._voice = voice
        self._system = system
        self._vision = vision
        self._event_bus = event_bus

        self._checkpointer = AgentCheckpointer(settings)
        self._tools: list[BaseTool] = []
        self._graph = None
        self._started = False
        self._start_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def start(self) -> None:
        async with self._start_lock:
            if self._started:
                return
            self._tools = build_tool_registry(
                memory=self._memory,
                automation=self._automation,
                browser=self._browser,
                system=self._system,
                voice=self._voice,
                chat=self._chat,
                vision=self._vision,
            )
            saver = await self._checkpointer.open()
            self._graph = build_agent_graph(llm=self._llm, tools=self._tools, checkpointer=saver)
            self._started = True
            _logger.info(
                "AgentOrchestrator started with {} tool(s): {}",
                len(self._tools),
                [t.name for t in self._tools],
            )

    async def stop(self) -> None:
        if not self._started:
            return
        await self._checkpointer.close()
        self._graph = None
        self._started = False
        _logger.info("AgentOrchestrator stopped.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def invoke(self, request: AgentRequest) -> AgentResponse:
        await self.start()
        thread_id = request.thread_id or uuid4().hex
        state = self._initial_state(request, thread_id)
        config = {"configurable": {"thread_id": thread_id}}

        assert self._graph is not None  # start() guarantees this
        try:
            result = await asyncio.wait_for(
                self._graph.ainvoke(state, config=config),
                timeout=self._settings.agent.timeout_seconds,
            )
        except TimeoutError as err:
            raise AgentTimeoutError(
                f"Agent exceeded {self._settings.agent.timeout_seconds}s timeout."
            ) from err
        except AgentError:
            raise
        except Exception as err:
            _logger.exception("Agent invoke() failed.")
            raise AgentError(str(err)) from err

        await self._publish_step_event(thread_id, result)
        return AgentResponse(
            text=result.get("final_response", ""),
            thread_id=thread_id,
            steps=result.get("step", 0),
            metadata={
                "tool_calls": result.get("tool_calls", []),
                "plan": result.get("plan", ""),
                "critique": result.get("critique", ""),
            },
        )

    async def stream(self, request: AgentRequest) -> AsyncIterator[str]:
        await self.start()
        thread_id = request.thread_id or uuid4().hex
        state = self._initial_state(request, thread_id)
        config = {"configurable": {"thread_id": thread_id}}

        assert self._graph is not None
        final_state: dict[str, Any] = dict(state)
        try:
            async for step_state in self._graph.astream(state, config=config, stream_mode="values"):
                final_state = step_state
                await self._publish_step_event(thread_id, final_state)
        except Exception as err:
            _logger.exception("Agent stream() failed.")
            raise AgentError(str(err)) from err

        for token in _chunk_for_streaming(final_state.get("final_response", "")):
            yield token

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _initial_state(self, request: AgentRequest, thread_id: str) -> AgentState:
        configured_max = self._settings.agent.max_steps
        max_steps = max(1, min(configured_max, MAX_AGENT_STEPS_HARD_CAP))
        return AgentState(
            prompt=request.prompt,
            thread_id=thread_id,
            max_steps=max_steps,
            plan="",
            next_action="",
            tool_name="",
            tool_args={},
            tool_calls=[],
            step=0,
            critique="",
            needs_more_work=False,
            final_response="",
            error=None,
            last_node="",
        )

    async def _publish_step_event(self, thread_id: str, state: dict[str, Any]) -> None:
        if self._event_bus is None:
            return
        from jarvis.core.events.events import AgentStepEvent

        detail = state.get("critique") or state.get("plan") or ""
        await self._event_bus.publish(
            AgentStepEvent(
                thread_id=thread_id,
                step=state.get("step", 0),
                node=state.get("last_node", ""),
                status="error" if state.get("error") else "ok",
                detail=str(detail)[:300],
            )
        )


def _chunk_for_streaming(text: str, *, chunk_size: int = 4) -> list[str]:
    """Split *text* into small whitespace-preserving chunks for a
    typewriter-style UX, mirroring how ``ChatService.stream`` yields
    tokens incrementally even though this text was already fully
    composed by the responder node."""
    if not text:
        return []
    words = text.split(" ")
    chunks: list[str] = []
    for i in range(0, len(words), chunk_size):
        piece = " ".join(words[i : i + chunk_size])
        chunks.append(piece + (" " if i + chunk_size < len(words) else ""))
    return chunks
