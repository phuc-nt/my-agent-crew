"""Five-field cron expressions (`min hour dom month dow`) with `*`, lists, ranges and
`*/n`, plus the `every: 30m` shorthand. Local time; day-of-week 0 and 7 are Sunday."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

_EVERY = re.compile(r"^(\d+)\s*([smhd])$")
_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
_RANGES = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))


def parse_every(text: str) -> int:
    match = _EVERY.match(text.strip().lower())
    if not match:
        raise ValueError(f"every must look like 30m, 2h or 1d, got {text!r}")
    seconds = int(match.group(1)) * _UNITS[match.group(2)]
    if seconds < 60:
        raise ValueError("every must be at least 60 seconds")
    return seconds


def _field(text: str, low: int, high: int) -> set[int]:
    values: set[int] = set()
    for part in text.split(","):
        step = 1
        if "/" in part:
            part, step_text = part.split("/", 1)
            step = int(step_text)
        if part == "*":
            start, end = low, high
        elif "-" in part:
            start_text, end_text = part.split("-", 1)
            start, end = int(start_text), int(end_text)
        else:
            start = end = int(part)
        if not (low <= start <= end <= high) or step < 1:
            raise ValueError(f"cron field {text!r} out of range {low}-{high}")
        values.update(range(start, end + 1, step))
    return values


@dataclass(frozen=True)
class CronSpec:
    minutes: frozenset[int]
    hours: frozenset[int]
    days: frozenset[int]
    months: frozenset[int]
    weekdays: frozenset[int]

    @classmethod
    def parse(cls, expr: str) -> CronSpec:
        parts = expr.split()
        if len(parts) != 5:
            raise ValueError(f"cron needs 5 fields, got {expr!r}")
        sets = [_field(p, lo, hi) for p, (lo, hi) in zip(parts, _RANGES, strict=True)]
        weekdays = {0 if d == 7 else d for d in sets[4]}
        return cls(*(frozenset(s) for s in sets[:4]), frozenset(weekdays))

    def matches(self, at: datetime) -> bool:
        weekday = (at.weekday() + 1) % 7  # python: Monday=0 → cron: Sunday=0
        return (
            at.minute in self.minutes
            and at.hour in self.hours
            and at.day in self.days
            and at.month in self.months
            and weekday in self.weekdays
        )

    def next_after(self, at: datetime, horizon_days: int = 366) -> datetime | None:
        candidate = at.replace(second=0, microsecond=0) + timedelta(minutes=1)
        limit = at + timedelta(days=horizon_days)
        while candidate <= limit:
            if self.matches(candidate):
                return candidate
            candidate += timedelta(minutes=1)
        return None


def due_between(cron: str | None, every: str | None, last: datetime, now: datetime) -> bool:
    """Whether a job should fire given it last fired (or was checked) at `last`."""
    if every:
        return (now - last).total_seconds() >= parse_every(every)
    if cron:
        spec = CronSpec.parse(cron)
        nxt = spec.next_after(last)
        return nxt is not None and nxt <= now
    return False


def next_run(cron: str | None, every: str | None, last: datetime, now: datetime) -> datetime | None:
    if every:
        return last + timedelta(seconds=parse_every(every))
    if cron:
        return CronSpec.parse(cron).next_after(now)
    return None
