"""Productivity domain models -- Milestone 11 Task Group B.

The closed vocabularies Tasks / Calendar / Reminders validate against,
plus :class:`RecurrenceRule` and its bounded expansion.

**Why the vocabularies are frozensets rather than free-form strings.**
Every one of them is filtered on (`list_tasks(status=...)`,
`list_reminders(status=...)`), and a typo'd value would persist happily
and then silently match nothing -- the failure reads as "you have no
tasks" rather than "you asked a nonsense question". Task Group A set
this precedent for workspace/project status; this follows it.

**What "recurring events foundation" means here, precisely.**
:class:`RecurrenceRule` is a stored description of a repeat, and
:meth:`RecurrenceRule.occurrences` expands one deterministically over a
bounded window. That is *expansion*, which a calendar view needs to
render next month, and it is not *scheduling*: nothing fires, nothing
is queued, and no background loop exists. Execution belongs to M7's
Scheduler (Phase 6), which has not shipped -- so this deliberately
stops at "given a rule and a window, which datetimes does it produce".

The rule is a small, explicit subset of RFC 5545 rather than a full
RRULE parser: frequency, interval, and one of count/until. A calendar
that claims RRULE support and then mishandles ``BYSETPOS`` is worse
than one that says up front which four frequencies it does.
"""

from __future__ import annotations

import calendar as _calendar
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

#: Task lifecycle. ``cancelled`` is kept distinct from ``done`` because
#: "finished" and "abandoned" are different answers to "why is this off
#: my list", and any later reporting will care which.
TASK_STATUSES: frozenset[str] = frozenset({"todo", "in_progress", "done", "cancelled"})

#: Ordered low -> urgent. The ordering is data, not convention, so
#: sorting does not depend on each caller remembering it.
TASK_PRIORITIES: tuple[str, ...] = ("low", "normal", "high", "urgent")
TASK_PRIORITY_RANK: dict[str, int] = {name: rank for rank, name in enumerate(TASK_PRIORITIES)}

#: A reminder's own state. ``sent`` is reachable only once something
#: delivers it -- nothing in this task group does, by design.
REMINDER_STATUSES: frozenset[str] = frozenset({"pending", "sent", "dismissed", "cancelled"})

#: Event categories. Deliberately small and generic: a category is a
#: colour-and-filter hint, not a taxonomy, and an installation that
#: wants richer grouping has calendars for that.
EVENT_CATEGORIES: frozenset[str] = frozenset(
    {"general", "meeting", "focus", "personal", "travel", "reminder"}
)

#: The four frequencies this build expands. See the module docstring for
#: why the list is short rather than "RRULE".
RECURRENCE_FREQUENCIES: frozenset[str] = frozenset({"daily", "weekly", "monthly", "yearly"})

#: A hard ceiling on how many occurrences one expansion may produce, so
#: a rule with no ``count`` and no ``until`` cannot be asked for an
#: unbounded list by a caller that forgot to pass a window.
MAX_OCCURRENCES = 366


