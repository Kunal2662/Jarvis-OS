"""Application bootstrapper — composition root.

The :class:`ApplicationBootstrapper`:

    1. Loads configuration (`Settings`).
    2. Configures logging.
    3. Builds the DI :class:`~jarvis.core.di.container.Container`.
    4. Starts the requested runtime (GUI / headless / API-only).
    5. Ensures a graceful shutdown on Ctrl+C / SIGTERM / QApplication quit.
"""

from __future__ import annotations

import asyncio
import enum
import signal
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jarvis.core.config.settings import Settings
    from jarvis.core.lifecycle.health_monitor import HealthMonitor
    from jarvis.core.lifecycle.runtime_manager import RuntimeManager


class RunMode(str, enum.Enum):
    GUI = "gui"
    HEADLESS = "headless"
    API_ONLY = "api_only"


class ApplicationBootstrapper:
    def __init__(self, env_file: str | None = None, mode: RunMode = RunMode.GUI) -> None:
        self._env_file: Path | None = Path(env_file) if env_file else None
        self._mode: RunMode = mode
        self._container = None

    def run(self) -> int:
        self._configure()
        self._install_signal_handlers()
        if self._mode is RunMode.GUI:
            return self._run_gui()
        if self._mode is RunMode.HEADLESS:
            return self._run_headless()
        if self._mode is RunMode.API_ONLY:
            return self._run_api_only()
        raise ValueError(f"Unsupported run mode: {self._mode!r}")

    # ------------------------------------------------------------------
    # Boot phases
    # ------------------------------------------------------------------
    def _configure(self) -> None:
        from jarvis.core.config.settings import load_settings
        from jarvis.core.di.container import Container
        from jarvis.core.logging.logger import configure_logging

        settings: Settings = load_settings(env_file=self._env_file)
        configure_logging(settings)

        container = Container()
        container.settings.override(settings)
        container.wire(
            packages=[
                "jarvis.services",
                "jarvis.features",
                "jarvis.agents",
                "jarvis.ui",
                "jarvis.infrastructure",
            ]
        )
        self._container = container

    def _install_signal_handlers(self) -> None:
        for sig_name in ("SIGINT", "SIGTERM"):
            sig = getattr(signal, sig_name, None)
            if sig is None:
                continue
            try:
                signal.signal(sig, self._on_signal)
            except (ValueError, OSError):
                pass

    def _on_signal(self, signum: int, _frame) -> None:
        from loguru import logger

        logger.warning("Received signal {}; requesting shutdown.", signum)
        self.shutdown()

    # ------------------------------------------------------------------
    # Runtime modes
    # ------------------------------------------------------------------
    def _run_gui(self) -> int:
        """Launch the PySide6 UI on a qasync-bridged event loop."""
        import qasync
        from loguru import logger
        from PySide6.QtWidgets import QApplication

        from jarvis.core.config.constants import APP_NAME, APP_ORG
        from jarvis.ui.main_window import MainWindow

        assert self._container is not None
        settings = self._container.settings()

        app = QApplication.instance() or QApplication(sys.argv)
        app.setApplicationName(APP_NAME)
        app.setOrganizationName(APP_ORG)

        # Must happen before any QSS referencing "Inter" is applied
        # (MainWindow applies the theme in its own __init__ below) --
        # otherwise the font-family falls through to a system font.
        from jarvis.ui.themes.fonts import load_application_fonts

        load_application_fonts()

        # Point the icon registry at the vendored SVGs before any view
        # constructs an Icon widget (MainWindow, below, builds the
        # sidebar immediately).
        from jarvis.core.config import paths
        from jarvis.ui.components.icons import icon_registry

        icon_registry.set_icons_dir(paths.ICONS_DIR)

        loop = qasync.QEventLoop(app)
        asyncio.set_event_loop(loop)

        # Initialize database inside the qasync loop before showing UI.
        # A hard dependency -- must fail loudly, not become a
        # fault-isolated RuntimeManager hook (see runtime_manager.py's
        # own design notes on the "best-effort only" boundary).
        database = self._container.database()
        loop.run_until_complete(database.initialize())

        # Milestone 9 — every other best-effort startup step registers
        # with the shared RuntimeManager instead of hand-sequencing its
        # own try/except here, mirroring how ShutdownManager already
        # replaced the equivalent hand-sequenced *shutdown* steps
        # (Milestone 5.5) — the same "doesn't scale" problem, on the
        # startup side.
        runtime_manager = self._container.runtime_manager()
        health_monitor = self._register_task_group_b_hooks(runtime_manager, settings)
        self._register_task_group_c_hooks(runtime_manager)

        # Milestone 3.1 — preload the local Whisper model eagerly instead of
        # paying the load cost on the user's first PTT/toggle-listen call.
        if settings.stt.enabled and settings.stt.backend.value == "whisper_local":
            stt_provider = self._container.stt_provider()
            preload = getattr(stt_provider, "preload", None)
            if preload is not None:

                async def _preload_whisper() -> None:
                    await preload()

                runtime_manager.register_startup("whisper_preload", _preload_whisper)

        startup_started_at = time.monotonic()
        loop.run_until_complete(runtime_manager.startup())
        health_monitor.mark_ready((time.monotonic() - startup_started_at) * 1000)

        # Milestone 9 — Application Lifecycle: publish AppReadyEvent once
        # every registered startup hook has actually run, so the rest of
        # the app (now real, over the Runtime WebSocket API relay above)
        # can react to a genuine "ready" signal instead of assuming
        # readiness once the window is merely constructed.
        from jarvis.core.events.events import AppReadyEvent

        event_bus = self._container.event_bus()
        loop.run_until_complete(event_bus.publish(AppReadyEvent()))

        window = MainWindow(
            settings=settings,
            container=self._container,
        )
        window.show()

        logger.info("JARVIS OS UI ready.")
        try:
            with loop:
                loop.run_forever()
        finally:
            loop.run_until_complete(database.dispose())
            self.shutdown()
        return 0

    def _register_task_group_b_hooks(
        self, runtime_manager: RuntimeManager, settings: Settings
    ) -> HealthMonitor:
        """Milestone 9 Task Group B — deterministic startup order:
        Configuration Manager -> Service Manager -> Session Manager ->
        remaining runtime services (Health Monitor, WebSocket relay,
        embedded API server) -> Application Ready (published by the
        caller once ``runtime_manager.startup()`` returns). Shutdown
        hooks below undo this in reverse. Priorities 0-9 are reserved
        for this sequence; every pre-existing hook (memory policies used
        to live directly in ``_run_gui`` -- now inside ServiceManager's
        ``MemoryServiceAdapter``, see ``core/lifecycle/service_manager.py``
        -- and whisper preload, registered by the caller) keeps its own
        ``PRIORITY_NORMAL`` default and simply runs after this block,
        unchanged from before this task group.

        Split out of ``_run_gui`` purely to keep that method's statement
        count readable -- this is still GUI-runtime-only wiring, not a
        general-purpose entry point other run modes call.
        """
        from jarvis.core.lifecycle.runtime_manager import PRIORITY_FIRST
        from jarvis.infrastructure.api.embedded_server import EmbeddedApiServer
        from jarvis.infrastructure.api.fastapi_server import create_app

        assert self._container is not None
        configuration_manager = self._container.configuration_manager()
        service_manager = self._container.service_manager()
        session_manager = self._container.session_manager()
        health_monitor = self._container.health_monitor()
        runtime_ws_hub = self._container.runtime_ws_hub()
        embedded_api_server = EmbeddedApiServer(
            create_app(settings, self._container),
            host=settings.api.host,
            port=settings.api.port,
        )

        async def _reload_configuration() -> None:
            await configuration_manager.reload()

        runtime_manager.register_startup(
            "configuration_manager", _reload_configuration, priority=PRIORITY_FIRST
        )

        async def _start_services() -> None:
            await service_manager.start_all()

        runtime_manager.register_startup(
            "service_manager", _start_services, priority=PRIORITY_FIRST + 2
        )

        async def _recover_sessions() -> None:
            await session_manager.recover()

        runtime_manager.register_startup(
            "session_manager", _recover_sessions, priority=PRIORITY_FIRST + 4
        )

        async def _start_health_monitor() -> None:
            await health_monitor.start()

        runtime_manager.register_startup(
            "health_monitor", _start_health_monitor, priority=PRIORITY_FIRST + 6
        )

        async def _start_ws_hub() -> None:
            runtime_ws_hub.start()

        runtime_manager.register_startup(
            "runtime_ws_hub", _start_ws_hub, priority=PRIORITY_FIRST + 8
        )

        async def _start_embedded_api_server() -> None:
            await embedded_api_server.start()

        runtime_manager.register_startup(
            "embedded_api_server", _start_embedded_api_server, priority=PRIORITY_FIRST + 9
        )

        # Shutdown -- reverse of the startup order above. Registered
        # ahead of time (RuntimeManager tracks startup/shutdown hooks
        # independently; registration order doesn't imply run order,
        # priority does), same as `_register_shutdown_hooks` in
        # `ui/main_window.py` already does for UI-owned resources.
        # Priorities 2-6 (not 0-4) -- Task Group C's
        # `_register_task_group_c_hooks` claims 0-1 and 7, see there.
        async def _stop_embedded_api_server() -> None:
            await embedded_api_server.stop()

        runtime_manager.register(
            "embedded_api_server", _stop_embedded_api_server, priority=PRIORITY_FIRST + 2
        )

        async def _stop_ws_hub() -> None:
            runtime_ws_hub.stop()

        runtime_manager.register("runtime_ws_hub", _stop_ws_hub, priority=PRIORITY_FIRST + 3)

        async def _stop_health_monitor() -> None:
            await health_monitor.stop()

        runtime_manager.register(
            "health_monitor", _stop_health_monitor, priority=PRIORITY_FIRST + 4
        )

        async def _close_sessions() -> None:
            await session_manager.close_all()

        runtime_manager.register("session_manager", _close_sessions, priority=PRIORITY_FIRST + 5)

        async def _stop_services() -> None:
            await service_manager.stop_all()

        runtime_manager.register("service_manager", _stop_services, priority=PRIORITY_FIRST + 6)

        return health_monitor

    def _register_task_group_c_hooks(self, runtime_manager: RuntimeManager) -> None:
        """Milestone 9 Task Group C -- Reliability. Extends Task Group
        B's deterministic order: Crash Recovery's dirty-check runs
        right after Configuration Manager (priority 1, before Service
        Manager's 2) so every later manager boots with crash status
        already known; Background Task Manager and Resource Manager
        join at the end of startup (priorities 10-11, after Task Group
        B's own 0-9). Shutdown is the reverse: Resource Manager and
        Background Task Manager stop first (priorities 0-1, before Task
        Group B's shutdown hooks, renumbered to 2-6 to make room -- see
        `_register_task_group_b_hooks`), and Crash Recovery marks this
        run clean last of all (priority 7), after every other shutdown
        hook has actually finished, so "clean" is accurate.
        """
        from jarvis.core.lifecycle.runtime_manager import PRIORITY_FIRST

        assert self._container is not None
        crash_recovery = self._container.crash_recovery_manager()
        background_task_manager = self._container.background_task_manager()
        resource_manager = self._container.resource_manager()

        async def _check_crash_recovery() -> None:
            await crash_recovery.check_and_mark_dirty()

        runtime_manager.register_startup(
            "crash_recovery", _check_crash_recovery, priority=PRIORITY_FIRST + 1
        )

        async def _start_background_tasks() -> None:
            await background_task_manager.start()

        runtime_manager.register_startup(
            "background_task_manager", _start_background_tasks, priority=PRIORITY_FIRST + 10
        )

        async def _start_resource_manager() -> None:
            resource_manager.start()

        runtime_manager.register_startup(
            "resource_manager", _start_resource_manager, priority=PRIORITY_FIRST + 11
        )

        async def _stop_resource_manager() -> None:
            resource_manager.stop()

        runtime_manager.register(
            "resource_manager", _stop_resource_manager, priority=PRIORITY_FIRST
        )

        async def _stop_background_tasks() -> None:
            await background_task_manager.stop()

        runtime_manager.register(
            "background_task_manager", _stop_background_tasks, priority=PRIORITY_FIRST + 1
        )

        async def _mark_clean() -> None:
            crash_recovery.mark_clean()

        runtime_manager.register("crash_recovery", _mark_clean, priority=PRIORITY_FIRST + 7)

    def _run_headless(self) -> int:
        from loguru import logger

        logger.info("Starting JARVIS OS in HEADLESS mode.")
        logger.info("Headless runtime not yet implemented (Milestone 2).")
        return 0

    def _run_api_only(self) -> int:
        from loguru import logger

        logger.info("Starting JARVIS OS in API_ONLY mode.")
        logger.info("API-only runtime not yet implemented (Milestone 1+).")
        return 0

    # ------------------------------------------------------------------
    def shutdown(self) -> None:
        if self._container is not None:
            self._container.shutdown_resources()
