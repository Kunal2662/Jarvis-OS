"""Personalized Greeting Engine (JARVIS Personalized Greeting System).

Replaces the static "Good Morning, {name}" header with a dynamically
generated, non-repetitive, context-aware greeting -- spoken at startup
and shown on the Home dashboard.

Two-tier generation:

1. **Primary**: build a system prompt encoding JARVIS's personality
   (calm, confident, supportive, observant, professional, human-like --
   never robotic or overly enthusiastic) plus every gathered context
   source, and ask the real ``ILLMProvider`` for one short greeting
   line. This is a genuine LLM call, not a mock -- it reuses whichever
   provider (Ollama/OpenAI/...) is already wired for chat.
2. **Fallback**: if the LLM call fails or is unavailable (offline
   Ollama, no API key, ...), fall back to a curated, randomized
   template (see ``features/greeting/fallback.py``) so the engine never
   goes silent.

Recent greetings are persisted to ``<data_dir>/greeting_history.json``
(best-effort; failure to read/write never breaks startup) so "never
repeat the exact same greeting frequently" holds *across restarts*, not
just within one running session.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING

from jarvis.core.logging.logger import get_logger
from jarvis.core.types import ChatMessage
from jarvis.domain.greeting.models import GreetingContext
from jarvis.features.greeting.fallback import fallback_greeting
from jarvis.features.greeting.mock_context import (
    mock_active_tasks,
    mock_recent_achievement,
    mock_upcoming_events,
)

if TYPE_CHECKING:
    from jarvis.core.config.settings import Settings
    from jarvis.core.interfaces.llm_provider import ILLMProvider
    from jarvis.services.conversation_service import ConversationService
    from jarvis.services.memory_service import MemoryService

_logger = get_logger("jarvis.services.greeting")

_MAX_HISTORY = 20
_RECENT_AVOID_COUNT = 5  # how many past greetings get shown to the LLM to avoid repeating

_SYSTEM_PROMPT = """You are JARVIS's greeting voice. Generate exactly ONE short spoken \
greeting for the user, and nothing else -- no preamble, no quotation marks, no explanation.

Personality: intelligent, calm, confident, supportive, observant, professional, human-like. \
Never robotic, never overly enthusiastic, never scripted-sounding.

