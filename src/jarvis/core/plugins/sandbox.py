"""Secure Plugin Sandbox -- Milestone 9 Task Group D, Phase 3.

Two real, working isolation tiers, not one mechanism pretending to be
both:

* :class:`PluginSandbox` (in-process, default) -- every lifecycle hook
  call is wrapped in the same fault-isolation guarantee every other M9
  lifecycle component already makes (one plugin's exception never
  reaches the caller), plus a hard per-call timeout
  (``asyncio.wait_for``) so a hung plugin can't block the platform
  forever. Cheap, but a plugin here still shares the host process's
  memory space and CPU/RAM budget -- a genuine crash (segfault, a
  native-extension abort) can still take the whole app down, and
  per-plugin CPU/memory attribution isn't possible (``psutil`` measures
  the *process*, not one coroutine inside it).

* :class:`PluginProcessSandbox` (opt-in, out-of-process) -- a real
  child process (``multiprocessing``, ``spawn`` start method -- already
  the default on Windows) running the plugin's own event loop,
  reachable only through a request/response pipe. A crash or hang
  there cannot corrupt the parent's memory. ``psutil``-based
  monitor-and-terminate enforces the resource budget -- a real,
  working control, but a *detect-and-kill* one on a polling interval,
  not a kernel-level hard cap; documented as such rather than
  overclaimed.

  **Known, documented v1 limitation:** a process-isolated plugin cannot
  receive the same live, in-process :class:`~jarvis.core.plugins.
  extension_api.PluginContext` the in-process tier hands to
  ``on_load`` -- that object holds live references (the real
  ``EventBus``, ...) that cannot cross a process boundary by value.
  It receives a minimal, this-process-only :class:`MinimalPluginContext`
  instead. A real IPC-relayed Extension API for the process tier is
  listed as Future Work, not silently pretended to work here.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import multiprocessing as mp
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import psutil

from jarvis.core.logging.logger import get_logger
from jarvis.core.plugins.sdk import IPlugin

if TYPE_CHECKING:
    from multiprocessing.connection import Connection

_logger = get_logger("jarvis.core.plugins.sandbox")

DEFAULT_HOOK_TIMEOUT_SECONDS = 10.0
DEFAULT_PROCESS_READY_TIMEOUT_SECONDS = 15.0


@dataclass(frozen=True, slots=True)
class SandboxResult:
    succeeded: bool
    error: str = ""
    duration_ms: float = 0.0


@dataclass(frozen=True, slots=True)
class MinimalPluginContext:
    """The only context a process-isolated plugin's ``on_load`` gets in
    this v1 -- identity only, no live service access. See the module
    docstring's "known, documented v1 limitation" note."""

    plugin_id: str


# ---------------------------------------------------------------------------
# Tier 1 -- in-process.
# ---------------------------------------------------------------------------
class PluginSandbox:
    """Runs one plugin's lifecycle hooks in-process, fault-isolated and
    timeout-bounded. Stateless and cheap -- safe to share across every
    plugin the Registry (Phase 6) manages."""

    def __init__(self, *, hook_timeout_seconds: float = DEFAULT_HOOK_TIMEOUT_SECONDS) -> None:
        self._hook_timeout_seconds = hook_timeout_seconds

    async def run_hook(
        self, plugin_id: str, plugin: IPlugin, hook_name: str, *args: Any
    ) -> SandboxResult:
        """Calls ``getattr(plugin, hook_name)(*args)``, isolating any
        exception or timeout to a reported :class:`SandboxResult`
        rather than letting it propagate -- the same guarantee
        ``ServiceManager.start_all()`` gives every registered service."""
        hook = getattr(plugin, hook_name, None)
        if hook is None:
            return SandboxResult(succeeded=False, error=f"Plugin has no hook {hook_name!r}.")

        started = time.monotonic()
        try:
            await asyncio.wait_for(hook(*args), timeout=self._hook_timeout_seconds)
        except TimeoutError:
            duration_ms = (time.monotonic() - started) * 1000
            _logger.warning(
                "Plugin {!r} hook {!r} timed out after {}s.",
                plugin_id,
                hook_name,
                self._hook_timeout_seconds,
            )
            return SandboxResult(
                succeeded=False,
                error=f"Hook {hook_name!r} timed out after {self._hook_timeout_seconds}s.",
                duration_ms=duration_ms,
            )
        except Exception as err:
            duration_ms = (time.monotonic() - started) * 1000
            _logger.exception("Plugin {!r} hook {!r} raised.", plugin_id, hook_name)
            return SandboxResult(succeeded=False, error=str(err), duration_ms=duration_ms)

        duration_ms = (time.monotonic() - started) * 1000
        return SandboxResult(succeeded=True, duration_ms=duration_ms)


