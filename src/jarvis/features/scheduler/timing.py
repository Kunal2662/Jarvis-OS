"""Interval/cron next-fire computation and validation -- Milestone 7
Phase 6 (Scheduler MVP). Pure functions, no persistence, no execution --
mirrors ``features/automation/parser.py``'s own "no I/O" discipline.

See ``docs/M7_SCHEDULER_LOGIC_CONTRACT.md`` §8 for the exact semantics
this module implements: 5-field POSIX cron only, timezone-aware, DST
policy delegated entirely to ``croniter`` rather than hand-rolled, 60s
minimum interval, first fire is one full interval/cron period after
creation (never an immediate T+0 fire).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import CroniterBadCronError, croniter

from jarvis.core.exceptions import ServiceError
from jarvis.domain.workflow.models import ScheduleKind

#: Logic Contract §8: finer-grained than this risks imprecision against
#: SchedulerSettings.poll_interval_seconds's own 30s default.
MIN_INTERVAL_SECONDS = 60.0


def _ensure_aware(value: datetime, *, param: str) -> datetime:
    if value.tzinfo is None:
        raise ServiceError(f"{param} must be a timezone-aware datetime, got a naive one.")
    return value


def validate_timezone(name: str) -> None:
    """Raises ``ServiceError`` if *name* is not a resolvable IANA zone."""
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, KeyError) as err:
        raise ServiceError(f"Unknown timezone {name!r}.") from err


def validate_interval_seconds(value: float) -> None:
    """Raises ``ServiceError`` for anything below the 60s MVP floor, or
    a non-numeric/boolean value (``bool`` is an ``int`` subclass in
    Python, so it is rejected explicitly -- the same guard this
    codebase's own ``_validate_duration``-style helpers already use)."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ServiceError(f"interval_seconds must be a number, got {value!r}.")
    if value < MIN_INTERVAL_SECONDS:
        raise ServiceError(
            f"interval_seconds must be at least {MIN_INTERVAL_SECONDS:.0f} seconds, "
            f"got {value!r}."
        )


def validate_cron_expression(expression: str) -> None:
    """Raises ``ServiceError`` for anything that is not a valid 5-field
    POSIX cron expression -- rejected at creation, never persisted
    uncomputable (Logic Contract §8). ``croniter.is_valid`` alone is
    insufficient here -- it also accepts croniter's own 6/7-field
    seconds/year extensions, which the Logic Contract explicitly does
    not support ("do not implement extended cron syntax beyond the
    contract"), so the field count is checked explicitly first."""
    if len(expression.split()) != 5 or not croniter.is_valid(expression):
        raise ServiceError(
            f"Invalid cron expression: {expression!r}. Expected 5-field POSIX cron syntax "
            "(minute hour day-of-month month day-of-week)."
        )


def compute_next_fire(
    *,
    kind: str,
    after: datetime,
    interval_seconds: float,
    cron_expression: str,
    timezone: str,
) -> datetime:
    """The next fire time strictly after *after*, as a timezone-aware
    UTC datetime. *after* is either a schedule's own ``created_at``
    (first fire) or its ``last_fired_at`` (every fire since)."""
    after = _ensure_aware(after, param="after")

    if kind == ScheduleKind.INTERVAL.value:
        return after.astimezone(UTC) + timedelta(seconds=interval_seconds)

    if kind == ScheduleKind.CRON.value:
        try:
            tz = ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError, KeyError) as err:
            raise ServiceError(f"Unknown timezone {timezone!r}.") from err
        try:
            iterator = croniter(cron_expression, after.astimezone(tz))
            next_local = iterator.get_next(datetime)
        except (CroniterBadCronError, ValueError) as err:
            raise ServiceError(f"Invalid cron expression: {cron_expression!r}.") from err
        return next_local.astimezone(UTC)

    raise ServiceError(f"Unknown schedule kind: {kind!r}. Expected 'interval' or 'cron'.")
