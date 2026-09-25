"""Event Viewer -- Milestone 12 Developer Tools.

A bounded, filterable capture buffer over the real
:class:`~jarvis.core.events.event_bus.EventBus`'s own
:class:`~jarvis.core.events.events.DeviceCommandExecutedEvent` stream --
structurally parallel to :class:`~jarvis.core.devtools.debug_console.
DebugConsole` (``start``/``stop``/``entries``/``clear``/``is_running``/
``__len__``), but simpler: `EventBus.subscribe` calls its handler
synchronously on the publishing coroutine's own task, so there is no
loguru sink, no background writer thread, and none of `DebugConsole`'s
own documented cross-thread ``publish_nowait`` cost to pay.

Closes the "no device-command event exists on the EventBus" gap Device
Diagnostics'/Device Logs' own Logic Contracts both named explicitly.
Deliberately not relayed over WebSocket -- see ``core/lifecycle/
runtime_ws_hub.py``'s ``UNPUBLISHED_EVENT_TYPES`` -- this is the
REST-pollable-history half only, matching every M12 Developer Tools
slice's own backend-only scope.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.events.events import DeviceCommandExecutedEvent

DEFAULT_MAX_ENTRIES = 200


@dataclass(frozen=True, slots=True)
class DeviceEventEntry:
    at: datetime
    device_id: str
    command: str
    success: bool
    detail: str


class DeviceEventLog:
    def __init__(self, event_bus: EventBus, *, max_entries: int = DEFAULT_MAX_ENTRIES) -> None:
        self._event_bus = event_bus
        self._entries: deque[DeviceEventEntry] = deque(maxlen=max_entries)
        self._unsubscribe: Callable[[], None] | None = None

    def start(self) -> None:
        """Idempotent -- a second call is a no-op rather than stacking a
        duplicate subscription."""
        if self._unsubscribe is not None:
            return
        from jarvis.core.events.events import DeviceCommandExecutedEvent

        self._unsubscribe = self._event_bus.subscribe(DeviceCommandExecutedEvent, self._on_event)

    def stop(self) -> None:
        if self._unsubscribe is None:
            return
        self._unsubscribe()
        self._unsubscribe = None

    def _on_event(self, event: DeviceCommandExecutedEvent) -> None:
        self._entries.append(
            DeviceEventEntry(
                at=event.occurred_at,
                device_id=event.device_id,
                command=event.command,
                success=event.success,
                detail=event.detail,
            )
        )

    def entries(
        self, *, device_id: str | None = None, limit: int = 200
    ) -> tuple[DeviceEventEntry, ...]:
        """Most-recent-first, filtered. Never raises on an empty buffer
        or an over-large *limit* -- just returns what's there."""
        results: list[DeviceEventEntry] = []
        for entry in reversed(self._entries):
            if device_id is not None and entry.device_id != device_id:
                continue
            results.append(entry)
            if len(results) >= limit:
                break
        return tuple(results)

    def clear(self) -> None:
        self._entries.clear()

    @property
    def is_running(self) -> bool:
        return self._unsubscribe is not None

    def __len__(self) -> int:
        return len(self._entries)
