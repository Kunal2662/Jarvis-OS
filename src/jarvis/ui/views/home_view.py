"""Home dashboard -- the official JARVIS UI (Milestone 5, single source
of truth screenshot). Recreates: greeting header + search bar, the
hero voice panel with quick-prompt pills, Today's Schedule / Tasks
cards, the Gmail/Spotify/Weather/Finance/Smart-Home service card row,
the "Speaking with Jarvis" transcript panel, and the Quick Actions grid.

What's real vs. mock, by design (documented again in
MILESTONE_5_DELIVERY.md):

* Voice orb, greeting, search bar, and the four Quick Actions tiles are
  wired to real services (VoiceController / AutomationService /
  MemoryService) where one already exists.
* Gmail, Spotify, Weather, Finance and Smart Home cards render
  realistic mock data -- there is no Gmail/Spotify/weather/brokerage/
  home-automation integration yet, so these are explicitly the "Future
  Integration Interfaces" the milestone checklist asks for: the card
  shape is final, the data source is the only thing left to plug in.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from jarvis.features.integrations.mocks import (
    MockFinanceProvider,
    MockGmailProvider,
    MockSmartHomeProvider,
    MockSpotifyProvider,
    MockWeatherProvider,
)
from jarvis.ui.components import (
    Card,
    IconTextButton,
    PillButton,
    SectionCard,
    ServiceWidget,
    SimpleListPanel,
)
from jarvis.ui.components.icons import Icon, icon_registry
from jarvis.ui.widgets.voice_orb import VoiceOrb
from jarvis.utils.async_utils import fire_and_forget

if TYPE_CHECKING:
    from jarvis.services.automation_service import AutomationService
    from jarvis.services.memory_service import MemoryService


class HomeView(QWidget):
    ask_jarvis_requested = Signal(str)  # quick prompt / search -> Chat page
    automation_requested = Signal(str)  # natural-language command -> AutomationService

    def __init__(
        self,
        user_name: str = "there",
        parent: QWidget | None = None,
        *,
        automation_service: AutomationService | None = None,
        memory_service: MemoryService | None = None,
    ) -> None:
        super().__init__(parent)
        self._automation = automation_service
        self._memory = memory_service

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(20, 16, 20, 20)
        outer.setSpacing(16)

        outer.addLayout(self._build_top_bar(user_name))
        outer.addLayout(self._build_hero_row())
        outer.addLayout(self._build_service_row())
        outer.addLayout(self._build_bottom_row())

        scroll.setWidget(content)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

        QShortcut(QKeySequence("Ctrl+K"), self, activated=self._focus_search)

    # ------------------------------------------------------------------
    # Top bar -- greeting + search
    # ------------------------------------------------------------------
    def _build_top_bar(self, user_name: str) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(16)

        greet_col = QVBoxLayout()
        greet_col.setSpacing(2)
        from datetime import datetime

        now = datetime.now()
        hour = now.hour
        salutation = (
            "Good Morning" if hour < 12 else "Good Afternoon" if hour < 18 else "Good Evening"
        )
        title = QLabel(f"{salutation}, {user_name}")
        title.setObjectName("greetingTitle")
        self._greeting_title = title
        subtitle = QLabel(now.strftime("%A, %d %B %Y · %I:%M %p"))
        subtitle.setObjectName("greetingSubtitle")
        greet_col.addWidget(title)
        greet_col.addWidget(subtitle)
        row.addLayout(greet_col)
        row.addStretch(1)

        self._search = QLineEdit()
        self._search.setObjectName("searchBar")
        self._search.setPlaceholderText("Ask anything, Jarvis…    Ctrl+K")
        self._search.setFixedWidth(360)
        self._search.returnPressed.connect(self._on_search_submitted)
        row.addWidget(self._search)

        bell = QPushButton()
        bell.setObjectName("cardAction")
        bell.setIcon(icon_registry.qicon("notification", size=18))
        row.addWidget(bell)
        return row

    def set_greeting(self, text: str) -> None:
        """Replace the static time-of-day greeting with a Personalized
        Greeting Engine result (see ``services/greeting_service.py``).
        Called once at startup after context gathering + generation
        finishes; the time-based placeholder set at construction stays
        visible until then so the dashboard never looks blank."""
        self._greeting_title.setText(text)

    def _focus_search(self) -> None:
        self._search.setFocus()
        self._search.selectAll()

    def _on_search_submitted(self) -> None:
        text = self._search.text().strip()
        if text:
            self.ask_jarvis_requested.emit(text)
            self._search.clear()

    # ------------------------------------------------------------------
    # Hero row -- voice orb + quick prompts | schedule + tasks
    # ------------------------------------------------------------------
    def _build_hero_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(16)

        hero = Card()
        hero.setObjectName("heroPanel")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(24, 24, 24, 20)
        hero_layout.setSpacing(10)

        greeting = QLabel("Hello, I'm")
        greeting.setObjectName("heroGreeting")
        hero_layout.addWidget(greeting)
        title = QLabel("JARVIS")
        title.setObjectName("heroTitle")
        hero_layout.addWidget(title)
        subtitle = QLabel("Your AI Assistant")
        subtitle.setObjectName("heroSubtitle")
        hero_layout.addWidget(subtitle)

        orb_row = QHBoxLayout()
        orb_row.addStretch(1)
        self.voice_orb = VoiceOrb()
        self.voice_orb.setFixedSize(160, 160)
        orb_row.addWidget(self.voice_orb)
        orb_row.addStretch(1)
        hero_layout.addLayout(orb_row)

        listening_row = QHBoxLayout()
        listening_row.addStretch(1)
        self._listening_chip = QLabel("● Listening…")
        self._listening_chip.setObjectName("listeningChip")
        listening_row.addWidget(self._listening_chip)
        listening_row.addStretch(1)
        hero_layout.addLayout(listening_row)

        prompts_row = QHBoxLayout()
        prompts_row.setSpacing(8)
        for icon, text in [
            ("gmail", "Summarize my emails"),
            ("calendar", "What's on my schedule?"),
            ("spotify", "Open Spotify"),
            ("task", "Show my tasks"),
        ]:
            btn = PillButton(icon, text)
            btn.clicked.connect(lambda _c=False, t=text: self.ask_jarvis_requested.emit(t))
            prompts_row.addWidget(btn)
        hero_layout.addLayout(prompts_row)

        row.addWidget(hero, 2)

        right_col = QVBoxLayout()
        right_col.setSpacing(16)

        schedule = SectionCard("Today's Schedule", action_text="View Calendar")
        schedule_list = SimpleListPanel()
        schedule_list.add_row("10:00 AM", "Project Meeting")
        schedule_list.add_row("01:00 PM", "Lunch with Sarah")
        schedule_list.add_row("04:00 PM", "Gym Session")
        schedule.body.addWidget(schedule_list)
        add_event = QPushButton("+ Add new event")
        add_event.setObjectName("cardAction")
        schedule.body.addWidget(add_event)
        right_col.addWidget(schedule)

        tasks = SectionCard("Tasks", action_text="View All")
        tasks_list = SimpleListPanel()
        tasks_list.add_row("Complete report", "", "Today", checkable=True)
        tasks_list.add_row("Reply to emails", "", "Today", checkable=True)
        tasks_list.add_row("Workout", "", "Tomorrow", checkable=True)
        tasks_list.add_row("Buy groceries", "", "Tomorrow", checkable=True)
        tasks.body.addWidget(tasks_list)
        right_col.addWidget(tasks)

        row.addLayout(right_col, 1)
        return row

    # ------------------------------------------------------------------
    # Service card row -- Gmail / Spotify / Weather / Finance / Smart Home
    # ------------------------------------------------------------------
    def _build_service_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(14)

        # Each card is a production-quality ServiceWidget (status,
        # summary, recent activity, quick actions, last sync, connection
        # indicator, loading/error states -- Milestone 5 section 2)
        # backed today by a Mock*Provider. Swapping in a real provider
        # later only changes the ``on_refresh`` callback below, never
        # the widget itself.
        gmail_provider = MockGmailProvider()

        async def _load_gmail() -> dict:
            status = await gmail_provider.get_connection_status()
            unread = await gmail_provider.get_unread_count()
            activity = await gmail_provider.get_recent_activity(3)
            return {
                "connected": status.connected,
                "summary": f"{unread} unread · {status.detail}",
                "activity": [(a.icon, a.text, a.timestamp.strftime("%H:%M")) for a in activity],
                "quick_actions": [
                    ("compose", "edit", "Compose"),
                    ("refresh", "refresh", "Refresh"),
                ],
                "last_sync": status.last_sync,
                # Real adapters are M11/M12; until then this card shows
                # illustrative data and says so, rather than rendering a
                # green "connected" light over invented figures.
                "preview": True,
            }

        gmail = ServiceWidget("gmail", "Gmail", on_refresh=_load_gmail)
        row.addWidget(gmail, 1)

        spotify_provider = MockSpotifyProvider()

        async def _load_spotify() -> dict:
            status = await spotify_provider.get_connection_status()
            now_playing = await spotify_provider.get_now_playing()
            activity = await spotify_provider.get_recent_activity(2)
            summary = "Nothing playing"
            if now_playing:
                state = "Playing" if now_playing["is_playing"] else "Paused"
                summary = f"{state}: {now_playing['title']} — {now_playing['artist']}"
            return {
                "connected": status.connected,
                "summary": summary,
                "activity": [(a.icon, a.text, a.timestamp.strftime("%H:%M")) for a in activity],
                "quick_actions": [
                    ("play", "play", ""),
                    ("pause", "pause", ""),
                    ("next", "skip_next", ""),
                ],
                "last_sync": status.last_sync,
                # Real adapters are M11/M12; until then this card shows
                # illustrative data and says so, rather than rendering a
                # green "connected" light over invented figures.
                "preview": True,
            }

        spotify = ServiceWidget("spotify", "Spotify", on_refresh=_load_spotify)
        row.addWidget(spotify, 1)

        weather_provider = MockWeatherProvider()

        async def _load_weather() -> dict:
            status = await weather_provider.get_connection_status()
            current = await weather_provider.get_current("New Delhi, India")
            return {
                "connected": status.connected,
                "summary": f"{current['temp_c']}°C · {current['condition']} · Humidity {current['humidity']}%",
                "activity": [("wind", f"Wind {current['wind_kph']} kph", "now")],
                "quick_actions": [("forecast", "calendar", "5-Day Forecast")],
                "last_sync": status.last_sync,
                # Real adapters are M11/M12; until then this card shows
                # illustrative data and says so, rather than rendering a
                # green "connected" light over invented figures.
                "preview": True,
            }

        weather = ServiceWidget("weather", "Weather", on_refresh=_load_weather)
        row.addWidget(weather, 1)

        finance_provider = MockFinanceProvider()

        async def _load_finance() -> dict:
            status = await finance_provider.get_connection_status()
            summary_data = await finance_provider.get_portfolio_summary()
            activity = await finance_provider.get_recent_activity(2)
            sign = "+" if summary_data["day_change_pct"] >= 0 else ""
            return {
                "connected": status.connected,
                "summary": f"Portfolio ₹{summary_data['total_value']:,.0f} ({sign}{summary_data['day_change_pct']:.2f}%)",
                "activity": [(a.icon, a.text, a.timestamp.strftime("%H:%M")) for a in activity],
                "quick_actions": [("holdings", "chart", "Holdings")],
                "last_sync": status.last_sync,
                # Real adapters are M11/M12; until then this card shows
                # illustrative data and says so, rather than rendering a
                # green "connected" light over invented figures.
                "preview": True,
            }

        finance = ServiceWidget("finance", "Finance Overview", on_refresh=_load_finance)
        row.addWidget(finance, 1)

        smart_home_provider = MockSmartHomeProvider()

        async def _load_smart_home() -> dict:
            status = await smart_home_provider.get_connection_status()
            activity = await smart_home_provider.get_recent_activity(3)
            return {
                "connected": status.connected,
                "summary": status.detail,
                "activity": [(a.icon, a.text, a.timestamp.strftime("%H:%M")) for a in activity],
                "quick_actions": [("devices", "smart_home", "All Devices")],
                "last_sync": status.last_sync,
                # Real adapters are M11/M12; until then this card shows
                # illustrative data and says so, rather than rendering a
                # green "connected" light over invented figures.
                "preview": True,
            }

        smart_home = ServiceWidget("smart_home", "Smart Home", on_refresh=_load_smart_home)
        row.addWidget(smart_home, 1)

        return row

    # ------------------------------------------------------------------
    # Bottom row -- transcript preview | Quick Actions
    # ------------------------------------------------------------------
    def _build_bottom_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(16)

        transcript = SectionCard("Speaking with Jarvis…")
        transcript_list = SimpleListPanel()
        transcript_list.add_row("You · 09:28 AM", "Jarvis, summarize my emails.")
        transcript_list.add_row("Jarvis · 09:28 AM", "You have 3 unread emails. 2 are important.")
        transcript.body.addWidget(transcript_list)
        note_row = QHBoxLayout()
        note_row.setSpacing(6)
        note_row.addWidget(Icon("lock", size=12))
        note = QLabel("This conversation is private and visible only to you.")
        note.setObjectName("rowSubtitle")
        note_row.addWidget(note, 1)
        transcript.body.addLayout(note_row)
        row.addWidget(transcript, 2)

        quick = SectionCard("Quick Actions")
        grid = QGridLayout()
        grid.setSpacing(10)
        actions = [
            ("screenshot", "Take Screenshot", "take screenshot"),
            ("calculator", "Open Calculator", "open calculator"),
            ("search", "Search Anything", None),
            ("note", "Create Note", None),
        ]
        for index, (icon, label, command) in enumerate(actions):
            btn = IconTextButton(icon, label)
            btn.clicked.connect(lambda _c=False, cmd=command: self._on_quick_action(cmd))
            grid.addWidget(btn, index // 2, index % 2)
        quick_widget = QWidget()
        quick_widget.setLayout(grid)
        quick.body.addWidget(quick_widget)
        row.addWidget(quick, 1)

        return row

    def _on_quick_action(self, command: str | None) -> None:
        if command is None:
            self._focus_search()
            return
        if self._automation is not None:
            self.automation_requested.emit(command)
            fire_and_forget(self._automation.run_command(command))
        else:
            self.automation_requested.emit(command)
