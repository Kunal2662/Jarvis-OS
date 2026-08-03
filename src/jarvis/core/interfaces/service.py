"""The service lifecycle contract -- `docs/ARCHITECTURE.md` section 8
made real code for the first time under Milestone 9 Task Group B.

`IService` was documented since the Aug 2026 architecture standard but
had no implementation anywhere in `src/` -- every existing service
(`ChatService`, `MemoryService`, ...) exposes only ad-hoc, inconsistent
subsets of it (a couple have `start()`/`stop()`, none have `health()`/
`status()`). This module does not retrofit those existing services --
that's a separate, larger migration outside this task group's scope
(see `MASTER_ROADMAP.md`'s Task Group B changelog addendum, "Future
Work"). `core/lifecycle/service_manager.py` wraps a curated set of
real services in thin adapters implementing this Protocol instead,
composition rather than inheritance, so no existing service file needs
to change to participate in the new registry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class HealthStatus:
    """A cheap, frequent, boolean-ish signal -- "is this service able
    to do its job right now." Never a detailed diagnostic dump; see
    `status()` on `IService` for that."""

    healthy: bool
    detail: str = ""


@dataclass(frozen=True, slots=True)
class ServiceStatus:
    """A detailed, human-readable snapshot -- safe to call on-demand,
    not on a tight poll loop. Backs Developer Platform Tools' Debug
    Console/API Inspector once those exist (M9, not yet built)."""

    name: str
    state: str
    detail: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class IService(Protocol):
    """`docs/ARCHITECTURE.md` section 8, verbatim. A service never
    implements a seventh top-level lifecycle method -- anything else
    it needs to expose is a domain-specific method on top of this
    base six, exactly as `AutomationService.run_command()` and
    `MemoryService.recall()` already do."""

    async def initialize(self) -> None:
        """Construct internal state, resolve DI dependencies. No
        network/disk I/O."""
        ...

    async def start(self) -> None:
        """Begin real work. May raise -- a raised exception moves the
        service to FAILED, it does not crash the runtime."""
        ...

    async def stop(self) -> None:
        """Graceful, idempotent stop."""
        ...

    async def health(self) -> HealthStatus:
        """Cheap (<10ms), frequent check. Polled by the Health
        Monitor."""
        ...

    async def status(self) -> ServiceStatus:
        """Detailed, on-demand snapshot."""
        ...

    async def shutdown(self) -> None:
        """Final resource release beyond what `stop()` already did."""
        ...
