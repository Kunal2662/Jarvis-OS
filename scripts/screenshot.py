"""Render the MainWindow offscreen and save a PNG for visual inspection."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def main() -> int:
    root = Path(__file__).resolve().parent
    tmp = Path("/tmp/jarvis_screenshot")
    tmp.mkdir(exist_ok=True)
    os.environ["JARVIS_DATA_DIR"] = str(tmp)
    os.environ["JARVIS_DB_URL"] = f"sqlite+aiosqlite:///{tmp / 'jarvis.db'}"
    os.environ["JARVIS_OPENAI_ENABLED"] = "false"
    os.environ["JARVIS_OLLAMA_ENABLED"] = "true"

    sys.path.insert(0, str(root / "src"))
    sys.path.insert(0, str(root))

    import qasync
    from PySide6.QtWidgets import QApplication
    from tests.fakes.fake_llm import FakeLLM

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
    container.llm_provider.override(FakeLLM())

    async def _run() -> int:
        db = container.database()
        await db.initialize()
        try:
            window = MainWindow(settings=settings, container=container)
            window.resize(1400, 860)
            window.show()

            # Simulate some content.
            chat_view = window._chat_view
            chat_view.add_message("user", "What can you do?")
            chat_view.add_message(
                "assistant",
                "I'm JARVIS. I can chat, remember what you tell me, control your browser, "
                "and automate Windows tasks. Ask me anything.",
            )

            await asyncio.sleep(0.3)
            window.grab().save(str(root / "docs" / "diagrams" / "milestone1-mainwindow.png"))
            print("Saved: docs/diagrams/milestone1-mainwindow.png")

            # Settings dialog snapshot.
            dlg = SettingsDialog(
                settings=settings,
                settings_service=container.settings_service(),
                theme_manager=ThemeManager(container.theme_service()),
                parent=window,
            )
            dlg.resize(1000, 700)
            dlg.show()
            await asyncio.sleep(0.2)
            dlg.grab().save(str(root / "docs" / "diagrams" / "milestone1-settings.png"))
            print("Saved: docs/diagrams/milestone1-settings.png")

            return 0
        finally:
            await db.dispose()

    with loop:
        return loop.run_until_complete(_run())


if __name__ == "__main__":
    raise SystemExit(main())
