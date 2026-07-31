"""Tiny async-friendly in-process event bus.

The bus deliberately has *no* persistence, *no* remote transport and *no*
retries — its only job is to decouple the components that live inside the
same Python process (UI ↔ services ↔ agents).

Usage::

    from jarvis.core.events import EventBus, Event

    @dataclass(frozen=True, slots=True)
    class HelloEvent(Event):
        who: str = "world"

    bus = EventBus()

    async def on_hello(evt: HelloEvent) -> None:
        print("Hello,", evt.who)

    bus.subscribe(HelloEvent, on_hello)
    await bus.publish(HelloEvent(who="Jarvis"))
"""

from __future__ import annotations

import asyncio
import inspect
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import TypeVar

from jarvis.core.events.events import Event
from jarvis.core.logging.logger import get_logger
from jarvis.utils.async_utils import fire_and_forget

_T = TypeVar("_T", bound=Event)
Handler = Callable[[_T], "Awaitable[None] | None"]

_logger = get_logger("jarvis.core.events")


class EventBus:
    """Thread-unsafe, asyncio-aware event bus."""

    def __init__(self) -> None:
        self._subs: dict[type[Event], list[Handler]] = defaultdict(list)

    # ------------------------------------------------------------------
    # Subscription
    # ------------------------------------------------------------------
    def subscribe(self, event_type: type[_T], handler: Handler[_T]) -> Callable[[], None]:
        """Register a handler and return an ``unsubscribe`` callable."""
        self._subs[event_type].append(handler)

        def _unsubscribe() -> None:
            try:
                self._subs[event_type].remove(handler)
            except ValueError:  # already removed
                pass

        return _unsubscribe

    # ------------------------------------------------------------------
    # Publication
    # ------------------------------------------------------------------
    async def publish(self, event: Event) -> None:
        """Deliver *event* to every subscriber, awaiting async handlers."""
        for et in type(event).__mro__:
            if et is object:
                break
            for handler in list(self._subs.get(et, ())):
                try:
                    result = handler(event)
                    if inspect.isawaitable(result):
                        await result
                except Exception:
                    _logger.exception(
                        "Event handler {} raised while processing {}.",
                        getattr(handler, "__qualname__", handler),
                        type(event).__name__,
                    )

    def publish_nowait(self, event: Event) -> None:
        """Fire-and-forget variant. Schedules :meth:`publish` on the running loop."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(self.publish(event))
            return
        fire_and_forget(self.publish(event))
