"""API Inspector -- Milestone 9 Task Group E.

Request/response inspection for *this* application's own `/api/v1/*`
runtime surface -- distinct from M11's future Workspace Developer
Tools, which inspect *external* API calls a workspace makes outward.
A bounded, in-memory record of recent request metadata (method, path,
status, duration) -- never bodies or headers (a request/response body
can contain secrets -- API keys, session tokens -- this dev tool must
never persist even transiently; ``docs/ARCHITECTURE.md`` section 17's
own secrets-handling standard).
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from starlette.requests import Request
    from starlette.responses import Response


@dataclass(frozen=True, slots=True)
class ApiCallRecord:
    method: str
    path: str
    status_code: int
    duration_ms: float
    at: float


DEFAULT_MAX_RECORDS = 500


class ApiInspector:
    def __init__(self, *, max_records: int = DEFAULT_MAX_RECORDS) -> None:
        self._records: deque[ApiCallRecord] = deque(maxlen=max_records)

    def record(self, *, method: str, path: str, status_code: int, duration_ms: float) -> None:
        self._records.append(
            ApiCallRecord(
                method=method,
                path=path,
                status_code=status_code,
                duration_ms=duration_ms,
                at=time.time(),
            )
        )

    def recent(
        self, *, limit: int = 100, path_contains: str | None = None
    ) -> tuple[ApiCallRecord, ...]:
        results: list[ApiCallRecord] = []
        for record in reversed(self._records):
            if path_contains is not None and path_contains not in record.path:
                continue
            results.append(record)
            if len(results) >= limit:
                break
        return tuple(results)

    def clear(self) -> None:
        self._records.clear()

    def __len__(self) -> int:
        return len(self._records)


async def api_inspector_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
    *,
    inspector: ApiInspector,
) -> Response:
    """A FastAPI ``@app.middleware("http")``-compatible callable, bound
    to a real *inspector* instance via ``functools.partial`` at mount
    time (``infrastructure/api/fastapi_server.py``) -- kept here,
    beside :class:`ApiInspector` itself, rather than in the FastAPI
    layer, so the recording logic has exactly one owner."""
    started = time.monotonic()
    response = await call_next(request)
    duration_ms = (time.monotonic() - started) * 1000
    inspector.record(
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=duration_ms,
    )
    return response
