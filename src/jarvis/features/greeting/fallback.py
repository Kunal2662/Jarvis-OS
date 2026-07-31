"""Fallback greetings for the Personalized Greeting Engine.

Used only when the LLM provider is unavailable/fails -- the engine
should never go silent just because the LLM call failed. These mirror
the example categories from the brief (Project Work, Productivity,
Late Night, Weekend, Weather, System) and are picked with light
randomization + recent-history avoidance so they don't feel like one
fixed template either, even without a model in the loop.
"""

from __future__ import annotations

import random

from jarvis.domain.greeting.models import GreetingContext

_PROJECT_WORK = [
    "Good {time_greeting}, {name}. Ready to continue building {project}?",
    "Welcome back, {name}. I've restored your last {project} workspace.",
    "Your development environment is ready, {name}.",
    "You made great progress last time, {name}. Let's continue.",
]
_LATE_NIGHT = [
    "Looks like another late-night session, {name}.",
    "I've kept everything ready for you, {name}.",
    "Still at it, {name}? Let's continue.",
]
_WEEKEND = [
    "No meetings today, {name}. A perfect day to build something.",
    "Relaxed schedule today, {name} -- plenty of time for new ideas.",
]
_PRODUCTIVITY = [
    "You have {task_count} things on your plate today, {name}.",
    "Everything is ready, {name}. Which should we tackle first?",
    "Your schedule looks manageable today, {name}.",
]
_SYSTEM_DEGRADED = [
    "Good {time_greeting}, {name}. One or two things need attention when you have a moment.",
]


def fallback_greeting(context: GreetingContext, *, avoid: list[str] | None = None) -> str:
    avoid = avoid or []
    time_greeting = {
        "morning": "morning",
        "afternoon": "afternoon",
        "evening": "evening",
        "late_night": "evening",
    }[context.time_of_day]

    if context.system_status != "nominal":
        pool = _SYSTEM_DEGRADED
    elif context.is_late_night:
        pool = _LATE_NIGHT
    elif context.is_weekend:
        pool = _WEEKEND
    elif context.active_tasks:
        pool = _PROJECT_WORK + _PRODUCTIVITY
    else:
        pool = _PRODUCTIVITY

    candidates = [t for t in pool if t not in avoid] or pool
    template = random.choice(candidates)
    return template.format(
        name=context.user_name,
        time_greeting=time_greeting,
        project=context.current_project or "your project",
        task_count=len(context.active_tasks) or "a few",
    )