# ---------------------------------------------------------------------------
# Tier 2 -- out-of-process (opt-in).
# ---------------------------------------------------------------------------
def _child_main(conn: Connection, module_file: str, class_name: str, plugin_id: str) -> None:
    """Entry point for the child process (module-level so it's
    picklable for ``multiprocessing``'s ``spawn`` start method). Reads
    the plugin's own source fresh (mirrors ``loader.PluginLoader.
    _exec_module``'s "no stale .pyc" guarantee), constructs one
    instance, then serves hook-call requests over *conn* until told to
    stop or the pipe closes."""
    try:
        source = Path(module_file).read_text(encoding="utf-8")
        spec = importlib.util.spec_from_loader(
            "_jarvis_plugin_child", loader=None, origin=module_file
        )
        if spec is None:
            raise RuntimeError(f"Could not build an import spec for {module_file}.")
        module = importlib.util.module_from_spec(spec)
        module.__file__ = module_file
        exec(compile(source, module_file, "exec"), module.__dict__)
        plugin_class = getattr(module, class_name)
        instance = plugin_class()
    except Exception as err:
        conn.send((False, f"Child process setup failed: {err}"))
        conn.close()
        return

    loop = asyncio.new_event_loop()
    conn.send((True, ""))  # ready signal
    try:
        while True:
            try:
                message = conn.recv()
            except EOFError:
                break
            if message is None or message[0] == "stop":
                break
            _, hook_name = message
            hook = getattr(instance, hook_name, None)
            if hook is None:
                conn.send((False, f"No such hook: {hook_name!r}"))
                continue
            try:
                if hook_name == "on_load":
                    loop.run_until_complete(hook(MinimalPluginContext(plugin_id=plugin_id)))
                else:
                    loop.run_until_complete(hook())
                conn.send((True, ""))
            except Exception as err:
                conn.send((False, str(err)))
    finally:
        loop.close()
        conn.close()


class PluginProcessSandbox:
    """One instance owns exactly one plugin's one child process for
    that process's whole lifetime -- call :meth:`start` once, then any
    number of :meth:`call_hook`\\ s, then :meth:`terminate`."""

    def __init__(
        self,
        plugin_id: str,
        module_file: Path,
        class_name: str,
        *,
        max_cpu_percent: float | None = None,
        max_memory_mb: float | None = None,
    ) -> None:
        self._plugin_id = plugin_id
        self._module_file = module_file
        self._class_name = class_name
        self._max_cpu_percent = max_cpu_percent
        self._max_memory_mb = max_memory_mb
        self._process: mp.process.BaseProcess | None = None
        # Typed loosely: `mp.get_context("spawn").Pipe()` returns a
        # concrete connection subtype typeshed doesn't cleanly unify
        # with `multiprocessing.connection.Connection` across contexts;
        # the real, narrower type is only used structurally below
        # (`.send`/`.recv`/`.poll`/`.close`), so `Any` costs nothing here.
        self._parent_conn: Any | None = None

    def start(
        self, *, ready_timeout: float = DEFAULT_PROCESS_READY_TIMEOUT_SECONDS
    ) -> SandboxResult:
        ctx = mp.get_context("spawn")
        parent_conn, child_conn = ctx.Pipe()
        process = ctx.Process(
            target=_child_main,
            args=(child_conn, str(self._module_file), self._class_name, self._plugin_id),
            daemon=True,
            name=f"jarvis-plugin-{self._plugin_id}",
        )
        process.start()
        self._process = process
        self._parent_conn = parent_conn

        if not parent_conn.poll(ready_timeout):
            self.terminate()
            return SandboxResult(
                succeeded=False, error="Child process did not become ready in time."
            )
        ok, error = parent_conn.recv()
        if not ok:
            self.terminate()
            return SandboxResult(succeeded=False, error=error)
        return SandboxResult(succeeded=True)

    def call_hook(
        self, hook_name: str, *, timeout: float = DEFAULT_HOOK_TIMEOUT_SECONDS
    ) -> SandboxResult:
        if self._parent_conn is None or self._process is None or not self._process.is_alive():
            return SandboxResult(succeeded=False, error="Process sandbox is not running.")
        started = time.monotonic()
        self._parent_conn.send(("call", hook_name))
        if not self._parent_conn.poll(timeout):
            duration_ms = (time.monotonic() - started) * 1000
            self.terminate()
            return SandboxResult(
                succeeded=False,
                error=f"Hook {hook_name!r} timed out after {timeout}s; process terminated.",
                duration_ms=duration_ms,
            )
        ok, error = self._parent_conn.recv()
        duration_ms = (time.monotonic() - started) * 1000
        return SandboxResult(succeeded=ok, error=error, duration_ms=duration_ms)

    def check_resource_budget(self) -> SandboxResult:
        """Real ``psutil``-based monitor-and-terminate -- polls the
        child's own CPU/memory (not the host process's), terminating
        it the moment either configured budget is exceeded. Not a
        kernel-level hard cap: usage between polls is uncontrolled, and
        no budget configured means no enforcement at all (never a
        silent default limit)."""
        if self._process is None or not self._process.is_alive():
            return SandboxResult(succeeded=True)
        if self._max_cpu_percent is None and self._max_memory_mb is None:
            return SandboxResult(succeeded=True)

        try:
            proc = psutil.Process(self._process.pid)
            cpu_percent = proc.cpu_percent(interval=0.1)
            memory_mb = proc.memory_info().rss / (1024 * 1024)
        except psutil.NoSuchProcess:
            return SandboxResult(succeeded=True)

        if self._max_cpu_percent is not None and cpu_percent > self._max_cpu_percent:
            self.terminate()
            return SandboxResult(
                succeeded=False,
                error=f"CPU budget exceeded: {cpu_percent:.1f}% > {self._max_cpu_percent:.1f}%.",
            )
        if self._max_memory_mb is not None and memory_mb > self._max_memory_mb:
            self.terminate()
            return SandboxResult(
                succeeded=False,
                error=f"Memory budget exceeded: {memory_mb:.1f}MB > {self._max_memory_mb:.1f}MB.",
            )
        return SandboxResult(succeeded=True)

    @property
    def is_alive(self) -> bool:
        return self._process is not None and self._process.is_alive()

    def terminate(self) -> None:
        if self._parent_conn is not None:
            with contextlib.suppress(OSError, ValueError):
                self._parent_conn.send(("stop", None))
            self._parent_conn.close()
            self._parent_conn = None
        if self._process is not None and self._process.is_alive():
            self._process.terminate()
            self._process.join(timeout=5)
        self._process = None
