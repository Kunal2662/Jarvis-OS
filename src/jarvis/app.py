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
from pathlib import Path


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
        from jarvis.core.config.settings import Settings, load_settings
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

        # Milestone 3 — apply memory retention/pruning policies once at
        # startup. Best-effort: a failure here must never block boot.
        if settings.memory.enabled:
            memory_service = self._container.memory_service()

            async def _enforce_memory_policies() -> None:
                await memory_service.enforce_policies()

            runtime_manager.register_startup("memory_policies", _enforce_memory_policies)

        # Milestone 3.1 — preload the local Whisper model eagerly instead of
        # paying the load cost on the user's first PTT/toggle-listen call.
        if settings.stt.enabled and settings.stt.backend.value == "whisper_local":
            stt_provider = self._container.stt_provider()
            preload = getattr(stt_provider, "preload", None)
            if preload is not None:

                async def _preload_whisper() -> None:
                    await preload()

                runtime_manager.register_startup("whisper_preload", _preload_whisper)

        loop.run_until_complete(runtime_manager.startup())

        # Milestone 9 — Application Lifecycle: publish AppReadyEvent once
        # every registered startup hook has actually run, so the rest of
        # the app (and, eventually, M8's frontend over WebSocket) can
        # react to a real "ready" signal instead of assuming readiness
        # once the window is merely constructed.
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
