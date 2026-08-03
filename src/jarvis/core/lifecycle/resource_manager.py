"""``ResourceManager`` -- CPU/memory budget tracking across everything
the runtime supervises (Milestone 9 Task Group C, Reliability module).

Composes on top of :class:`~jarvis.core.lifecycle.health_monitor.
HealthMonitor` rather than polling ``psutil`` a second time --
subscribes to the existing ``HealthUpdatedEvent`` (published on every
poll tick) instead of running a competing poll loop, avoiding both
duplicate collection and a duplicate loop. The consumer-side
counterpart to M22 Edge AI Platform's future Resource Allocation
module (``MASTER_ROADMAP.md`` §8) -- this milestone tracks and alerts,
it does not throttle or kill anything on a budget breach, matching M9
Reliability's own "observability, not an autonomous scheduler" scope.

GPU/disk budgets are real, typed, registerable today even though
``HealthMonitor`` has no GPU/disk collector yet (`register_collector()`
is that class's own extension point) -- :meth:`register_budget` keeps
this class snapshot-key-agnostic instead of hardcoding field access,
so a future collector's metric gains a budget without editing this
class again.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from jarvis.core.events.events import HealthUpdatedEvent, ResourceBudgetExceededEvent
from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.core.events.event_bus import EventBus

_logger = get_logger("jarvis.core.lifecycle.resource_manager")


@dataclass(frozen=True, slots=True)
class ResourceBudget:
    """*snapshot_key* names the ``HealthMonitor.snapshot()``/
    ``HealthUpdatedEvent.snapshot`` dict key this budget checks (e.g.
    ``"cpu_percent"``, ``"memory_rss_bytes"``)."""

    resource: str
    snapshot_key: str
    limit: float


class ResourceManager:
    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._budgets: dict[str, ResourceBudget] = {}
        self._exceeded: set[str] = set()
        self._unsubscribe: Any = None

    def register_budget(self, resource: str, snapshot_key: str, limit: float) -> None:
        self._budgets[resource] = ResourceBudget(resource, snapshot_key, limit)

    def unregister_budget(self, resource: str) -> None:
        self._budgets.pop(resource, None)
        self._exceeded.discard(resource)

    @property
    def budgets(self) -> tuple[ResourceBudget, ...]:
        return tuple(self._budgets.values())

    def start(self) -> None:
        if self._unsubscribe is not None:
            return
        self._unsubscribe = self._event_bus.subscribe(HealthUpdatedEvent, self._on_health_updated)

    def stop(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

    async def _on_health_updated(self, event: HealthUpdatedEvent) -> None:
        for budget in self._budgets.values():
            used = event.snapshot.get(budget.snapshot_key)
            if not isinstance(used, int | float):
                continue
            within = used <= budget.limit
            if not within and budget.resource not in self._exceeded:
                self._exceeded.add(budget.resource)
                _logger.warning(
                    "Resource budget exceeded: {} = {} > {}.", budget.resource, used, budget.limit
                )
                await self._event_bus.publish(
                    ResourceBudgetExceededEvent(
                        resource=budget.resource, used=float(used), budget=budget.limit
                    )
                )
            elif within and budget.resource in self._exceeded:
                self._exceeded.discard(budget.resource)

    def is_exceeded(self, resource: str) -> bool:
        """On-demand, synchronous read of the last known state for one
        budget -- for diagnostics/tests, doesn't wait for the next
        ``HealthUpdatedEvent`` tick."""
        return resource in self._exceeded
