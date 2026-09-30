"""`CronSpec.next_after` against a naive minute-by-minute reference, across leap days,
short months, day-and-weekday combinations, year boundaries and expressions with no match
in the horizon. The jump-based rewrite (a separate commit) must agree with this reference
on every case here; the reference is written independently of the implementation."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from my_agent_crew.scheduler.cron import CronSpec

EXPRESSIONS = [
    "* * * * *",
    "*/5 * * * *",
    "*/15 * * * *",
    "0 * * * *",
    "30 * * * *",
    "0 7 * * *",
    "0 7,19 * * *",
    "30 23,0 * * *",
    "0 0 1 * *",
    "0 0 15 * *",
    "0 0 * * 0",
    "0 0 * * 1-5",
    "0 9 3 5 *",  # a yearly cron: the slow case next_after must jump through
    "0 0 29 2 *",  # only fires on a leap year
    "0 0 30 2 *",  # never occurs: no February has 30 days
    "0 0 31 4 *",  # never occurs: April has 30 days
    "0 0 31 * *",  # only the months with 31 days
    "59 23 * * *",
    "0 0 1 1 *",
    "0 0 25 12 *",
    "*/7 3,15 * * *",
    "0 6-8 * * *",
    "0 0 29 2 1",  # leap day AND a specific weekday: both must hold
    "15,45 * * * *",
    "0 12 * * 6,0",
    "0 0 1 6 *",
    "0 3 * 2 *",
    "0 0 * 2 *",
    "1 0 * * *",
    "0 0 28 2 *",
]

START_POINTS = [
    datetime(2026, 1, 1, 0, 0, 30),  # odd seconds: next_after must floor to the minute
    datetime(2026, 2, 27, 23, 59, 0),
    datetime(2028, 2, 28, 12, 0, 0),  # 2028 is a leap year
    datetime(2026, 2, 28, 12, 0, 0),  # 2026 is not
    datetime(2026, 3, 31, 23, 58, 0),
    datetime(2026, 4, 30, 23, 59, 59),
    datetime(2026, 12, 31, 23, 59, 0),  # crosses the year boundary
    datetime(2026, 9, 30, 8, 17, 45),
    datetime(2026, 6, 15, 0, 0, 0),
]


def naive_next_after(spec: CronSpec, at: datetime, horizon_days: int = 366) -> datetime | None:
    """Independent reference: step one minute at a time, exactly as the pre-optimization
    implementation does. Kept deliberately dumb so it cannot share a bug with the jump
    logic it is meant to catch regressions in."""
    candidate = at.replace(second=0, microsecond=0) + timedelta(minutes=1)
    limit = at + timedelta(days=horizon_days)
    while candidate <= limit:
        if spec.matches(candidate):
            return candidate
        candidate += timedelta(minutes=1)
    return None


@pytest.mark.parametrize("expr", EXPRESSIONS)
@pytest.mark.parametrize("start", START_POINTS)
def test_next_after_matches_a_minute_by_minute_scan(expr: str, start: datetime) -> None:
    spec = CronSpec.parse(expr)
    assert spec.next_after(start) == naive_next_after(spec, start)


def test_never_matching_expression_returns_none_within_the_horizon() -> None:
    spec = CronSpec.parse("0 0 30 2 *")
    assert spec.next_after(datetime(2026, 1, 1)) is None


def test_day_and_weekday_are_both_required() -> None:
    # A leap day landing on a chosen weekday is rare (next after 2020 is 2044-02-29, a
    # Monday), so both constraints only agree within a horizon wide enough to reach it.
    # The default 366-day horizon on its own would find nothing, which is exactly the
    # point: day-of-month and weekday are AND'd, not OR'd.
    spec = CronSpec.parse("0 0 29 2 1")  # Monday
    assert spec.next_after(datetime(2020, 1, 1)) is None
    found = spec.next_after(datetime(2020, 1, 1), horizon_days=366 * 30)
    assert found is not None
    assert found == datetime(2044, 2, 29, 0, 0)
    assert (found.weekday() + 1) % 7 == 1


def test_result_is_always_strictly_after_the_start_even_on_a_minute_boundary() -> None:
    spec = CronSpec.parse("* * * * *")
    at = datetime(2026, 5, 1, 10, 30, 0)
    assert spec.next_after(at) == datetime(2026, 5, 1, 10, 31, 0)