Rules:
- Maximum one or two sentences, speakable in 8-12 seconds.
- Combine multiple pieces of context naturally when it makes sense; don't force all of them in.
- Never use a fixed template. Vary sentence structure every time.
- Do not repeat, or closely paraphrase, any of the recent greetings you are shown below.
- Address the user by name at most once.
- Output only the greeting text itself."""


class GreetingService:
    def __init__(
        self,
        settings: Settings,
        llm_provider: ILLMProvider | None = None,
        *,
        memory_service: MemoryService | None = None,
        conversation_service: ConversationService | None = None,
    ) -> None:
        self._settings = settings
        self._llm = llm_provider
        self._memory = memory_service
        self._conversations = conversation_service
        self._history_path = settings.resolved_data_dir / "greeting_history.json"
        self.history: list[str] = self._load_history()

    # ------------------------------------------------------------------
    # Context gathering -- every source is best-effort; a failure in any
    # one of them never prevents a greeting from being generated.
    # ------------------------------------------------------------------
    async def build_context(
        self, user_name: str, *, current_workspace: str = "home", now: datetime | None = None
    ) -> GreetingContext:
        now = now or datetime.now()

        system_status = "nominal"
        if self._llm is not None:
            try:
                status = await self._llm.health()
                system_status = "nominal" if status.healthy else "degraded"
            except Exception:
                system_status = "degraded"

        battery_percent: int | None = None
        battery_charging: bool | None = None
        try:
            import psutil

            battery = psutil.sensors_battery()
            if battery is not None:
                battery_percent = int(battery.percent)
                battery_charging = bool(battery.power_plugged)
        except Exception:
            pass

        weather_summary = ""
        now_playing = ""
        smart_home_summary = ""
        try:
            from jarvis.features.integrations.mocks import MockWeatherProvider

            weather = await MockWeatherProvider().get_current("your location")
            weather_summary = f"{weather['temp_c']}\u00b0C and {weather['condition'].lower()}"
        except Exception:
            pass
        try:
            from jarvis.features.integrations.mocks import MockSpotifyProvider

            track = await MockSpotifyProvider().get_now_playing()
            if track and track.get("is_playing"):
                now_playing = f"{track['title']} by {track['artist']}"
        except Exception:
            pass
        try:
            from jarvis.features.integrations.mocks import MockSmartHomeProvider

            status = await MockSmartHomeProvider().get_connection_status()
            smart_home_summary = status.detail
        except Exception:
            pass

        recent_conversation_summary = ""
        if self._conversations is not None:
            try:
                conversations = await self._conversations.list()
                if conversations:
                    recent_conversation_summary = f'last talked about "{conversations[0].title}"'
            except Exception:
                pass

        remembered_notes: list[str] = []
        if self._memory is not None:
            try:
                records = await self._memory.recall("user goals preferences projects", top_k=3)
                remembered_notes = [r.content for r in (records or []) if hasattr(r, "content")]
            except Exception:
                pass

        return GreetingContext(
            user_name=user_name,
            now=now,
            battery_percent=battery_percent,
            battery_charging=battery_charging,
            system_status=system_status,
            weather_summary=weather_summary,
            now_playing=now_playing,
            smart_home_summary=smart_home_summary,
            current_workspace=current_workspace,
            active_tasks=mock_active_tasks(now),
            upcoming_events=mock_upcoming_events(now),
            recent_achievements=[mock_recent_achievement()],
            current_project=self._settings.app_name,
            current_milestone=f"v{self._settings.app_version}",
            recent_conversation_summary=recent_conversation_summary,
            remembered_notes=remembered_notes,
        )

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------
    async def generate(self, context: GreetingContext) -> str:
        text = await self._generate_with_llm(context)
        if not text:
            text = fallback_greeting(context, avoid=self.history[-_RECENT_AVOID_COUNT:])
        self._remember(text)
        return text

    async def _generate_with_llm(self, context: GreetingContext) -> str | None:
        if self._llm is None:
            return None
        try:
            messages = [
                ChatMessage(role="system", content=_SYSTEM_PROMPT),
                ChatMessage(role="user", content=self._describe_context(context)),
            ]
            text = await self._llm.complete(messages, temperature=0.9, max_tokens=80)
        except Exception as err:
            _logger.warning("Greeting LLM generation failed, using fallback: {}", err)
            return None

        if not text or not isinstance(text, str):
            return None
        text = text.strip().strip('"').strip()
        if not text:
            return None
        if len(text) > 300:
            text = text[:300].rsplit(" ", 1)[0] + "…"
        # Avoid a greeting that's identical to a recent one even if the
        # model didn't follow the "don't repeat" instruction.
        if text in self.history[-_RECENT_AVOID_COUNT:]:
            return None
        return text

    def _describe_context(self, context: GreetingContext) -> str:
        lines = [
            f"User: {context.user_name}",
            f"Time: {context.now.strftime('%A, %B %d, %I:%M %p')} ({context.time_of_day.replace('_', ' ')})",
            f"System status: {context.system_status}",
        ]
        if context.weather_summary:
            lines.append(f"Weather: {context.weather_summary}")
        if context.battery_percent is not None:
            state = "charging" if context.battery_charging else "on battery"
            lines.append(f"Battery: {context.battery_percent}% ({state})")
        if context.now_playing:
            lines.append(f"Currently playing: {context.now_playing}")
        if context.smart_home_summary:
            lines.append(f"Smart home: {context.smart_home_summary}")
        if context.active_tasks:
            lines.append(f"Active tasks: {', '.join(context.active_tasks)}")
        if context.upcoming_events:
            lines.append(f"Upcoming today: {', '.join(context.upcoming_events)}")
        if context.recent_achievements:
            lines.append(f"Recently: {', '.join(context.recent_achievements)}")
        if context.current_project:
            lines.append(
                f"Current project: {context.current_project} ({context.current_milestone})"
            )
        if context.recent_conversation_summary:
            lines.append(f"Continuity: {context.recent_conversation_summary}")
        if context.remembered_notes:
            lines.append(f"Remembered: {'; '.join(context.remembered_notes)}")
        if self.history:
            recent = self.history[-_RECENT_AVOID_COUNT:]
            lines.append("Recent greetings (do not repeat these): " + " | ".join(recent))
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # History persistence
    # ------------------------------------------------------------------
    def _remember(self, greeting: str) -> None:
        self.history.append(greeting)
        self.history = self.history[-_MAX_HISTORY:]
        self._save_history()

    def _load_history(self) -> list[str]:
        try:
            if self._history_path.is_file():
                data = json.loads(self._history_path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return [str(g) for g in data][-_MAX_HISTORY:]
        except Exception as err:
            _logger.warning("Could not load greeting history: {}", err)
        return []

    def _save_history(self) -> None:
        try:
            self._history_path.parent.mkdir(parents=True, exist_ok=True)
            self._history_path.write_text(
                json.dumps(self.history, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as err:
            _logger.warning("Could not persist greeting history: {}", err)
