"""Personalized Greeting Engine -- domain model.

``GreetingContext`` aggregates every context source the greeting brief
lists, gathered best-effort by ``GreetingService.build_context()``.
Every field has a safe default so a missing/unavailable subsystem
(no battery, no smart-home hub, memory recall failed, ...) never
prevents a greeting from being generated -- it just means less context
to work with.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class GreetingContext:
    user_name: str
    now: datetime

    # System / device state
    battery_percent: int | None = None
    battery_charging: bool | None = None
    system_status: str = "nominal"  # nominal | degraded | down

    # Ambient services (mock where no real backend exists yet)
    weather_summary: str = ""
    now_playing: str = ""
    smart_home_summary: str = ""

    # Work context
    current_workspace: str = "home"
    active_tasks: list[str] = field(default_factory=list)
    upcoming_events: list[str] = field(default_factory=list)
    recent_achievements: list[str] = field(default_factory=list)
    current_project: str = ""
    current_milestone: str = ""

    # Memory / continuity
    recent_conversation_summary: str = ""
    remembered_notes: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    @property
    def hour(self) -> int:
        return self.now.hour

    @property
    def is_weekend(self) -> bool:
        return self.now.weekday() >= 5  # Saturday=5, Sunday=6

    @property
    def is_late_night(self) -> bool:
        return self.hour >= 23 or self.hour < 5

    @property
    def time_of_day(self) -> str:
        if self.is_late_night:
            return "late_night"
        if self.hour < 12:
            return "morning"
        if self.hour < 18:
            return "afternoon"
        return "evening"
