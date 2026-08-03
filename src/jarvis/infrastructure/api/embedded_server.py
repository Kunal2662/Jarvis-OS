"""Embeds the FastAPI ASGI app inside the application's own asyncio
event loop (Milestone 9 Task Group B, Runtime Integration) -- so the
desktop app's existing PySide6/qasync loop (``app.py``'s ``_run_gui``)
can serve ``/api/v1/ws`` without a second process or a second event
loop. The console-only entry point (``fastapi_server.run()``) still
uses a blocking ``uvicorn.run()`` directly for the API-only runtime
mode; this class is for the GUI runtime mode -- the one real,
user-facing path today the Runtime WebSocket API needs to actually be
reachable from, not a placeholder relay nothing serves.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from jarvis.core.logging.logger import get_logger
from jarvis.utils.async_utils import fire_and_forget

if TYPE_CHECKING:
    from fastapi import FastAPI

_logger = get_logger("jarvis.infrastructure.api.embedded_server")

_STARTUP_POLL_INTERVAL_SECONDS = 0.02
_STARTUP_POLL_ATTEMPTS = 50  # bounded ~1s wait; a real bind failure surfaces well before this


class EmbeddedApiServer:
    def __init__(self, app: FastAPI, *, host: str, port: int) -> None:
        self._app = app
        self._host = host
        self._port = port
        self._server: Any = None
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Bind and begin serving. Raises if the server fails to start
        (e.g. the port is already in use) -- the caller (a RuntimeManager
        startup hook) is expected to treat that as a best-effort failure,
        not a boot-blocking one."""
        if self._task is not None:
            return
        import uvicorn

        config = uvicorn.Config(
            self._app,
            host=self._host,
            port=self._port,
            log_config=None,
            lifespan="off",
        )
        self._server = uvicorn.Server(config)
        self._task = fire_and_forget(self._server.serve())

        for _ in range(_STARTUP_POLL_ATTEMPTS):
            if self._server.started or self._task.done():
                break
            await asyncio.sleep(_STARTUP_POLL_INTERVAL_SECONDS)

        if self._task.done():
            # Re-raise so a bind failure becomes a real RuntimeManager hook
            # failure (logged + reported), not a silently-dead background task.
            self._task.result()

        _logger.info("Embedded API server listening on {}:{}.", self._host, self._port)

    async def stop(self) -> None:
        if self._server is None or self._task is None:
            return
        self._server.should_exit = True
        await self._task
        self._server = None
        self._task = None
