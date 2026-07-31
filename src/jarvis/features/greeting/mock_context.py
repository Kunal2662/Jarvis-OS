"""Mock work-context data for the Personalized Greeting Engine.

Calendar, task-tracking, and "recent achievements" have no real backend
in this codebase yet (same honest-mock convention as the Milestone 5
workspaces) -- this returns realistic, varied mock data rather than a
fixed template, so the greeting has genuine work context to reference
without a real project-management integration existing.
"""

from __future__ import annotations

import random
from datetime import datetime

_WEEKDAY_TASKS = [
    "Finish the quarterly report",
    "Review the pending pull requests",
    "Reply to the unread emails",
    "Prep slides for the afternoon sync",
    "Follow up with the design team",
]
_WEEKEND_TASKS = [
    "Nothing urgent -- a clear day ahead",
]
_UPCOMING_EVENTS_WEEKDAY = [
    "a 10 AM project review",
    "a 1 PM lunch catch-up",
    "a 4 PM 1:1",
]
_UPCOMING_EVENTS_WEEKEND = []
_ACHIEVEMENTS = [
    "shipped the Milestone 5 completion pass",
    "cleared the backlog down to zero open bugs",
    "got the update pipeline's rollback path fully tested",
    "wrapped up the last refactor without a single regression",
]


def mock_active_tasks(now: datetime) -> list[str]:
    pool = _WEEKEND_TASKS if now.weekday() >= 5 else _WEEKDAY_TASKS
    if pool is _WEEKEND_TASKS:
        return list(pool)
    return random.sample(pool, k=min(2, len(pool)))


def mock_upcoming_events(now: datetime) -> list[str]:
    pool = _UPCOMING_EVENTS_WEEKEND if now.weekday() >= 5 else _UPCOMING_EVENTS_WEEKDAY
    return list(pool)


def mock_recent_achievement() -> str:
    return random.choice(_ACHIEVEMENTS)
