"""AI Orchestrator API -- Milestone 10.

The REST surface over :class:`~jarvis.agents.orchestrator.AgentOrchestrator`:
``POST /agent/invoke`` (blocking, ``Envelope``-wrapped ``AgentResponse``) and
``POST /agent/stream`` (real token-level Server-Sent Events, Milestone 10
AC2 -- see ``AgentOrchestrator.stream``'s own docstring for what "real"
means here and its one documented, scoped exception).

Same ``Depends(get_current_session)`` Bearer auth as ``routes/plugins.py``
and ``routes/devtools.py`` -- this is a developer/first-party surface, not
a public one, same posture as those two.

``/agent/stream`` is a documented exception to the ``{data, meta}``
envelope rule, the same way ``/api/v1/sessions`` already is (see
``docs/ARCHITECTURE.md`` section 5): an SSE body is a sequence of
``data: <chunk>\\n\\n`` frames, not one JSON object, by the nature of the
transport -- wrapping each frame in an ``Envelope`` would just be
JSON-inside-SSE-inside-HTTP for no benefit.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from jarvis.infrastructure.api.auth import Envelope, envelope, get_current_session

if TYPE_CHECKING:
    from jarvis.agents.orchestrator import AgentOrchestrator

router = APIRouter(tags=["agent"], dependencies=[Depends(get_current_session)])


class AgentInvokeRequest(BaseModel):
    prompt: str
    thread_id: str | None = None


def _orchestrator(request: Request) -> AgentOrchestrator:
    return cast("AgentOrchestrator", request.app.state.container.agent_orchestrator())


@router.post("/agent/invoke", response_model=Envelope[dict[str, Any]])
async def invoke_agent(body: AgentInvokeRequest, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.interfaces.agent import AgentRequest

    orchestrator = _orchestrator(request)
    response = await orchestrator.invoke(AgentRequest(prompt=body.prompt, thread_id=body.thread_id))
    payload = {
        "text": response.text,
        "thread_id": response.thread_id,
        "steps": response.steps,
        "metadata": response.metadata,
    }
    return envelope(payload)


@router.post("/agent/stream")
async def stream_agent(body: AgentInvokeRequest, request: Request) -> StreamingResponse:
    from jarvis.core.interfaces.agent import AgentRequest

    orchestrator = _orchestrator(request)
    agent_request = AgentRequest(prompt=body.prompt, thread_id=body.thread_id)

    async def _event_source() -> AsyncIterator[str]:
        async for token in orchestrator.stream(agent_request):
            escaped = token.replace("\r", "").replace("\n", "\\n")
            yield f"data: {escaped}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(_event_source(), media_type="text/event-stream")
