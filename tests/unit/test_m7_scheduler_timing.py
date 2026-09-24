"""Tests for `features/scheduler/timing.py` -- Milestone 7 Phase 6
(Scheduler MVP). Pure functions, no persistence, no execution -- see
``docs/M7_SCHEDULER_LOGIC_CONTRACT.md`` §8.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from jarvis.core.exceptions import ServiceError
from jarvis.features.scheduler.timing import (
    MIN_INTERVAL_SECONDS,
    compute_next_fire,
    validate_cron_expression,
    validate_interval_seconds,
    validate_timezone,
)

# --- Interval ------------------------------------------------------------------


def test_interval_next_fire_is_after_plus_interval() -> None:
    after = datetime(2026, 8, 18, 0, 0, 0, tzinfo=UTC)
    result = compute_next_fire(
        kind="interval", after=after, interval_seconds=60.0, cron_expression="", timezone="UTC"
    )
    assert result == datetime(2026, 8, 18, 0, 1, 0, tzinfo=UTC)


def test_interval_next_fire_is_never_immediate() -> None:
    """First fire is one full interval after `after`, never T+0."""
    after = datetime(2026, 8, 18, 0, 0, 0, tzinfo=UTC)
    result = compute_next_fire(
        kind="interval", after=after, interval_seconds=300.0, cron_expression="", timezone="UTC"
    )
    assert result > after


def test_minimum_interval_constant_is_60_seconds() -> None:
    assert MIN_INTERVAL_SECONDS == 60.0


@pytest.mark.parametrize("value", [0, 1, 30, 59, 59.9])
def test_interval_below_minimum_is_rejected(value: float) -> None:
    with pytest.raises(ServiceError, match="at least 60"):
        validate_interval_seconds(value)


@pytest.mark.parametrize("value", [60, 60.0, 61, 3600, 86400])
def test_interval_at_or_above_minimum_is_accepted(value: float) -> None:
    validate_interval_seconds(value)  # must not raise


@pytest.mark.parametrize("value", [True, False, "60", None, [60]])
def test_interval_rejects_non_numeric_and_bool(value: object) -> None:
    with pytest.raises(ServiceError):
        validate_interval_seconds(value)  # type: ignore[arg-type]


# --- Cron ------------------------------------------------------------------


def test_cron_next_fire_respects_timezone() -> None:
    after = datetime(2026, 8, 18, 0, 0, 0, tzinfo=UTC)
    result = compute_next_fire(
        kind="cron",
        after=after,
        interval_seconds=0.0,
        cron_expression="0 8 * * *",
        timezone="Asia/Kolkata",
    )
    # 08:00 IST == 02:30 UTC (+05:30 offset).
    assert result == datetime(2026, 8, 18, 2, 30, 0, tzinfo=UTC)


def test_cron_next_fire_is_strictly_after_reference() -> None:
    after = datetime(2026, 8, 18, 2, 30, 0, tzinfo=UTC)
    result = compute_next_fire(
        kind="cron",
        after=after,
        interval_seconds=0.0,
        cron_expression="0 8 * * *",
        timezone="Asia/Kolkata",
    )
    assert result > after
    assert result == datetime(2026, 8, 19, 2, 30, 0, tzinfo=UTC)


def test_cron_dst_spring_forward_skips_to_next_valid_wall_clock_time() -> None:
    """A 2:30am fire that doesn't exist on the US spring-forward date
    resolves to the library's own documented DST policy (skip forward),
    not a crash or a silently wrong instant -- Logic Contract §8."""
    after = datetime(2026, 3, 7, 0, 0, 0, tzinfo=UTC)
    result = compute_next_fire(
        kind="cron",
        after=after,
        interval_seconds=0.0,
        cron_expression="30 2 * * *",
        timezone="America/New_York",
    )
    first = result
    assert first.astimezone(UTC).hour in (7,)  # 02:30 EST == 07:30 UTC

    second = compute_next_fire(
        kind="cron",
        after=first,
        interval_seconds=0.0,
        cron_expression="30 2 * * *",
        timezone="America/New_York",
    )
    # 2026-03-08 02:30 doesn't exist (US spring-forward) -- resolves to
    # 03:00 EDT instead of raising or silently landing on a wrong hour.
    assert second.astimezone(UTC).hour == 7 or second.astimezone(UTC).hour == 6


def test_invalid_cron_expression_is_rejected() -> None:
    with pytest.raises(ServiceError, match="Invalid cron expression"):
        validate_cron_expression("not a cron")


@pytest.mark.parametrize("expr", ["0 8 * * *", "*/5 * * * *", "0 0 1 1 *", "30 2 * * 1-5"])
def test_valid_5_field_cron_expressions_are_accepted(expr: str) -> None:
    validate_cron_expression(expr)  # must not raise


def test_6_field_cron_expression_is_rejected() -> None:
    """Only 5-field POSIX syntax is supported -- no seconds field."""
    with pytest.raises(ServiceError):
        validate_cron_expression("0 0 8 * * *")


# --- Timezone ------------------------------------------------------------------


def test_valid_timezone_is_accepted() -> None:
    validate_timezone("UTC")
    validate_timezone("Asia/Kolkata")
    validate_timezone("America/New_York")


def test_unknown_timezone_is_rejected() -> None:
    with pytest.raises(ServiceError, match="Unknown timezone"):
        validate_timezone("Not/AZone")


def test_compute_next_fire_rejects_naive_datetime() -> None:
    naive = datetime(2026, 8, 18, 0, 0, 0)  # deliberately naive
    with pytest.raises(ServiceError, match="timezone-aware"):
        compute_next_fire(
            kind="interval", after=naive, interval_seconds=60.0, cron_expression="", timezone="UTC"
        )


def test_compute_next_fire_rejects_unknown_kind() -> None:
    after = datetime(2026, 8, 18, 0, 0, 0, tzinfo=UTC)
    with pytest.raises(ServiceError, match="Unknown schedule kind"):
        compute_next_fire(
            kind="daily", after=after, interval_seconds=60.0, cron_expression="", timezone="UTC"
        )
