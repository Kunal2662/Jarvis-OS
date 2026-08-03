"""``RuntimeManager`` -- owns both the application's startup and
shutdown sequences (Milestone 5.5's ``ShutdownManager``, generalized
under Milestone 9's Runtime Core module).

Before ``ShutdownManager`` existed, every resource's cleanup (voice,
browser, hotkeys, database, ...) was hand-sequenced directly inside
``MainWindow._graceful_quit()``. ``ShutdownManager`` fixed that for
shutdown. The same problem existed on the *startup* side and was never
fixed: ``app.py``'s ``run()`` still hand-sequences a growing list of
best-effort startup steps (memory-policy enforcement, Whisper preload,
...), each wrapped in its own ad-hoc ``try/except`` -- the exact
"doesn't scale" shape ``ShutdownManager``'s own history already proved
out. ``RuntimeManager`` closes that gap by generalizing the same
priority-ordered, fault-isolated hook design to both directions
instead of introducing a second, parallel mechanism for startup.

Any resource -- UI or not, built today or added in a future milestone
-- registers its own startup and/or shutdown callback with a priority
once, wherever that resource is constructed (typically in the DI
container's wiring or the owning service's ``__init__``). Application
boot calls :meth:`startup`; application exit calls :meth:`shutdown`.
Both run every registered callback for that direction in deterministic
priority order.

No Qt/PySide6 dependency -- this lives in ``core`` so any layer
(``services``, ``features``, ``infrastructure``) can register a hook
without reaching "up" into ``ui`` (see ``docs/ARCHITECTURE.md``).

Design notes
------------
* **Priority = execution order, lower runs first.** Ties are broken by
  registration order (Python's ``sorted`` is stable) -- documented and
  relied on by tests, not an implementation accident. Same rule for
  both startup and shutdown.
* **Every callback is independently fault-tolerant.** One resource
  failing to start or clean up must never block the others or prevent
  the others from running. Exceptions are caught, logged, and recorded
  in the returned report -- never re-raised. A *hard* dependency (e.g.
  database initialization) that must actually fail loudly on error
  does **not** belong here as a hook -- it stays a direct, explicit
  call in ``app.py``, exactly as it does today; this class is for
  best-effort work only, matching every real caller's own existing
  "must never block boot" intent.
* **Callbacks are async.** Every real startup/cleanup method in this
  codebase already is (``memory_service.enforce_policies``,
  ``stt_provider.preload``, ``voice_service.stop_listening``,
  ``browser_service.shutdown``, ``database.dispose``, ...); this
  doesn't add a sync/async bridge that isn't needed anywhere yet.
* **Startup and shutdown hooks are tracked independently.** Registering
  a startup hook has no effect on the shutdown side and vice versa --
  a resource that needs both registers each explicitly.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from jarvis.core.logging.logger import get_logger

_logger = get_logger("jarvis.core.lifecycle.runtime_manager")

LifecycleCallback = Callable[[], Awaitable[None]]

# Suggested priority bands -- purely a convention (any int works), kept
# here so call sites don't have to invent their own numbering scheme.
# The same bands apply to both startup and shutdown hooks.
PRIORITY_FIRST = 0  # e.g. "announce shutdown while voice is still fully up"
PRIORITY_EARLY = 10  # subsystems that should wind up/down before the rest
PRIORITY_NORMAL = 50  # most resources
PRIORITY_LATE = 90  # things other cleanup steps might still want available
PRIORITY_LAST = 100  # e.g. the database -- the most "final" resource


@dataclass(frozen=True, slots=True)
class LifecycleHook:
    name: str
    callback: LifecycleCallback
    priority: int


@dataclass(frozen=True, slots=True)
class LifecycleResult:
    name: str
    succeeded: bool
    duration_ms: float
    error: str = ""


class RuntimeManager:
    def __init__(self) -> None:
        self._startup_hooks: list[LifecycleHook] = []
        self._shutdown_hooks: list[LifecycleHook] = []
        self._has_started = False
        self._has_shut_down = False

    # ---- Startup ---------------------------------------------------
    def register_startup(
        self, name: str, callback: LifecycleCallback, *, priority: int = PRIORITY_NORMAL
    ) -> None:
        """Register a startup callback. Re-registering an existing
        *name* replaces it (keeps this idempotent for services that
        might construct more than once, e.g. in tests)."""
        self.unregister_startup(name)
        self._startup_hooks.append(LifecycleHook(name, callback, priority))
        _logger.debug("Registered startup hook {!r} (priority={}).", name, priority)

    def unregister_startup(self, name: str) -> None:
        self._startup_hooks = [h for h in self._startup_hooks if h.name != name]

    def is_startup_registered(self, name: str) -> bool:
        return any(h.name == name for h in self._startup_hooks)

    @property
    def registered_startup_names(self) -> list[str]:
        """Names in the order they will actually run (priority, then
        registration order) -- useful for tests and diagnostics."""
        return [h.name for h in self._ordered(self._startup_hooks)]

    async def startup(self) -> list[LifecycleResult]:
        """Run every registered startup hook in priority order. Never
        raises -- each hook's failure is caught, logged, and reflected
        in the returned report instead of stopping the sequence."""
        if self._has_started:
            _logger.warning("RuntimeManager.startup() called more than once -- ignoring.")
            return []
        self._has_started = True
        return await self._run(self._startup_hooks, "Startup")

    # ---- Shutdown ----------------------------------------------------
    def register(
        self, name: str, callback: LifecycleCallback, *, priority: int = PRIORITY_NORMAL
    ) -> None:
        """Register a shutdown/cleanup callback. Re-registering an
        existing *name* replaces it (keeps this idempotent for services
        that might construct more than once, e.g. in tests)."""
        self.unregister(name)
        self._shutdown_hooks.append(LifecycleHook(name, callback, priority))
        _logger.debug("Registered shutdown hook {!r} (priority={}).", name, priority)

    def unregister(self, name: str) -> None:
        self._shutdown_hooks = [h for h in self._shutdown_hooks if h.name != name]

    def is_registered(self, name: str) -> bool:
        return any(h.name == name for h in self._shutdown_hooks)

    @property
    def registered_names(self) -> list[str]:
        """Names in the order they will actually run (priority, then
        registration order) -- useful for tests and diagnostics."""
        return [h.name for h in self._ordered(self._shutdown_hooks)]

    async def shutdown(self) -> list[LifecycleResult]:
        """Run every registered shutdown hook in priority order. Never
        raises -- each hook's failure is caught, logged, and reflected
        in the returned report instead of stopping the sequence."""
        if self._has_shut_down:
            _logger.warning("RuntimeManager.shutdown() called more than once -- ignoring.")
            return []
        self._has_shut_down = True
        return await self._run(self._shutdown_hooks, "Shutdown")

    # ---- Shared ----------------------------------------------------
    @staticmethod
    def _ordered(hooks: list[LifecycleHook]) -> list[LifecycleHook]:
        return sorted(hooks, key=lambda h: h.priority)

    async def _run(self, hooks: list[LifecycleHook], direction: str) -> list[LifecycleResult]:
        results: list[LifecycleResult] = []
        for hook in self._ordered(hooks):
            started = time.monotonic()
            try:
                await hook.callback()
                duration_ms = (time.monotonic() - started) * 1000
                results.append(LifecycleResult(hook.name, True, duration_ms))
                _logger.info(
                    "{} hook {!r} completed ({:.0f}ms).", direction, hook.name, duration_ms
                )
            except Exception as err:
                duration_ms = (time.monotonic() - started) * 1000
                results.append(LifecycleResult(hook.name, False, duration_ms, str(err)))
                _logger.exception(
                    "{} hook {!r} failed after {:.0f}ms.", direction, hook.name, duration_ms
                )

        failed = [r for r in results if not r.succeeded]
        if failed:
            _logger.warning(
                "{} complete with {} failure(s): {}",
                direction,
                len(failed),
                [r.name for r in failed],
            )
        else:
            _logger.info("{} complete: {} hook(s) ran cleanly.", direction, len(results))
        return results
