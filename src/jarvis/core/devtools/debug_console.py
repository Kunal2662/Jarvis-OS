"""Debug Console + Live Logs -- Milestone 9 Task Group E.

A bounded, filterable capture buffer over the runtime's own real
loguru log stream. Attaches as one more loguru sink -- the exact same
mechanism ``core/logging/logger.py``'s own JSON/console/file sinks
already use -- but entirely self-contained here rather than modifying
that shared bootstrap module, so this dev-only capture adds zero
coupling to it.

**Debug Console and Live Logs are one mechanism, not two.** "Debug
Console" (a filterable query over recent history) reads
:meth:`DebugConsole.entries`; "Live Logs" (real-time streaming) is the
same capture, additionally publishing one :class:`~jarvis.core.events.
events.DebugLogCapturedEvent` per line for the Runtime WebSocket API to
relay -- the same "capture once, serve two ways" shape
``HealthMonitor`` already establishes for its own poll-tick snapshot.

**Honest cost note.** The sink runs with ``enqueue=True`` (loguru's own
background writer thread, not the app's main event loop), so each
captured line's ``EventBus.publish_nowait`` call takes the "no running
loop in this thread" fallback path (a short-lived ``asyncio.run()`` per
line) rather than scheduling onto an already-running loop. Acceptable
for a developer-only, opt-in tool -- not attached in a default
production run (``start()`` is never called unless Developer Mode
explicitly enables it) -- but a real per-line cost, not free.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from loguru import logger as loguru_logger

from jarvis.core.events.events import DebugLogCapturedEvent

if TYPE_CHECKING:
    from jarvis.core.events.event_bus import EventBus

DEFAULT_MAX_ENTRIES = 2000
DEFAULT_LEVEL = "INFO"


@dataclass(frozen=True, slots=True)
class DebugLogEntry:
    at: datetime
    level: str
    logger: str
    message: str
    module: str
    function: str
    line: int


class DebugConsole:
    def __init__(self, event_bus: EventBus, *, max_entries: int = DEFAULT_MAX_ENTRIES) -> None:
        self._event_bus = event_bus
        self._entries: deque[DebugLogEntry] = deque(maxlen=max_entries)
        self._sink_id: int | None = None

    def start(self, *, level: str = DEFAULT_LEVEL) -> None:
        """Attaches this console as a real loguru sink. Idempotent --
        a second call is a no-op rather than stacking a duplicate
        sink."""
        if self._sink_id is not None:
            return
        self._sink_id = loguru_logger.add(self._sink, level=level, enqueue=True)

    def stop(self) -> None:
        if self._sink_id is None:
            return
        loguru_logger.remove(self._sink_id)
        self._sink_id = None

    def _sink(self, message: Any) -> None:
        record = message.record
        entry = DebugLogEntry(
            at=record["time"],
            level=record["level"].name,
            logger=record["extra"].get("logger") or record["name"] or "",
            message=record["message"],
            module=record["module"],
            function=record["function"],
            line=record["line"],
        )
        self._entries.append(entry)
        self._event_bus.publish_nowait(
            DebugLogCapturedEvent(
                level=entry.level,
                logger=entry.logger,
                message=entry.message,
                at=entry.at.isoformat(),
            )
        )

    def entries(
        self,
        *,
        level: str | None = None,
        logger: str | None = None,
        contains: str | None = None,
        limit: int = 200,
    ) -> tuple[DebugLogEntry, ...]:
        """Most-recent-first, filtered. Never raises on an empty
        buffer or an over-large *limit* -- just returns what's there."""
        results: list[DebugLogEntry] = []
        for entry in reversed(self._entries):
            if level is not None and entry.level != level.upper():
                continue
            if logger is not None and logger not in entry.logger:
                continue
            if contains is not None and contains.lower() not in entry.message.lower():
                continue
            results.append(entry)
            if len(results) >= limit:
                break
        return tuple(results)

    def clear(self) -> None:
        self._entries.clear()

    @property
    def is_running(self) -> bool:
        return self._sink_id is not None

    def __len__(self) -> int:
        return len(self._entries)
