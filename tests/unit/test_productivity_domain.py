"""Productivity domain-model tests -- Milestone 11 Task Group B.

Pure functions: recurrence expansion and tag normalization. No database
and no I/O, which is exactly the property that makes expansion safe to
call from a render path.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from jarvis.domain.productivity.models import (
    MAX_OCCURRENCES,
    RecurrenceRule,
    normalize_tags,
)

_START = datetime(2026, 1, 15, 9, 0, tzinfo=UTC)


# --- Tags -----------------------------------------------------------------------


def test_tags_are_lowercased_deduplicated_and_ordered() -> None:
    """Normalizing on write means a tag filter is a plain equality
    check, and ``["Work", "work "]`` cannot become two tags that render
    identically."""
    assert normalize_tags(["Work", "work ", "HOME", "  ", "home", ""]) == ["work", "home"]


def test_no_tags_is_an_empty_list_not_none() -> None:
    assert normalize_tags(None) == []


# --- Recurrence: the non-recurring case -----------------------------------------


def test_a_non_recurring_rule_yields_exactly_the_start() -> None:
    """So a caller never has to branch on ``is_recurring`` before
    rendering."""
    assert RecurrenceRule().occurrences(_START) == [_START]
    assert RecurrenceRule().is_recurring is False


# --- Recurrence: frequencies ----------------------------------------------------


@pytest.mark.parametrize(
    ("frequency", "expected_second"),
    [
        ("daily", datetime(2026, 1, 16, 9, 0, tzinfo=UTC)),
        ("weekly", datetime(2026, 1, 22, 9, 0, tzinfo=UTC)),
        ("monthly", datetime(2026, 2, 15, 9, 0, tzinfo=UTC)),
        ("yearly", datetime(2027, 1, 15, 9, 0, tzinfo=UTC)),
    ],
)
def test_each_frequency_advances_correctly(frequency: str, expected_second: datetime) -> None:
    rule = RecurrenceRule(frequency=frequency, count=2)

    assert rule.occurrences(_START) == [_START, expected_second]


def test_interval_multiplies_the_step() -> None:
    rule = RecurrenceRule(frequency="daily", interval=3, count=3)

    assert [d.day for d in rule.occurrences(_START)] == [15, 18, 21]


def test_monthly_from_the_31st_clamps_rather_than_overflowing() -> None:
    """A monthly event set on the 31st should land in every month --
    which is what a user means by "monthly". Naive month arithmetic
    would skip February entirely or land on March 3rd."""
    rule = RecurrenceRule(frequency="monthly", count=4)
    start = datetime(2026, 1, 31, 9, 0, tzinfo=UTC)

    assert [d.date().isoformat() for d in rule.occurrences(start)] == [
        "2026-01-31",
        "2026-02-28",
        "2026-03-31",
        "2026-04-30",
    ]


def test_yearly_on_a_leap_day_clamps() -> None:
    rule = RecurrenceRule(frequency="yearly", count=2)
    start = datetime(2024, 2, 29, 9, 0, tzinfo=UTC)

    assert [d.date().isoformat() for d in rule.occurrences(start)] == [
        "2024-02-29",
        "2025-02-28",
    ]


# --- Recurrence: bounds ---------------------------------------------------------


def test_count_bounds_the_expansion() -> None:
    assert len(RecurrenceRule(frequency="daily", count=3).occurrences(_START)) == 3


def test_until_bounds_the_expansion() -> None:
    rule = RecurrenceRule(frequency="daily", until=_START + timedelta(days=2))

    assert len(rule.occurrences(_START)) == 3  # start, +1, +2


def test_window_end_bounds_the_expansion() -> None:
    rule = RecurrenceRule(frequency="daily", count=100)

    result = rule.occurrences(_START, window_end=_START + timedelta(days=4))

    assert len(result) == 5


def test_an_unbounded_rule_still_cannot_run_away() -> None:
    """No count, no until, no window -- the hard ceiling is what stops a
    caller that forgot to pass one from getting an unbounded list."""
    result = RecurrenceRule(frequency="daily").occurrences(_START)

    assert len(result) == MAX_OCCURRENCES


def test_naive_and_aware_bounds_compare_without_raising() -> None:
    """SQLite round-trips a stored aware datetime back as naive. Both
    sides are normalized before comparison, so an ``until`` read from
    the database does not blow up against an aware start."""
    naive_until = datetime(2026, 1, 17, 9, 0)
    rule = RecurrenceRule(frequency="daily", until=naive_until)

    assert len(rule.occurrences(_START)) == 3


# --- Recurrence: validation -----------------------------------------------------


def test_a_valid_rule_validates_silently() -> None:
    RecurrenceRule(frequency="weekly", interval=2, count=5).validate()
    RecurrenceRule().validate()  # non-recurring is always valid


@pytest.mark.parametrize(
    ("rule", "message"),
    [
        (RecurrenceRule(frequency="hourly"), "Unknown recurrence frequency"),
        (RecurrenceRule(frequency="daily", interval=0), "interval must be at least 1"),
        (RecurrenceRule(frequency="daily", count=0), "count must be at least 1"),
        (
            RecurrenceRule(frequency="daily", count=2, until=_START),
            "count or until, not both",
        ),
    ],
)
def test_invalid_rules_are_rejected(rule: RecurrenceRule, message: str) -> None:
    """Validated when written rather than when a view tries to render
    six months of it."""
    with pytest.raises(ValueError, match=message):
        rule.validate()


# --- Recurrence: serialization --------------------------------------------------


def test_a_rule_round_trips_through_its_dict() -> None:
    rule = RecurrenceRule(frequency="weekly", interval=2, until=_START)

    assert RecurrenceRule.from_dict(rule.as_dict()) == rule


def test_a_malformed_stored_rule_degrades_to_non_recurring() -> None:
    """One bad write must not make an event unreadable -- the same
    posture ``WorkspaceSettings.from_dict`` takes."""
    rule = RecurrenceRule.from_dict(
        {"frequency": "daily", "interval": "not-a-number", "until": "not-a-date"}
    )

    assert rule.frequency == "daily"
    assert rule.interval == 1
    assert rule.until is None


def test_from_dict_tolerates_none_and_junk() -> None:
    assert RecurrenceRule.from_dict(None).is_recurring is False
    assert RecurrenceRule.from_dict({}).is_recurring is False
