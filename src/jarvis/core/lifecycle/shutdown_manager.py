"""``ShutdownManager`` -- owns the application's shutdown sequence
(Milestone 5.5, reliability).

Before this existed, every resource's cleanup (voice, browser,
hotkeys, database, ...) was hand-sequenced directly inside
``MainWindow._graceful_quit()``. That worked, but doesn't scale: every
future subsystem (an IoT/smart-home bridge, a plugin loader, the agent
orchestrator, a local web server, the automation engine, ...) would
mean editing ``MainWindow`` again to slot its cleanup into the right
place in one growing method.

``ShutdownManager`` inverts that: any resource -- UI or not, built
today or added in a future milestone -- registers its own cleanup
callback with a priority once, wherever that resource is constructed
(typically in the DI container's wiring or the owning service's
``__init__``). Application exit just calls :meth:`shutdown`, which
runs every registered callback in deterministic priority order.

No Qt/PySide6 dependency -- this lives in ``core`` so any layer
(``services``, ``features``, ``infrastructure``) can register a hook
without reaching "up" into ``ui`` (see ``docs/ARCHITECTURE.md``).

Design notes
------------
* **Priority = execution order, lower runs first.** Ties are broken by
  registration order (Python's ``sorted`` is stable) -- documented and
  relied on by tests, not an implementation accident.
* **Every callback is independently fault-tolerant.** One resource
  failing to clean up must never block the others or prevent the
  others from running. Exceptions are caught, logged, and recorded in
  the returned report -- never re-raised.
* **Callbacks are async.** Every real cleanup method in this codebase
  already is (``voice_service.stop_listening``,
  ``browser_service.shutdown``, ``database.dispose``, ...); this
  doesn't add a sync/async bridge that isn't needed anywhere yet.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from jarvis.core.logging.logger import get_logger

_logger = get_logger("jarvis.core.lifecycle.shutdown_manager")

ShutdownCallback = Callable[[], Awaitable[None]]

# Suggested priority bands -- purely a convention (any int works), kept
# here so call sites don't have to invent their own numbering scheme.
PRIORITY_FIRST = 0  # e.g. "announce shutdown while voice is still fully up"
PRIORITY_EARLY = 10  # subsystems that should wind down before the rest
PRIORITY_NORMAL = 50  # most resources
PRIORITY_LATE = 90  # things other cleanup steps might still want available
PRIORITY_LAST = 100  # e.g. the database -- the most "final" resource


@dataclass(frozen=True, slots=True)
class ShutdownHook:
    name: str
    callback: ShutdownCallback
    priority: int


@dataclass(frozen=True, slots=True)
class ShutdownResult:
    name: str
    succeeded: bool
    duration_ms: float
    error: str = ""


class ShutdownManager:
    def __init__(self) -> None:
        self._hooks: list[ShutdownHook] = []
        self._has_run = False

    # ------------------------------------------------------------------
    def register(
        self, name: str, callback: ShutdownCallback, *, priority: int = PRIORITY_NORMAL
    ) -> None:
        """Register a cleanup callback. Re-registering an existing
        *name* replaces it (keeps this idempotent for services that
        might construct more than once, e.g. in tests)."""
        self.unregister(name)
        self._hooks.append(ShutdownHook(name, callback, priority))
        _logger.debug("Registered shutdown hook {!r} (priority={}).", name, priority)

    def unregister(self, name: str) -> None:
        self._hooks = [h for h in self._hooks if h.name != name]

    def is_registered(self, name: str) -> bool:
        return any(h.name == name for h in self._hooks)

    @property
    def registered_names(self) -> list[str]:
        """Names in the order they will actually run (priority, then
        registration order) -- useful for tests and diagnostics."""
        return [h.name for h in self._ordered_hooks()]

    def _ordered_hooks(self) -> list[ShutdownHook]:
        return sorted(self._hooks, key=lambda h: h.priority)

    # ------------------------------------------------------------------
    async def shutdown(self) -> list[ShutdownResult]:
        """Run every registered hook in priority order. Never raises --
        each hook's failure is caught, logged, and reflected in the
        returned report instead of stopping the sequence."""
        if self._has_run:
            _logger.warning("ShutdownManager.shutdown() called more than once -- ignoring.")
            return []
        self._has_run = True

        results: list[ShutdownResult] = []
        for hook in self._ordered_hooks():
            started = time.monotonic()
            try:
                await hook.callback()
                duration_ms = (time.monotonic() - started) * 1000
                results.append(ShutdownResult(hook.name, True, duration_ms))
                _logger.info("Shutdown hook {!r} completed ({:.0f}ms).", hook.name, duration_ms)
            except Exception as err:
                duration_ms = (time.monotonic() - started) * 1000
                results.append(ShutdownResult(hook.name, False, duration_ms, str(err)))
                _logger.exception(
                    "Shutdown hook {!r} failed after {:.0f}ms.", hook.name, duration_ms
                )

        failed = [r for r in results if not r.succeeded]
        if failed:
            _logger.warning(
                "Shutdown complete with {} failure(s): {}", len(failed), [r.name for r in failed]
            )
        else:
            _logger.info("Shutdown complete: {} hook(s) ran cleanly.", len(results))
        return results