@dataclass(frozen=True, slots=True)
class RecurrenceRule:
    """How an event repeats. ``None`` frequency means "does not"."""

    frequency: str = ""
    interval: int = 1
    count: int | None = None
    until: datetime | None = None

    @property
    def is_recurring(self) -> bool:
        return bool(self.frequency)

    def validate(self) -> None:
        """Raises :class:`ValueError` on a rule that could not expand.
        Called at construction time by the service, so a malformed rule
        fails when it is written rather than when a view tries to render
        six months of it."""
        if not self.frequency:
            return
        if self.frequency not in RECURRENCE_FREQUENCIES:
            raise ValueError(
                f"Unknown recurrence frequency {self.frequency!r}; "
                f"allowed: {sorted(RECURRENCE_FREQUENCIES)}."
            )
        if self.interval < 1:
            raise ValueError("Recurrence interval must be at least 1.")
        if self.count is not None and self.count < 1:
            raise ValueError("Recurrence count must be at least 1 when given.")
        if self.count is not None and self.until is not None:
            # RFC 5545 forbids both for the same reason: they can
            # disagree, and then the answer depends on which one the
            # implementation happens to check first.
            raise ValueError("A recurrence may set count or until, not both.")

    def occurrences(
        self, start: datetime, *, window_end: datetime | None = None, limit: int = MAX_OCCURRENCES
    ) -> list[datetime]:
        """Every occurrence from *start*, bounded by whichever of
        ``count`` / ``until`` / *window_end* / *limit* runs out first.

        Pure: no I/O, no clock read, no state. A non-recurring rule
        yields exactly ``[start]``, so a caller never has to branch on
        ``is_recurring`` before rendering.
        """
        if not self.is_recurring:
            return [start]

        ceiling = min(limit, MAX_OCCURRENCES) if limit > 0 else MAX_OCCURRENCES
        if self.count is not None:
            ceiling = min(ceiling, self.count)

        results: list[datetime] = []
        current = start
        for index in range(ceiling):
            if self.until is not None and _aware(current) > _aware(self.until):
                break
            if window_end is not None and _aware(current) > _aware(window_end):
                break
            results.append(current)
            current = self._advance(start, index + 1)
        return results

    def _advance(self, start: datetime, step: int) -> datetime:
        delta = self.interval * step
        if self.frequency == "daily":
            return start + timedelta(days=delta)
        if self.frequency == "weekly":
            return start + timedelta(weeks=delta)
        if self.frequency == "monthly":
            return _add_months(start, delta)
        return _add_months(start, delta * 12)

    def as_dict(self) -> dict[str, Any]:
        return {
            "frequency": self.frequency,
            "interval": self.interval,
            "count": self.count,
            "until": self.until.isoformat() if self.until else None,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> RecurrenceRule:
        """Tolerant, like ``WorkspaceSettings.from_dict``: a malformed
        stored rule degrades to "does not repeat" rather than making the
        event unreadable."""
        payload = payload or {}
        until_raw = payload.get("until")
        until: datetime | None = None
        if isinstance(until_raw, str) and until_raw:
            try:
                until = datetime.fromisoformat(until_raw)
            except ValueError:
                until = None
        try:
            interval = int(payload.get("interval") or 1)
        except (TypeError, ValueError):
            interval = 1
        count_raw = payload.get("count")
        try:
            count = int(count_raw) if count_raw is not None else None
        except (TypeError, ValueError):
            count = None
        return cls(
            frequency=str(payload.get("frequency") or ""),
            interval=interval,
            count=count,
            until=until,
        )


def normalize_tags(tags: list[str] | tuple[str, ...] | None) -> list[str]:
    """Lower-cased, stripped, de-duplicated, order preserved.

    Normalizing on write rather than on read means a tag filter is a
    plain equality check, and ``["Work", "work "]`` cannot become two
    tags that render identically.
    """
    seen: list[str] = []
    for raw in tags or ():
        tag = str(raw).strip().lower()
        if tag and tag not in seen:
            seen.append(tag)
    return seen


def _add_months(moment: datetime, months: int) -> datetime:
    """Month arithmetic that clamps rather than overflowing: the 31st
    plus one month is the 30th, not the 1st of the month after. A
    monthly event set on the 31st should land in every month, which is
    what a user means by "monthly"."""
    month_index = moment.month - 1 + months
    year = moment.year + month_index // 12
    month = month_index % 12 + 1
    day = min(moment.day, _calendar.monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)


def _aware(moment: datetime) -> datetime:
    """SQLite round-trips a stored aware datetime back as naive -- a
    dialect quirk ``IntelligenceService`` already documents. Everything
    stored here is UTC by convention, so a naive value means naive UTC;
    normalizing before comparison avoids the offset-naive/offset-aware
    TypeError regardless of which side came from the database."""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)
