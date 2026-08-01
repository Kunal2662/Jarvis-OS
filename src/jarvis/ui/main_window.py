"""Main application window (Milestone 5 -- Official UI & Frontend Framework).

Layout::

    ┌───────────┬──────────────────────────────────────────┐
    │           │  Home | Chat | Voice | ... (QStackedWidget)│
    │  Sidebar  │                                          │
    │  (nav)    │                                          │
    └───────────┴──────────────────────────────────────────┘

The sidebar now matches the official UI's fixed nav rail (see
``ui/widgets/sidebar.py``); everything to its right is a
``QStackedWidget`` page switched by ``nav_selected``. Home and Chat are
fully built out; the remaining nav items get an honest "future
integration interface" placeholder (see ``ComingSoonView``) until their
own milestone lands.
"""

from __future__ import annotations

import asyncio
import importlib
from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QInputDialog,
    QMainWindow,
    QMenu,
    QStackedWidget,
    QStatusBar,
    QWidget,
)

from jarvis.core.logging.logger import get_logger
from jarvis.core.types import VoiceMode
from jarvis.features.conversation.controller import ConversationController
from jarvis.features.voice.controller import VoiceController
from jarvis.ui.components.icons import icon_registry
from jarvis.ui.dialogs.memory_timeline_dialog import MemoryTimelineDialog
from jarvis.ui.dialogs.private_transcript_dialog import PrivateTranscriptDialog
from jarvis.ui.dialogs.settings_dialog import SettingsDialog
from jarvis.ui.dialogs.update_terminal_dialog import UpdateTerminalDialog
from jarvis.ui.themes.theme_manager import ThemeManager
from jarvis.ui.tray_icon import SystemTrayIcon
from jarvis.ui.views.coming_soon_view import ComingSoonView
from jarvis.ui.views.developer.entry import open_developer_mode
from jarvis.ui.views.home_view import HomeView
from jarvis.ui.widgets.chat_page import ChatPage
from jarvis.ui.widgets.sidebar import NAV_ITEMS, Sidebar
from jarvis.ui.widgets.status_chip import ProviderChip
from jarvis.utils.async_utils import fire_and_forget

if TYPE_CHECKING:
    from jarvis.core.config.settings import Settings
    from jarvis.core.di.container import Container

_logger = get_logger("jarvis.ui.main_window")

# Nav ids with a real, fully-built page. Milestone 5 completion pass:
# Voice, Files & Drive, Browser, Coding, Finance, Smart Home, Calendar,
# Gmail, and Spotify all got real desktop workspaces (mock data, real
# UI -- see ui/views/workspaces/). Only Automations remains a
# ComingSoonView placeholder: it wasn't in this pass's scope and the
# automation engine itself is already reachable via the Developer
# Console.
_REAL_PAGES = {
    "home",
    "chat",
    "voice",
    "files",
    "browser",
    "coding",
    "finance",
    "smart_home",
    "calendar",
    "gmail",
    "spotify",
}

# Milestone 5.5 performance fix: importing all 9 workspace modules
# eagerly (the old ``from jarvis.ui.views.workspaces import (...)`` at
# module top) cost ~358ms measured (`python -X importtime`) -- about
# 20% of this module's entire import chain -- even for users who never
# visit most of them in a session. Construction was already lazy (see
# ``_on_nav_selected``); the *import* wasn't. Each factory now defers
# its module import to first use, same lazy-loading principle applied
# one layer earlier.
_WORKSPACE_FACTORIES: dict[str, Callable[[], QWidget]] = {
    "voice": lambda: _import_workspace("voice_workspace", "VoiceWorkspace")(),
    "files": lambda: _import_workspace("files_workspace", "FilesWorkspace")(),
    "browser": lambda: _import_workspace("browser_workspace", "BrowserWorkspace")(),
    "coding": lambda: _import_workspace("coding_workspace", "CodingWorkspace")(),
    "finance": lambda: _import_workspace("finance_workspace", "FinanceWorkspace")(),
    "smart_home": lambda: _import_workspace("smart_home_workspace", "SmartHomeWorkspace")(),
    "calendar": lambda: _import_workspace("calendar_workspace", "CalendarWorkspace")(),
    "gmail": lambda: _import_workspace("gmail_workspace", "GmailWorkspace")(),
    "spotify": lambda: _import_workspace("spotify_workspace", "SpotifyWorkspace")(),
}


