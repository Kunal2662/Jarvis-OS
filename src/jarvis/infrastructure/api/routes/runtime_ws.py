"""Runtime WebSocket API -- ``/api/v1/ws``, ``docs/ARCHITECTURE.md``
section 6 made real for the first time (Milestone 9 Task Group B).

This router owns only the connection lifecycle (accept, heartbeat,
receive loop, close) -- the relay logic (event-to-envelope mapping,
the replay buffer, the connection set) lives in
:class:`~jarvis.core.lifecycle.runtime_ws_hub.RuntimeWebSocketHub`,
matching the layered relationship every other FastAPI router in this
project already has with its service.

**Authentication.** Section 6 calls for the Bearer session token M14
(Security Platform) will issue -- M14 doesn't exist yet, and building
its token issuance/refresh/expiry here would be implementing a future
milestone, not this one. Today's real, working equivalent: the
``token`` query param is a
:class:`~jarvis.core.lifecycle.session_manager.SessionManager` session
id, minted by ``POST /api/v1/sessions`` (``routes/sessions.py``) --
the ``Depends(get_current_session)`` mechanism section 5/6 references,
resolving through the one real session concept this task group builds
instead of a second, placeholder one. M14 layers real Bearer/JWT
semantics on top of this same contract later without changing it.
"""

from __future__ import annotations

import asyncio
import contextlib
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from jarvis.core.lifecycle.runtime_ws_hub import RuntimeWebSocketHub, now_iso
from jarvis.core.logging.logger import get_logger

_logger = get_logger("jarvis.infrastructure.api.routes.runtime_ws")

router = APIRouter(tags=["runtime"])

HEARTBEAT_INTERVAL_SECONDS = 30.0
CLOSE_UNAUTHORIZED = 4401


async def _heartbeat_loop(websocket: WebSocket) -> None:
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
        await websocket.send_json({"type": "heartbeat", "occurred_at": now_iso()})


@router.websocket("/ws")
async def runtime_ws(websocket: WebSocket) -> None:
    hub: RuntimeWebSocketHub = websocket.app.state.runtime_ws_hub
    token = websocket.query_params.get("token")

    if not await hub.authenticate(token):
        await websocket.close(code=CLOSE_UNAUTHORIZED)
        return

    await websocket.accept()
    hub.connect(websocket)
    heartbeat_task = asyncio.create_task(_heartbeat_loop(websocket))
    try:
        while True:
            message = await websocket.receive_json()
            if message.get("type") == "resume":
                served = await hub.replay(websocket, message.get("last_id", ""))
                if not served:
                    await websocket.send_json(
                        {
                            "type": "resume_failed",
                            "id": uuid4().hex,
                            "occurred_at": now_iso(),
                            "payload": {"reason": "replay_window_expired"},
                        }
                    )
    except WebSocketDisconnect:
        pass
    finally:
        heartbeat_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat_task
        hub.disconnect(websocket)
