"""Root LangGraph orchestrator (Milestone 5-Agents; extended Milestone 10 --
AI Orchestrator).

Wires together, in order: tool registry (``agents/tools``) -> checkpointer
(``agents/checkpointer``) -> compiled state graph (``agents/graph``,
nodes in ``agents/nodes``). Every other layer of the app (Developer
Mode's Agent Trace panel; the ``/api/v1/agent`` REST route, Milestone 10)
only ever talks to :class:`AgentOrchestrator` through the
:class:`~jarvis.core.interfaces.agent.IAgentOrchestrator` port — it never
touches the graph, nodes or tools directly, mirroring how
``AutomationService`` fronts the automation engine's internal layers.

Streaming note (Milestone 10 AC2): :meth:`stream` now yields real,
measurable token-level output from the LLM provider's own ``stream()``
call for the dominant path (an answer composed from tool results), instead
of word-chunking an already-composed string. It does this by compiling a
second, responder-less variant of the graph (``build_agent_graph(...,
include_responder=False)``) that runs the identical
intent/context/plan/tool-select/permission/execute/critique pipeline but
routes straight to ``END`` instead of through ``responder`` — then, once
that pipeline settles, calls ``llm.stream()`` directly on the same prompt
``responder_node`` would have used (:func:`~jarvis.agents.nodes.responder.
build_final_response_prompt`, shared so the two paths can't drift). The one
remaining non-token-real path is ``tool_selector``'s "final" shortcut (no
tool needed -- the answer is embedded in a JSON decision object, which
can't be cleanly token-streamed without restructuring tool selection
itself); that path still replays its already-composed text in the pre-M10
chunked style, a scoped, documented limitation rather than a hidden gap.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from jarvis.agents.checkpointer import AgentCheckpointer
from jarvis.agents.graph import build_agent_graph
from jarvis.agents.nodes.responder import build_final_response_prompt
from jarvis.agents.permission import AgentPermissionGate
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
from jarvis.core.types import ChatMessage

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

    from jarvis.core.config.settings import Settings
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.interfaces.llm_provider import ILLMProvider
    from jarvis.features.automation.permission import ConfirmationCallback
    from jarvis.services.automation_service import AutomationService
    from jarvis.services.browser_service import BrowserService
    from jarvis.services.chat_service import ChatService
    from jarvis.services.integration_service import IntegrationService
    from jarvis.services.intelligence_service import IntelligenceService
    from jarvis.services.knowledge_service import KnowledgeService
    from jarvis.services.memory_service import MemoryService
    from jarvis.services.system_service import SystemService
    from jarvis.services.vision_service import VisionService
    from jarvis.services.voice_service import VoiceService
    from jarvis.services.workspace_ai_service import WorkspaceAssistantService

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
        knowledge: KnowledgeService | None = None,
        intelligence: IntelligenceService | None = None,
        workspace_assistant: WorkspaceAssistantService | None = None,
        integrations: IntegrationService | None = None,
        event_bus: EventBus | None = None,
        confirm: ConfirmationCallback | None = None,
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
        self._knowledge = knowledge
        self._intelligence = intelligence
        # Milestone 11 Task Group D: the workspace domain reaches the
        # agent as tools, not as a new graph node. The graph already
        # assembles context (`context_engine`) and already selects tools;
        # a workspace-shaped node would be a second context assembler
        # that only some prompts benefit from, and it would need a
        # workspace id the request has no way to carry today.
        self._workspace_assistant = workspace_assistant
        # Milestone 11 Task Group E: external vendors reach the agent
        # as four discovery-and-invoke tools, on the same registry.
        self._integrations = integrations
        self._event_bus = event_bus
        # Milestone 10 AC3 (interim Permission Validation): the confirmation
        # channel forwarded to every proposed tool call's AgentPermissionGate
        # check. None (the default) means "no interactive surface available"
        # -- see AgentPermissionGate's own auto-deny-when-unconfirmable
        # default, the same safe-by-default posture automation's own
        # PermissionGate already uses.
        self._confirm = confirm

        self._checkpointer = AgentCheckpointer(settings)
        self._tools: list[BaseTool] = []
        self._graph = None
        # Milestone 10 AC2: a second, responder-less compiled graph used
        # only by stream() for real token-level output -- see module
        # docstring.
        self._stream_graph = None
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
                knowledge=self._knowledge,
                intelligence=self._intelligence,
                workspace_assistant=self._workspace_assistant,
                integrations=self._integrations,
            )
            saver = await self._checkpointer.open()
            permission_gate = AgentPermissionGate(
                confirm_required_tools=self._settings.agent.confirm_required_tools,
            )
            graph_kwargs: dict[str, Any] = {
                "llm": self._llm,
                "tools": self._tools,
                "memory": self._memory,
                "knowledge": self._knowledge,
                "permission_gate": permission_gate,
                "confirm": self._confirm,
                "max_parallel_steps": self._settings.agent.max_parallel_steps,
            }
            self._graph = build_agent_graph(checkpointer=saver, **graph_kwargs)
            self._stream_graph = build_agent_graph(
                checkpointer=saver, include_responder=False, **graph_kwargs
            )
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
        self._stream_graph = None
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

        assert self._stream_graph is not None  # start() guarantees this
        final_state: dict[str, Any] = dict(state)
        try:
            async for step_state in self._stream_graph.astream(
                state, config=config, stream_mode="values"
            ):
                final_state = step_state
                await self._publish_step_event(thread_id, final_state)
        except Exception as err:
            _logger.exception("Agent stream() failed.")
            raise AgentError(str(err)) from err

        if final_state.get("final_response"):
            # tool_selector's "final" shortcut already composed the answer
            # synchronously, embedded in a JSON decision object -- it can't
            # be cleanly token-streamed without restructuring tool
            # selection itself (see module docstring). Replay it in the
            # pre-M10 chunked style rather than claim a token-real stream
            # for a path that isn't one.
            for token in _chunk_for_streaming(final_state.get("final_response", "")):
                yield token
            return

        prompt = build_final_response_prompt(final_state)
        accumulated: list[str] = []
        try:
            async for token in self._llm.stream([ChatMessage(role="user", content=prompt)]):
                accumulated.append(token)
                yield token
        except Exception as err:
            _logger.exception("Agent stream() real-token generation failed.")
            raise AgentError(str(err)) from err

        final_state["final_response"] = "".join(accumulated)
        final_state["last_node"] = "responder"
        final_state["response_mode"] = "composed"
        await self._publish_step_event(thread_id, final_state)

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
            intent="",
            intent_confidence=0.0,
            context="",
            plan="",
            next_action="",
            tool_name="",
            tool_args={},
            pending_tool_calls=[],
            permission_denied=False,
            tool_calls=[],
            step=0,
            critique="",
            needs_more_work=False,
            final_response="",
            response_mode="",
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