def _import_workspace(module_name: str, class_name: str) -> type:
    module = importlib.import_module(f"jarvis.ui.views.workspaces.{module_name}")
    return getattr(module, class_name)


_COMING_SOON_COPY: dict[str, str] = {
    "automations": "A dedicated Automations screen is a future integration interface. "
    "The automation engine itself is fully built -- try the Developer Console.",
}


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings, container: Container) -> None:
        super().__init__()
        self._settings = settings
        self._container = container
        self._transcript_dialog: PrivateTranscriptDialog | None = None
        self._update_terminal: UpdateTerminalDialog | None = None
        self._last_real_nav_id = "home"
        self._shutting_down = False

        self.setWindowTitle(f"{settings.app_name} — {settings.app_version}")
        self.resize(1400, 900)

        # Theme.
        self._theme_manager = ThemeManager(container.theme_service())
        self._theme_manager.apply(QApplication.instance(), theme=settings.ui.theme)

        # --- Sidebar ----------------------------------------------------
        self._sidebar = Sidebar(self, app_version=f"v{settings.app_version}")

        # --- Content pages ------------------------------------------------
        self._stack = QStackedWidget(self)
        self._page_index: dict[str, int] = {}

        self._user_name = "Aditya"
        self._home_view = HomeView(
            self._user_name,
            automation_service=container.automation_service(),
            memory_service=container.memory_service(),
        )
        self._add_page("home", self._home_view)

        self._chat_page = ChatPage(self)
        self._add_page("chat", self._chat_page)

        # The 9 Milestone-5-completion workspaces (Voice, Files & Drive,
        # Browser, Coding, Finance, Smart Home, Calendar, Gmail, Spotify)
        # are built lazily on first visit rather than all up front --
        # see ``_on_nav_selected`` -- so app startup doesn't pay for
        # constructing nine full dashboards nobody may ever open this
        # session (Milestone 5, section 12: lazy loading).
        for item_id, _icon, label in NAV_ITEMS:
            if (
                item_id in _WORKSPACE_FACTORIES
                or item_id in _REAL_PAGES
                or item_id in ("settings", "memory")
            ):
                continue
            self._add_page(item_id, ComingSoonView(label, _COMING_SOON_COPY.get(item_id, "")))

        # Layout.
        central = QWidget(self)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._sidebar)
        root.addWidget(self._stack, 1)
        self.setCentralWidget(central)

        # Status bar.
        self._provider_chip = ProviderChip(self)
        self._voice_chip = ProviderChip(self)
        self._voice_chip.set_state("unknown", "Voice: idle")
        status = QStatusBar(self)
        status.addPermanentWidget(self._voice_chip)
        status.addPermanentWidget(self._provider_chip)
        self.setStatusBar(status)
        self._provider_chip.set_state("unknown", f"LLM: {container.llm_provider().name}")

        # Controllers.
        self._chat_controller = ConversationController(
            chat_service=container.chat_service(),
            conversation_service=container.conversation_service(),
            parent=self,
        )
        self._voice_controller = VoiceController(
            voice_service=container.voice_service(),
            settings=settings,
            parent=self,
        )

        # Tray.
        self._tray = SystemTrayIcon(self)
        try:
            self._tray.show()
        except Exception:
            _logger.warning("System tray not available on this platform.")

        # Menu + wiring + hotkeys.
        self._build_menu()
        self._wire_signals()
        self._subscribe_update_events()
        self._register_shutdown_hooks()
        self._start_memory_policy_scheduler()
        fire_and_forget(self._on_start())

    # ------------------------------------------------------------------
    def _add_page(self, item_id: str, widget: QWidget) -> None:
        index = self._stack.addWidget(widget)
        self._page_index[item_id] = index

    # ------------------------------------------------------------------
    # Wiring
    # ------------------------------------------------------------------
    def _wire_signals(self) -> None:
        self._sidebar.nav_selected.connect(self._on_nav_selected)
        self._sidebar.new_conversation_requested.connect(self._chat_controller.new_conversation)
        self._sidebar.conversation_selected.connect(self._on_conversation_selected)
        self._sidebar.settings_requested.connect(self._open_settings)
        self._sidebar.memory_requested.connect(self._open_memory_timeline)
        self._sidebar.developer_mode_requested.connect(self._open_developer_mode)
        self._sidebar.update_indicator_clicked.connect(self._reopen_update_terminal)
        self._sidebar.update_history_requested.connect(self._show_update_history_popup)

        self._chat_page.new_conversation_requested.connect(self._chat_controller.new_conversation)
        self._chat_page.conversation_selected.connect(self._on_conversation_selected)
        self._chat_page.prompt.submitted.connect(self._chat_controller.send)
        self._chat_page.prompt.submitted.connect(self._on_user_message_submitted)

        # Home dashboard -> Chat.
        self._home_view.ask_jarvis_requested.connect(self._ask_jarvis_from_home)

        # PTT button (lives on the Chat page now).
        if self._settings.voice.mode is VoiceMode.PUSH_TO_TALK:
            self._chat_page.ptt.pressed_ptt.connect(self._voice_controller.press_to_talk)
            self._chat_page.ptt.released_ptt.connect(self._voice_controller.release_to_talk)
        else:
            self._chat_page.ptt.clicked.connect(self._voice_controller.toggle_listening)

        # Voice → prompt. (transcribed carries the *final* STT result --
        # true partial/incremental voice-token streaming into the
        # transcript would need a partial-results signal the voice
        # pipeline doesn't expose yet; begin_user_stream/append_user_token
        # on PrivateTranscriptDialog are ready for that follow-up.)
        self._voice_controller.transcribed.connect(self._chat_page.prompt._text.setPlainText)
        self._voice_controller.transcribed.connect(self._chat_controller.send)
        self._voice_controller.transcribed.connect(self._on_user_message_submitted)
        self._voice_controller.state_changed.connect(self._on_voice_state_changed)
        self._voice_controller.error.connect(self._on_error)
        self._voice_controller.set_continuous_conversation(
            self._settings.voice.continuous_conversation
        )
        if self._settings.wake.enabled:
            self._voice_controller.start_wake_word()

        # Chat controller.
        self._chat_controller.conversations_loaded.connect(self._chat_page.set_conversations)
        self._chat_controller.stream_started.connect(self._on_stream_started)
        self._chat_controller.stream_started.connect(self._voice_controller.on_llm_stream_started)
        self._chat_controller.token.connect(self._chat_page.chat_view.append_token)
        self._chat_controller.token.connect(self._on_assistant_token)
        self._chat_controller.token.connect(self._voice_controller.on_llm_token)
        self._chat_controller.stream_finished.connect(self._on_stream_finished)
        self._chat_controller.stream_finished.connect(self._voice_controller.on_llm_stream_finished)
        self._chat_controller.error.connect(self._on_error)

        # Tray.
        self._tray.show_requested.connect(self._show_from_tray)
        self._tray.hide_requested.connect(self.hide)
        self._tray.toggle_requested.connect(self._toggle_window)
        self._tray.quit_requested.connect(self._quit_app)
        self._tray.voice_mode_requested.connect(lambda: self._on_nav_selected("chat"))
        self._tray.private_transcript_requested.connect(self._open_private_transcript)
        self._tray.quick_commands_requested.connect(self._open_quick_commands)
        self._tray.smart_home_requested.connect(lambda: self._on_nav_selected("smart_home"))
        self._tray.settings_requested.connect(self._open_settings)

    def _build_menu(self) -> None:
        menu = self.menuBar()
        file_menu = menu.addMenu("&File")
        new_action = QAction("New chat", self)
        new_action.setShortcut(QKeySequence.StandardKey.New)
        new_action.triggered.connect(self._chat_controller.new_conversation)
        file_menu.addAction(new_action)

        settings_action = QAction("Settings…", self)
        settings_action.setShortcut(QKeySequence("Ctrl+,"))
        settings_action.triggered.connect(self._open_settings)
        file_menu.addAction(settings_action)

        dev_mode_action = QAction("Developer Mode…", self)
        dev_mode_action.setShortcut(QKeySequence("Ctrl+Shift+D"))
        dev_mode_action.triggered.connect(self._open_developer_mode)
        file_menu.addAction(dev_mode_action)

        file_menu.addSeparator()
        quit_action = QAction("Quit", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self._quit_app)
        file_menu.addAction(quit_action)

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------
    async def _on_start(self) -> None:
        self._chat_controller.refresh_conversations()
        try:
            status = await self._container.llm_provider().health()
            state = "healthy" if status.healthy else ("down" if status.enabled else "unknown")
            self._provider_chip.set_state(state, f"LLM: {status.name}")
        except Exception:
            self._provider_chip.set_state("down", "LLM: error")

        try:
            await self._install_hotkeys()
        except Exception:
            _logger.exception("Failed to install global hotkeys.")

        await self._greet_user()

    async def _greet_user(self) -> None:
        """Personalized Greeting Engine (JARVIS Personalized Greeting
        System) -- replaces the generic "JARVIS is now online." startup
        announcement with a dynamically generated, context-aware,
        non-repetitive greeting: shown on the Home dashboard and spoken
        aloud. Falls back to the static time-of-day greeting already on
        screen (set at HomeView construction) if generation fails for
        any reason -- greeting failures must never block startup."""
        try:
            greeting_service = self._container.greeting_service()
            context = await greeting_service.build_context(
                self._user_name, current_workspace=self._last_real_nav_id
            )
            greeting = await greeting_service.generate(context)
        except Exception:
            _logger.exception("Personalized greeting generation failed; keeping default greeting.")
            return

        self._home_view.set_greeting(greeting)
        try:
            self._voice_controller.speak(greeting)
        except Exception:
            _logger.exception("Speaking the personalized greeting failed.")

    async def _install_hotkeys(self) -> None:
        service = self._container.hotkey_service()
        await service.start()

        toggle_combo = self._settings.hotkey.toggle_window
        if toggle_combo:
            service.register("toggle_window", toggle_combo, self._toggle_window)

        v = self._settings.voice
        if v.mode is VoiceMode.PUSH_TO_TALK and v.push_to_talk_hotkey:
            service.register("ptt", v.push_to_talk_hotkey, self._voice_controller.toggle_listening)
        elif v.mode is VoiceMode.TOGGLE and v.toggle_hotkey:
            service.register(
                "toggle_listen", v.toggle_hotkey, self._voice_controller.toggle_listening
            )

    def _start_memory_policy_scheduler(self) -> None:
        if not self._settings.memory.enabled:
            return
        interval_ms = 6 * 60 * 60 * 1000  # 6 hours
        self._memory_policy_timer = QTimer(self)
        self._memory_policy_timer.setInterval(interval_ms)
        self._memory_policy_timer.timeout.connect(self._run_memory_policies)
        self._memory_policy_timer.start()

    def _run_memory_policies(self) -> None:
        fire_and_forget(self._run_memory_policies_async())

    async def _run_memory_policies_async(self) -> None:
        try:
            await self._container.memory_service().enforce_policies()
        except Exception:
            _logger.exception("Scheduled memory policy enforcement failed.")

    # ------------------------------------------------------------------
    # Milestone 5 -- Update Center sidebar indicator + Update Terminal
    # ------------------------------------------------------------------
    def _subscribe_update_events(self) -> None:
        from jarvis.core.events.events import UpdatePhaseEvent

        async def _on_event(evt: UpdatePhaseEvent) -> None:
            if evt.phase in ("update_completed", "rollback_completed", "failed"):
                self._sidebar.hide_update_progress()
                self._refresh_update_history()
            else:
                self._sidebar.show_update_progress(
                    evt.progress_percent, evt.phase.replace("_", " ").title()
                )

        self._container.event_bus().subscribe(UpdatePhaseEvent, _on_event)
        self._refresh_update_history()

    def _refresh_update_history(self) -> None:
        try:
            history = self._container.update_service().session_history()
        except Exception:
            return
        self._sidebar.set_update_history(history)

    def _show_update_history_popup(self) -> None:
        history = self._container.update_service().session_history(limit=8)
        menu = QMenu(self)
        if not history:
            no_history = menu.addAction("No updates yet")
            no_history.setEnabled(False)
        for session in history:
            when = (
                session.finished_at.strftime("%b %d, %H:%M")
                if session.finished_at
                else "in progress"
            )
            if session.rollback_report is not None:
                icon_key = "history" if session.rollback_report.succeeded else "warning"
                label = f"Rolled back to {session.from_version} · {when}"
            elif session.succeeded:
                icon_key = "check"
                label = f"Updated to {session.to_version} · {when}"
            else:
                icon_key = "error"
                label = f"Failed: {session.from_version} → {session.to_version} · {when}"
            menu.addAction(icon_registry.qicon(icon_key, size=14), label)
        menu.addSeparator()
        menu.addAction("Open Update Terminal…").triggered.connect(self._reopen_update_terminal)
        self._update_history_menu = menu  # keep alive -- popup() is non-blocking
        menu.popup(self._sidebar.mapToGlobal(self._sidebar.rect().bottomLeft()))

    def _reopen_update_terminal(self) -> None:
        if self._update_terminal is None:
            self._update_terminal = UpdateTerminalDialog(self._container.event_bus(), self)
        self._update_terminal.show()
        self._update_terminal.raise_()
        self._update_terminal.activateWindow()

    # ------------------------------------------------------------------
    # Slots -- navigation
    # ------------------------------------------------------------------
    def _on_nav_selected(self, item_id: str) -> None:
        if item_id in ("settings", "memory"):
            # These open dialogs (wired via settings_requested/memory_requested);
            # keep whichever real page was showing highlighted underneath.
            self._sidebar.select(self._last_real_nav_id)
            return
        if item_id not in self._page_index and item_id in _WORKSPACE_FACTORIES:
            # First visit to this workspace this session -- build it now
            # (lazy loading, Milestone 5 section 12) and cache it in the
            # stack for every subsequent visit.
            factory = _WORKSPACE_FACTORIES[item_id]
            self._add_page(item_id, factory())
        index = self._page_index.get(item_id)
        if index is not None:
            self._stack.setCurrentIndex(index)
            self._last_real_nav_id = item_id
            self._sidebar.select(item_id)

    def _ask_jarvis_from_home(self, text: str) -> None:
        self._on_nav_selected("chat")
        self._chat_controller.send(text)

    def _on_conversation_selected(self, conversation_id: str) -> None:
        self._chat_controller.select_conversation(conversation_id)
        fire_and_forget(self._load_history(conversation_id))

    async def _load_history(self, conversation_id: str) -> None:
        self._chat_page.chat_view.clear()
        history = await self._container.conversation_service().history(conversation_id)
        for msg in history:
            self._chat_page.chat_view.add_message(msg.role, msg.content)

    def _on_stream_started(self, _conversation_id: str) -> None:
        self._chat_page.prompt.set_enabled_input(False)
        self._chat_page.chat_view.begin_assistant()
        if self._transcript_dialog is not None:
            self._transcript_dialog.begin_assistant_stream()

    def _on_assistant_token(self, token: str) -> None:
        if self._transcript_dialog is not None:
            self._transcript_dialog.append_assistant_token(token)

    def _on_stream_finished(self, full_text: str) -> None:
        self._chat_page.chat_view.end_assistant()
        self._chat_page.prompt.set_enabled_input(True)
        if self._transcript_dialog is not None:
            self._transcript_dialog.end_assistant_stream()

    def _on_user_message_submitted(self, text: str) -> None:
        if self._transcript_dialog is not None and text.strip():
            self._transcript_dialog.add_message("user", text.strip())

    def _on_voice_state_changed(self, state: str, detail: str) -> None:
        labels = {
            "idle": ("unknown", "Voice: idle"),
            "listening": ("healthy", "Voice: listening"),
            "thinking": ("degraded", "Voice: thinking"),
            "speaking": ("healthy", "Voice: speaking"),
            "interrupted": ("degraded", "Voice: interrupted"),
            "offline": ("down", "Voice: offline"),
            "error": ("down", f"Voice: error — {detail}" if detail else "Voice: error"),
        }
        color, text = labels.get(state, ("unknown", f"Voice: {state}"))
        self._voice_chip.set_state(color, text)
        self._home_view.voice_orb.set_state(state, detail)
        self._chat_page.voice_orb.set_state(state, detail)

    def _on_error(self, message: str) -> None:
        self._chat_page.chat_view.add_message("system", message)
        self._chat_page.prompt.set_enabled_input(True)

    # ------------------------------------------------------------------
    # Dialogs / tray helpers
    # ------------------------------------------------------------------
    def _open_settings(self) -> None:
        dlg = SettingsDialog(
            settings=self._settings,
            settings_service=self._container.settings_service(),
            theme_manager=self._theme_manager,
            memory_service=self._container.memory_service(),
            container=self._container,
            parent=self,
        )
        dlg.exec()

    def _open_memory_timeline(self) -> None:
        dlg = MemoryTimelineDialog(
            memory_service=self._container.memory_service(),
            parent=self,
        )
        dlg.exec()

    def _open_developer_mode(self) -> None:
        open_developer_mode(self._settings, self._container, self)

    def _open_private_transcript(self) -> None:
        if self._transcript_dialog is None:
            self._transcript_dialog = PrivateTranscriptDialog(self)
        self._transcript_dialog.show()
        self._transcript_dialog.raise_()
        self._transcript_dialog.activateWindow()

    def _open_quick_commands(self) -> None:
        text, ok = QInputDialog.getText(
            self, "Quick Commands", "Enter a command for JARVIS to run:"
        )
        if ok and text.strip():
            fire_and_forget(self._container.automation_service().run_command(text.strip()))

    def _toggle_window(self) -> None:
        if self.isVisible() and not self.isMinimized():
            self.hide()
        else:
            self._show_from_tray()

    def _show_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit_app(self) -> None:
        self._shutting_down = True
        fire_and_forget(self._graceful_quit())

    def _register_shutdown_hooks(self) -> None:
        """Register every resource's cleanup with the shared
        ``ShutdownManager`` (Milestone 5.5) instead of hand-sequencing
        them inline in ``_graceful_quit``. Adding a future subsystem's
        cleanup (an IoT/smart-home bridge, a plugin loader, the agent
        orchestrator, a local web server, ...) is one more
        ``register(...)`` call wherever that subsystem is constructed
        -- it never requires touching ``MainWindow`` again.

        Priority order preserves the exact sequence this app has always
        shut down in: announce shutdown while voice is still fully up
        -> stop voice -> release the browser -> stop hotkeys -> close
        the database last (the most "final" resource).
        """
        from jarvis.core.lifecycle.shutdown_manager import (
            PRIORITY_EARLY,
            PRIORITY_FIRST,
            PRIORITY_LAST,
            PRIORITY_NORMAL,
        )
        from jarvis.domain.voice_announcements.events import AnnouncementEvent

        manager = self._container.shutdown_manager()

        async def _announce_shutdown() -> None:
            await self._container.voice_announcement_service().announce_event(
                AnnouncementEvent.SHUTDOWN
            )

        manager.register("voice_announcement", _announce_shutdown, priority=PRIORITY_FIRST)

        voice_service = self._container.voice_service()

        async def _stop_voice() -> None:
            await voice_service.stop_wake_word()
            await voice_service.stop_speaking()
            if voice_service.is_listening:
                await voice_service.stop_listening()

        manager.register("voice_service", _stop_voice, priority=PRIORITY_EARLY)

        async def _stop_agent_orchestrator() -> None:
            await self._container.agent_orchestrator().stop()

        # Same tier as voice: the orchestrator wraps automation/browser as
        # tools, so it must release its checkpointer before those
        # lower-level resources shut down below.
        manager.register("agent_orchestrator", _stop_agent_orchestrator, priority=PRIORITY_EARLY)

        async def _stop_browser() -> None:
            await self._container.browser_service().shutdown()

        manager.register("browser_service", _stop_browser, priority=PRIORITY_NORMAL)

        async def _stop_hotkeys() -> None:
            await self._container.hotkey_service().stop()

        manager.register("hotkey_service", _stop_hotkeys, priority=PRIORITY_NORMAL)

        async def _dispose_database() -> None:
            await self._container.database().dispose()

        manager.register("database", _dispose_database, priority=PRIORITY_LAST)

    async def _graceful_quit(self) -> None:
        """Release every real resource the app is holding before exit,
        via the shared ``ShutdownManager`` (Milestone 5.5). Each
        registered hook is independently fault-tolerant -- one
        resource failing to clean up never blocks the others or
        prevents the app from closing (see ``ShutdownManager.shutdown``).
        """
        await self._container.shutdown_manager().shutdown()
        self.close()

    # ------------------------------------------------------------------
    def closeEvent(self, event) -> None:
        """Milestone 5.5 reliability fix: closing the window (the OS
        title-bar X button, Alt+F4, window-manager close, ...) used to
        bypass ``_graceful_quit()`` entirely and just stop the event
        loop directly -- meaning hotkeys/voice/browser/database were
        never released unless the user specifically used the tray or
        menu "Quit" action. There's no "minimize to tray on close"
        design in this app (closing the window has always meant quit,
        per the tray-menu's separate explicit "Hide" action) so this
        doesn't change what closing the window *does* -- it only makes
        that already-intended quit path release resources properly,
        same as the tray/menu path already does.

        First close request: ignore it, kick off the same graceful
        shutdown the tray/menu Quit action uses. That shutdown calls
        ``self.close()`` again once cleanup finishes, which re-enters
        this method a second time -- ``_shutting_down`` is already True
        by then, so that second call actually lets the close proceed
        and stops the event loop.
        """
        if not self._shutting_down:
            self._shutting_down = True
            event.ignore()
            fire_and_forget(self._graceful_quit())
            return
        _logger.info("MainWindow closing — asking loop to stop.")
        loop = asyncio.get_event_loop()
        loop.stop()
        super().closeEvent(event)
