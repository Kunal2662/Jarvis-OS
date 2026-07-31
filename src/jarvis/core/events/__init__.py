"""In-process event bus package."""

from __future__ import annotations

from jarvis.core.events.event_bus import EventBus
from jarvis.core.events.events import Event

__all__ = ["Event", "EventBus"]
