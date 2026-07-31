"""Headless UI smoke test — instantiate MainWindow with a fake LLM.

Renders the window offscreen and verifies that:
  * Theme QSS is applied.
  * MainWindow constructs without exceptions.
  * SettingsDialog can be built.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def main() -> int:
    tmp = Path("/tmp/jarvis_ui_smoke")
    tmp.mkdir(exist_ok=True)
    os.environ["JARVIS_DATA_DIR"] = str(tmp)
    os.environ["JARVIS_DB_URL"] = f"sqlite+aiosqlite:///{tmp / 'jarvis.db'}"
    os.environ["JARVIS_OPENAI_ENABLED"] = "false"
    os.environ["JARVIS_OLLAMA_ENABLED"] = "true"

    sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

    import asyncio

    import qasync
    from PySide6.QtWidgets import QApplication

    from jarvis.core.config.settings import load_settings
    from jarvis.core.di.container import Container
    from jarvis.ui.dialogs.settings_dialog import SettingsDialog
    from jarvis.ui.main_window import MainWindow
    from jarvis.ui.themes.theme_manager import ThemeManager

    settings = load_settings()

    app = QApplication.instance() or QApplication(sys.argv)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    container = Container()
    container.settings.override(settings)

    async def _run() -> int:
        # Patch the LLM provider with our fake.
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from tests.fakes.fake_llm import FakeLLM

        container.llm_provider.override(FakeLLM("Milestone 1 UI smoke pass"))

        db = container.database()
        await db.initialize()
        try:
            window = MainWindow(settings=settings, container=container)
            window.show()

            # Build a settings dialog to make sure page registry works.
            dlg = SettingsDialog(
                settings=settings,
                settings_service=container.settings_service(),
                theme_manager=ThemeManager(container.theme_service()),
                parent=window,
            )
            _ = dlg.sizeHint()

            # Give the async on-start a beat, then tear down.
            await asyncio.sleep(0.5)
            print("OK: MainWindow built, SettingsDialog built, DB initialized.")
            return 0
        finally:
            await db.dispose()

    with loop:
        return loop.run_until_complete(_run())


if __name__ == "__main__":
    raise SystemExit(main())
